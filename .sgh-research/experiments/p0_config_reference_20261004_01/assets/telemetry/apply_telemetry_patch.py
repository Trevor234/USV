#!/usr/bin/env python3
"""Guarded local edits only; no transport, no build, no whole-file source payload.

Run on the ROS workspace supplied by its owner. Default is a dry run. Each old
anchor must be unique; C++ anchors allow formatter whitespace differences. A
hash manifest, when supplied, must name every existing file changed by the patch.
All guards pass before any write. Original files receive a sibling backup.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
MARKER = "P0_REFERENCE_PREDICTION_V1"
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_][A-Za-z_0-9]*|\d+|[^\s]')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pattern(old: str) -> str:
    return r"\s*".join(re.escape(t) for t in TOKEN.findall(old))


def replace_once(text: str, old: str, new: str) -> str:
    hits = list(re.finditer(pattern(old), text))
    if len(hits) != 1:
        raise ValueError(f"expected one anchor ({len(hits)} found): {old[:100]}")
    hit = hits[0]
    return text[:hit.start()] + new + text[hit.end():]


def edit_function(text: str, name: str, operation) -> str:
    # The next out-of-class node method is the boundary, so overload/header
    # occurrences and comments elsewhere cannot satisfy a function anchor.
    start_hits = list(re.finditer(r"(?m)^.*MpcControllerNode::" + re.escape(name) + r"\s*\(", text))
    if len(start_hits) != 1:
        raise ValueError(f"function definition {name}: {len(start_hits)} matches")
    start = start_hits[0].start()
    nxt = re.search(r"(?m)^.*MpcControllerNode::[A-Za-z_]\w*\s*\(", text[start_hits[0].end():])
    end = start_hits[0].end() + nxt.start() if nxt else len(text)
    return text[:start] + operation(text[start:end]) + text[end:]


def patch_header(text: str) -> str:
    text = replace_once(text,
        "Eigen::MatrixXd build_reference_(const Vector6d & current_state);",
        "Eigen::MatrixXd build_reference_(const Vector6d & current_state,\n"
        "    ResearchReference * evidence = nullptr);")
    return replace_once(text, "std::unique_ptr<ResearchLogger> research_;",
        "// " + MARKER + "\n"
        "  bool reference_logging_enabled_ = false;\n"
        "  std::string research_nominal_config_hash_;\n"
        "  // state_lock_ protects these received-container versions.\n"
        "  uint64_t path_received_sequence_ = 0, profile_received_sequence_ = 0;\n"
        "  std::unique_ptr<ResearchLogger> research_;")


def patch_logger(text: str) -> str:
    include = '#include <usv_research_interfaces/msg/cycle_timing.hpp>'
    text = replace_once(text, include,
        include + '\n#include <usv_research_interfaces/msg/reference_prediction.hpp>')
    text = replace_once(text,
        "using ResearchCycle = usv_research_interfaces::msg::CycleTiming;",
        "using ResearchCycle = usv_research_interfaces::msg::CycleTiming;\n"
        "using ResearchReference = usv_research_interfaces::msg::ReferencePrediction;")
    text = replace_once(text,
        "const std::string & baseline, const std::string & config)",
        "const std::string & baseline, const std::string & config,\n"
        "    bool reference_enabled = false, const std::string & nominal_hash = std::string())")
    text = replace_once(text, "context_ = node.get_node_base_interface()->get_context();",
        "// " + MARKER + "\n"
        "    reference_enabled_ = reference_enabled; nominal_hash_ = nominal_hash;\n"
        "    if (reference_enabled_ && (nominal_hash_.size() != 64 ||\n"
        "      nominal_hash_.find_first_not_of(\"0123456789abcdef\") != std::string::npos))\n"
        "    {throw std::runtime_error(\"reference telemetry requires nominal SHA256\");}\n"
        "    context_ = node.get_node_base_interface()->get_context();")
    text = replace_once(text, 'streams_["cycle"] = {};',
        'streams_["cycle"] = {};\n'
        '    if (reference_enabled_) {\n'
        '      reference_pub_ = node.create_publisher<ResearchReference>("/research/reference_prediction", 100);\n'
        '      streams_["reference_prediction"] = {};\n'
        '    }')
    text = replace_once(text, "template<class T> uint64_t enqueue(T msg, const std::string & stream)",
        "void identity(ResearchReference & msg) const {\n"
        "    identity<ResearchReference>(msg);\n"
        "    msg.schema_version = \"p0-reference-prediction-v1\";\n"
        "  }\n"
        "  template<class T> uint64_t enqueue(T msg, const std::string & stream)")
    text = replace_once(text, "std::variant<ResearchState, ResearchApplied, ResearchCycle>",
        "std::variant<ResearchState, ResearchApplied, ResearchCycle, ResearchReference>")
    text = replace_once(text,
        "if constexpr (std::is_same_v<T, ResearchCycle>) {cycle_pub_->publish(msg);}",
        "if constexpr (std::is_same_v<T, ResearchCycle>) {cycle_pub_->publish(msg);}\n"
        "          if constexpr (std::is_same_v<T, ResearchReference>) {reference_pub_->publish(msg);}")
    text = replace_once(text, 'j["queue_dropped_total"] = dropped;',
        'j["queue_dropped_total"] = dropped;\n'
        '    j["reference_prediction"] = {{"enabled", reference_enabled_},\n'
        '      {"schema_version", "p0-reference-prediction-v1"}, {"nominal_config_hash", nominal_hash_},\n'
        '      {"prediction_policy", "accepted_post_deadline_only"}, {"record_policy", "solve_invoked_only"},\n'
        '      {"matrix_layout", "k_major"}, {"queue_capacity_events", 1024}};')
    return replace_once(text, "rclcpp::Publisher<ResearchCycle>::SharedPtr cycle_pub_;",
        "rclcpp::Publisher<ResearchCycle>::SharedPtr cycle_pub_;\n"
        "  rclcpp::Publisher<ResearchReference>::SharedPtr reference_pub_;\n"
        "  bool reference_enabled_ = false;\n"
        "  std::string nominal_hash_;")


def patch_node(text: str) -> str:
    text = replace_once(text,
        'this->declare_parameter("enable_research_logging", false);',
        '// ' + MARKER + '\n'
        '  this->declare_parameter("enable_reference_prediction_logging", false);\n'
        '  this->declare_parameter("research_nominal_config_hash", std::string(""));\n'
        '  this->declare_parameter("enable_research_logging", false);')
    text = replace_once(text, 'if (this->get_parameter("enable_research_logging").as_bool()) {',
        'reference_logging_enabled_ = this->get_parameter("enable_reference_prediction_logging").as_bool();\n'
        '  research_nominal_config_hash_ = this->get_parameter("research_nominal_config_hash").as_string();\n'
        '  if (reference_logging_enabled_ && !this->get_parameter("enable_research_logging").as_bool()) {\n'
        '    throw std::runtime_error("reference telemetry requires enable_research_logging");\n'
        '  }\n'
        '  if (this->get_parameter("enable_research_logging").as_bool()) {')
    text = replace_once(text, 'this->get_parameter("research_config_hash").as_string());',
        'this->get_parameter("research_config_hash").as_string(),\n'
        '      reference_logging_enabled_, research_nominal_config_hash_);')
    for method, count in [('path_callback_', 'path_received_sequence_'),
                          ('profile_callback_', 'profile_received_sequence_')]:
        text = edit_function(text, method, lambda s, c=count: replace_once(s,
            "std::lock_guard<std::mutex> lk(state_lock_);",
            "std::lock_guard<std::mutex> lk(state_lock_);\n"
            f"  if (reference_logging_enabled_) {{++{c};}}"))

    def run(s: str) -> str:
        s = replace_once(s, "Eigen::MatrixXd reference;",
            "Eigen::MatrixXd reference;\n"
            "  const bool observe_reference = reference_logging_enabled_ && research_ && research_->armed();\n"
            "  ResearchReference reference_event;")
        s = replace_once(s, "reference = build_reference_(current_state);",
            "reference = build_reference_(current_state, observe_reference ? &reference_event : nullptr);")
        # After the state lock closes; the actual local matrix is immutable while
        # callbacks may update the source containers during solve.
        s = replace_once(s,
            "if (research_ && research_->armed()) { research_cycle_.solve_invoked = true;",
            (ROOT / "node_run_capture.cpp.txt").read_text(encoding="utf-8") +
            "  if (research_ && research_->armed()) {\n    research_cycle_.solve_invoked = true;")
        s = replace_once(s, "control_count_++;",
            (ROOT / "node_result_capture.cpp.txt").read_text(encoding="utf-8") + "  control_count_++;")
        return s
    text = edit_function(text, "run_dynamic_mpc_", run)

    def build(s: str) -> str:
        s = replace_once(s, "build_reference_(const Vector6d & current_state)",
            "build_reference_(const Vector6d & current_state, ResearchReference * evidence)")
        s = replace_once(s, "const auto & path = reference_path_;",
            "const auto & path = reference_path_;\n" +
            (ROOT / "build_reference_metadata.cpp.txt").read_text(encoding="utf-8"))
        s = replace_once(s,
            "int idx = std::min(nearest + std::max(1, reference_start_offset_), static_cast<int>(path.size()) - 1);",
            "int idx = std::min(nearest + std::max(1, reference_start_offset_),\n"
            "                     static_cast<int>(path.size()) - 1);\n"
            "  if (evidence) {evidence->nearest_index = nearest; evidence->start_index = idx;}")
        s = replace_once(s, "if (synced) {",
            "if (evidence) {\n"
            "    evidence->profile_synced = synced; evidence->profile_sync_reason = sync_reason;\n"
            "    evidence->reference_mode = synced ? \"profile_time\" : \"cruise_arc_fallback\";\n"
            "  }\n"
            "  if (synced) {")
        s = replace_once(s, "double t0 = times[idx];",
            "double t0 = times[idx];\n"
            "    if (evidence) {evidence->profile_t0_known = true; evidence->profile_t0 = t0;}")
        return s
    return edit_function(text, "build_reference_", build)


def patch_interfaces(text: str) -> str:
    return replace_once(text, '"msg/CycleTiming.msg")',
        '"msg/CycleTiming.msg" "msg/ReferencePrediction.msg")\n# ' + MARKER)


def patch_launch(text: str) -> str:
    # Compose with the independent-controller-config patch: different anchors.
    text = replace_once(text, "'enable_research_logging': 'false',",
        "# " + MARKER + "\n"
        "        'enable_reference_prediction_logging': 'false', 'research_nominal_config_hash': '',\n"
        "        'enable_research_logging': 'false',")
    return replace_once(text,
        "('enable_research_logging', 'research_logging_armed', 'research_frame_contract_verified')",
        "('enable_reference_prediction_logging', 'enable_research_logging',\n"
        "         'research_logging_armed', 'research_frame_contract_verified')")


PATCHES = {
    "src/usv_mpc_cpp/include/usv_mpc_cpp/mpc_node.hpp": patch_header,
    "src/usv_mpc_cpp/include/usv_mpc_cpp/research_logger.hpp": patch_logger,
    "src/usv_mpc_cpp/src/mpc_node.cpp": patch_node,
    "src/usv_research_interfaces/CMakeLists.txt": patch_interfaces,
    "src/usv_bringup/launch/vrx.launch.py": patch_launch,
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--expected-hashes", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    expected = json.loads(args.expected_hashes.read_text(encoding="utf-8")) if args.expected_hashes else None
    plan = []
    for relative, edit in PATCHES.items():
        path = (workspace / relative).resolve()
        if not path.is_relative_to(workspace):
            raise ValueError("target outside supplied workspace")
        old = path.read_bytes()
        if expected is not None and expected.get(relative) != digest(old):
            raise ValueError(f"SHA mismatch or missing expected hash: {relative}")
        text = old.decode("utf-8")
        if MARKER in text:
            raise ValueError(f"patch marker already present: {relative}")
        updated = edit(text.replace("\r\n", "\n")).encode("utf-8")
        if updated == old:
            raise ValueError(f"no edit: {relative}")
        backup = path.with_name(path.name + ".pre_reference_prediction_v1")
        if args.write and backup.exists():
            raise ValueError(f"refuse to overwrite backup: {backup}")
        plan.append((path, old, updated, backup))
    new_path = workspace / "src/usv_research_interfaces/msg/ReferencePrediction.msg"
    if new_path.exists():
        raise ValueError("new message destination already exists")
    payload = (ROOT / "ReferencePrediction.msg").read_bytes()
    # Validate every file again before committing any mutation.
    if args.write:
        for path, old, _, _ in plan:
            if path.read_bytes() != old:
                raise ValueError(f"source changed during validation: {path}")
        for path, old, updated, backup in plan:
            backup.write_bytes(old)
            path.write_bytes(updated)
        new_path.write_bytes(payload)
    print(json.dumps({"written": args.write, "workspace": str(workspace), "files": [
        {"path": str(p.relative_to(workspace)), "before_sha256": digest(old),
         "after_sha256": digest(new)} for p, old, new, _ in plan],
        "message_sha256": digest(payload)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
