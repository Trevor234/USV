#!/usr/bin/env python3
"""Generate an independent F5/core test oracle only on the private ROS host.

This program transports nothing, builds nothing and changes no package source.
Only the SHA-bound F5 reference/gate/numeric callback excerpts are compiled into
the private oracle. Its bytes remain in the supplied create-only experiment dir.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

F5_NODE_SHA256 = "2f1b457ce9644d6ceff722e4ce328fa6a5de23a2cb94f8470c022e0bd70f2dd8"
HERE = Path(__file__).resolve().parent


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def function(text: str, name: str) -> str:
    hits = list(re.finditer(r"(?m)^.*MpcControllerNode::" + re.escape(name) + r"\s*\(", text))
    if len(hits) != 1:
        raise ValueError("expected one F5 function: " + name)
    start = hits[0].start()
    next_method = re.search(r"(?m)^.*MpcControllerNode::\w+\s*\(", text[hits[0].end():])
    end = hits[0].end() + next_method.start() if next_method else len(text)
    section = text[start:end]
    begin, finish = section.index("{"), section.rfind("}")
    return section[:finish + 1] if finish > begin else ""


def once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError("expected one original excerpt binding: " + old)
    return text.replace(old, new)


def oracle(f5: str) -> tuple[str, dict]:
    reference = function(f5, "build_reference_")
    gate = function(f5, "can_solve_")
    odom = function(f5, "odom_callback_")
    mapping = function(f5, "publish_vrx_thrust_")
    reference = once(reference, "MpcControllerNode::build_reference_", "F5ReferenceOracle::build_reference")
    reference = re.sub(r"\bResearchReference\b", "ReferenceMetadata", reference)
    gate = once(gate, "MpcControllerNode::can_solve_", "F5EligibilityOracle::can_solve")
    gate = once(gate, "double now = steady_now();", "double now = now_s_;")
    finite_start = odom.index("if (!std::isfinite(p.x)")
    finite_end = odom.index("std::lock_guard<std::mutex> lk(state_lock_);", finite_start)
    admission = odom[finite_start:finite_end].replace("return;", "return false;")
    if admission.count("quaternion_norm2") < 3 or "1e-12" not in admission:
        raise ValueError("actual F5 finite/quaternion/yaw gate not found")
    assign_start = odom.index("x_ = p.x;")
    assign_end = odom.index("r_ = t.angular.z;", assign_start) + len("r_ = t.angular.z;")
    assignments = odom[assign_start:assign_end]
    map_start = mapping.index("{") + 1
    map_end = mapping.index("if (research_", map_start)
    map_body = mapping[map_start:map_end].replace("std_msgs::msg::Float64", "F5Scalar")
    preamble = r'''// Private host-only oracle generated from the verified F5 backup.
// It is independent of the new core implementation and stays on this host.
#pragma once
#include "usv_mpc_cpp/p1_input_core.hpp"
namespace usv_mpc {
struct F5SolverShape {
  int n; double step;
  int N() const {return n;}
  double dt() const {return step;}
};
class F5ReferenceOracle {
public:
  F5ReferenceOracle(const ReferenceInput & in, int n, double dt, int offset, double cruise)
  : solver_{n, dt}, mpc_(&solver_), reference_path_(in.path),
    reference_path_stamp_(in.path_stamp), ref_profile_(in.profile),
    ref_profile_stamp_(in.profile_stamp), path_received_sequence_(in.path_sequence),
    profile_received_sequence_(in.profile_sequence), reference_start_offset_(offset),
    cruise_speed_(cruise) {}
  Eigen::MatrixXd build_reference(const Vector6d &, ReferenceMetadata *);
  bool cached_synced() const {return profile_synced_;}
  const std::string & cached_reason() const {return profile_sync_reason_;}
private:
  F5SolverShape solver_; F5SolverShape * mpc_;
  std::vector<std::array<double, 3>> reference_path_;
  std::pair<int, int> reference_path_stamp_;
  std::vector<std::array<double, 4>> ref_profile_;
  std::pair<int, int> ref_profile_stamp_;
  uint64_t path_received_sequence_, profile_received_sequence_;
  int reference_start_offset_; double cruise_speed_;
  bool profile_synced_ = false;
  std::string profile_sync_reason_ = "no_profile";
};
class F5EligibilityOracle {
public:
  explicit F5EligibilityOracle(const InputEligibility & c)
  : odom_received_(c.odom_received), path_received_(c.path_received),
    reference_path_(c.path_size), require_fcu_state_(c.require_fcu), armed_(c.armed),
    now_s_(c.now_s), last_odom_time_(c.last_odom_s), odom_timeout_s_(c.odom_timeout_s),
    last_state_time_(c.last_state_s), state_timeout_s_(c.state_timeout_s),
    mode_(c.mode), allowed_fcu_modes_(c.allowed_modes) {}
  std::pair<bool, std::string> can_solve() const;
private:
  bool odom_received_, path_received_;
  std::vector<int> reference_path_;
  bool require_fcu_state_, armed_;
  double now_s_, last_odom_time_, odom_timeout_s_, last_state_time_, state_timeout_s_;
  std::string mode_; std::vector<std::string> allowed_fcu_modes_;
};
struct F5Point {double x, y;};
struct F5Quat {double x, y, z, w;};
struct F5Linear {double x, y;};
struct F5Angular {double z;};
struct F5Twist {F5Linear linear; F5Angular angular;};
struct F5Scalar {double data;};
'''
    sample_bindings = '''  F5Point p{a[0], a[1]};
  F5Quat q{orientation[0], orientation[1], orientation[2], orientation[3]};
  F5Twist t{{a[2], a[3]}, {a[4]}};
'''
    result = preamble + reference + "\n" + gate + "\n"
    result += '''// Diagnostics are discarded by the macro; the original numeric
// conditions and their original order are retained verbatim below.
#define RCLCPP_WARN_THROTTLE(...) do {} while (false)
inline bool f5_admit_odom(const std::array<double, 5> & a,
  const std::array<double, 4> & orientation) {
''' + sample_bindings + admission + "  return true;\n}\n#undef RCLCPP_WARN_THROTTLE\n"
    result += '''inline Vector6d f5_compose_odom(const std::array<double, 5> & a,
  const std::array<double, 4> & orientation) {
''' + sample_bindings + '''  double psi = quaternion_to_yaw(q.x, q.y, q.z, q.w);
  double x_, y_, psi_, u_, v_, r_;
''' + assignments + '''
  Vector6d s; s << x_, y_, psi_, u_, v_, r_; return s;
}
inline Eigen::Vector2d f5_map_vrx(const Eigen::Vector2d & thrust,
  double vrx_thrust_scale_, double dyn_T_min_, double dyn_T_max_,
  double vrx_thrust_cmd_max_) {
''' + map_body + "  return Eigen::Vector2d(left.data, right.data);\n}\n}  // namespace usv_mpc\n"
    return result, {"metadata_fields": sorted(set(re.findall(r"evidence->(\w+)", reference))),
                    "extracted_functions": ["build_reference_", "can_solve_", "odom_callback_ numeric excerpts",
                                            "publish_vrx_thrust_ numeric prefix"],
                    "reference_transforms": ["class/function binding", "ROS message metadata type to same-field POD"],
                    "eligibility_transform": "deterministic fixture now_s replaces steady_now only",
                    "odom_transform": "void reject to bool false; diagnostics discarded; original predicates unchanged",
                    "mapping_transform": "scalar ROS message type to POD; original scale/clamp unchanged"}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--f5-source", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args(argv)
    source = args.f5_source.read_bytes()
    if sha(source) != F5_NODE_SHA256:
        raise ValueError("private F5 backup SHA does not match the verified baseline")
    if args.output_dir.exists():
        raise ValueError("oracle output must be a fresh create-only directory")
    fixture = HERE / "test_shared_input_core.cpp"
    files = {"f5_backup": args.f5_source,
             "core_header": args.workspace / "src/usv_mpc_cpp/include/usv_mpc_cpp/p1_input_core.hpp",
             "core_source": args.workspace / "src/usv_mpc_cpp/src/p1_input_core.cpp",
             "model_source": args.workspace / "src/usv_mpc_cpp/src/usv_model_dynamic.cpp",
             "utils_source": args.workspace / "src/usv_mpc_cpp/src/utils.cpp",
             "model_header": args.workspace / "src/usv_mpc_cpp/include/usv_mpc_cpp/usv_model_dynamic.hpp",
             "utils_header": args.workspace / "src/usv_mpc_cpp/include/usv_mpc_cpp/utils.hpp",
             "actual_legacy_wrapper": args.workspace / "src/usv_mpc_cpp/src/mpc_node.cpp",
             "public_fixture": fixture}
    before = {k: {"path": str(v), "sha256": sha(v.read_bytes())} for k, v in files.items()}
    private_oracle, transforms = oracle(source.decode("utf-8"))
    fixture_data = fixture.read_bytes()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    header = args.output_dir / "f5_input_oracle.hpp"
    with header.open("x", encoding="utf-8") as out:
        out.write(private_oracle)
    target = args.output_dir / fixture.name
    with target.open("xb") as out:
        out.write(fixture_data)
    after = {k: sha(v.read_bytes()) for k, v in files.items()}
    if any(after[k] != item["sha256"] for k, item in before.items()):
        raise RuntimeError("input source changed while oracle was generated; retain and reject this attempt")
    report = {"schema": "p1-m1-private-f5-oracle-generation/1", "inputs": before,
              "unchanged_after_generation": True, "transforms": transforms,
              "outputs": {header.name: sha(header.read_bytes()), target.name: sha(target.read_bytes())},
              "private_source_exported": False, "package_source_modified": False,
              "tests_run": False, "reference_fixture_pairs": 600,
              "shared_reference_calls_with_without_metadata": 1200,
              "gtest_cases": len(re.findall(r"TEST\(P1SharedInputCore,", fixture_data.decode())),
              "bounded_domain": {"N": [2, 20], "dt_s": 0.2, "path_points_max": 41,
                  "reference_input": "finite numeric path/profile; strictly increasing profile time when present",
                  "mapping": "finite ordered clamp bounds and finite commands/scales",
                  "propagation": "nonnegative source/target sim, sorted history, interval <=1 second"},
              "interpretation": "legacy math/source fixture equivalence and nominal analytic propagation only"}
    with (args.output_dir / "oracle_manifest.json").open("x", encoding="utf-8") as out:
        json.dump(report, out, indent=2)
        out.write("\n")
    # Print metadata only. Never print the private oracle body.
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
