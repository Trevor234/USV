#!/usr/bin/env python3
"""Read-only actual-run comparison for independent nominal/plant configuration.

The acceptance scope is configuration isolation, not a pure payload experiment,
tracking improvement, plant response equivalence, execution acknowledgment or GP.
The only SDF normalization replaces generated mesh URI output-directory prefixes;
all other source text, elements, attributes and values remain byte-significant.
"""

import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from urllib.request import url2pathname
import xml.etree.ElementTree as ET

from research_config_sources import (
    VEHICLE_KEYS, load_asset, parameter_mapping, read_document, verify_runtime_sources,
)


IDENTITY_EXCLUSIONS = (
    "research_run_id", "research_output_dir", "research_config_hash",
    "research_nominal_config_hash",
)
URI_TAG = re.compile(r"(<uri(?:\s[^>]*)?>)([\s\S]*?)(</uri\s*>)")
DEFAULT_MASS = 14.2
PROBE_MASS = 17.04


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_parameter_dump(raw):
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        import yaml
        value = yaml.safe_load(raw)
    if not isinstance(value, dict):
        raise ValueError("Actual ROS parameter dump must be a mapping")
    return parameter_mapping(value)


def flatten_parameters(parameters, prefix=""):
    result = {}
    for key, value in parameters.items():
        name = prefix + str(key)
        if isinstance(value, dict):
            nested = flatten_parameters(value, name + ".")
            for leaf, item in nested.items():
                if leaf in result:
                    raise ValueError("Duplicate actual parameter key: " + leaf)
                result[leaf] = item
        else:
            if name in result:
                raise ValueError("Duplicate actual parameter key: " + name)
            result[name] = value
    return result


def finite_parameter_values(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, (list, tuple)):
        return all(finite_parameter_values(item) for item in value)
    if isinstance(value, dict):
        return all(finite_parameter_values(item) for item in value.values())
    return True


def differences(left, right):
    return {key: {"baseline": left.get(key), "probe": right.get(key),
                  "baseline_present": key in left, "probe_present": key in right}
            for key in sorted(set(left) | set(right)) if key not in left or key not in right or left[key] != right[key]}


def normalized_sdf_and_meshes(model_dir):
    model_dir = Path(model_dir).resolve(strict=True)
    sdf_path = model_dir / "model.sdf"
    raw = sdf_path.read_bytes()
    text = raw.decode("utf-8")
    tree = ET.fromstring(text)
    mesh_uris = [e.text for e in tree.findall(".//geometry/mesh/uri")]
    if not mesh_uris or any(not isinstance(uri, str) or not uri.strip() for uri in mesh_uris):
        raise ValueError("Expected generated mesh URI(s) in actual SDF")
    replacements, mesh_hashes, normalization = {}, {}, []
    for uri in mesh_uris:
        original = uri.strip()
        parsed = urlsplit(original)
        if parsed.scheme not in ("", "file") or parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("Only local generated mesh URIs are supported: " + original)
        decoded_path = url2pathname(parsed.path)
        mesh = Path(decoded_path)
        if not mesh.is_absolute():
            mesh = model_dir / mesh
        mesh = mesh.resolve(strict=True)
        if not mesh.is_relative_to(model_dir) or not mesh.is_file():
            raise ValueError("Mesh URI is not a contained generated model asset")
        relative = mesh.relative_to(model_dir).as_posix()
        replacement = ("file://" if parsed.scheme == "file" else "") + "__MODEL_OUTPUT__/" + relative
        replacements[original] = replacement
        mesh_hashes[relative] = sha(mesh.read_bytes())
        normalization.append({"original_uri": original, "normalized_uri": replacement,
                              "mesh_relative_path": relative, "mesh_sha256": mesh_hashes[relative]})
    replaced = set()

    def normalize_tag(match):
        inner = match.group(2)
        stripped = html.unescape(inner.strip())
        if stripped not in replacements:
            return match.group(0)
        replacement = replacements[stripped]
        left_space = inner[:len(inner) - len(inner.lstrip())]
        right_space = inner[len(inner.rstrip()):]
        replaced.add(stripped)
        return match.group(1) + left_space + html.escape(replacement, quote=False) + right_space + match.group(3)

    normalized = URI_TAG.sub(normalize_tag, text).encode("utf-8")
    if replaced != set(replacements):
        raise ValueError("Could not bind every generated mesh URI to exact SDF text")
    return {"raw_sdf_sha256": sha(raw), "normalized_sdf_sha256": sha(normalized),
            "mesh_sha256_by_relative_path": mesh_hashes, "mesh_uri_normalizations": normalization,
            "normalization_rule": "replace contained generated mesh URI directory only; retain all other SDF text"}


def load_run(run_dir):
    run_dir = Path(run_dir).resolve(strict=True)
    if not run_dir.is_dir():
        raise ValueError("Existing actual experiment directory required")
    source_path = run_dir / "config/config_sources.json"
    runtime_path = run_dir / "config_runtime.json"
    graph_path = run_dir / "topic_graph.json"
    sources, recorded_runtime, graph = (read_json(p) for p in (source_path, runtime_path, graph_path))
    dump = graph["effective_parameter_dump"]
    if dump.get("returncode") != 0 or not isinstance(dump.get("stdout"), str):
        raise ValueError("Actual ROS parameter dump was unsuccessful")
    if sha(dump["stdout"].encode("utf-8")) != dump.get("stdout_sha256"):
        raise ValueError("Actual ROS dump stdout hash mismatch")
    params = parse_parameter_dump(dump["stdout"])
    if not finite_parameter_values(params):
        raise ValueError("Actual parameter dump contains nonfinite numeric values")
    flat = flatten_parameters(params)
    for required in IDENTITY_EXCLUSIONS + ("research_baseline_id",):
        if not isinstance(flat.get(required), str) or not flat[required]:
            raise ValueError("Missing actual controller identity parameter: " + required)
    if graph.get("run_id") != flat["research_run_id"] or graph.get("baseline_id") != flat["research_baseline_id"]:
        raise ValueError("Graph and actual controller run/baseline identity mismatch")
    # Read snapshots only inside this supplied actual experiment directory.
    for value in sources["snapshot_paths"].values():
        if not Path(value).resolve(strict=True).is_relative_to(run_dir / "config"):
            raise ValueError("Source snapshot path escapes this actual run config directory")
    for role in ("nominal", "plant"):
        asset = load_asset(sources["snapshot_paths"][role + "_input"], role)
        for key in ("source_sha256", "vehicle", "thruster"):
            if asset[key] != sources[role][key]:
                raise ValueError("Source report disagrees with actual frozen input: " + role + "." + key)
    _, settings = read_document(sources["snapshot_paths"]["simulation_input"])
    if settings.get("added_mass_cross_policy") != sources["simulation"]["added_mass_cross_policy"]:
        raise ValueError("Source report disagrees with actual plant projection policy")
    expected_plant = dict(sources["plant"]["vehicle"])
    if settings["added_mass_cross_policy"] == "symmetric_mean":
        mean = (expected_plant["Yr_dot"] + expected_plant["Nv_dot"]) / 2.0
        expected_plant.update(Yr_dot=mean, Nv_dot=mean)
    elif settings["added_mass_cross_policy"] != "strict" or expected_plant["Yr_dot"] != expected_plant["Nv_dot"]:
        raise ValueError("Unsupported or inconsistent plant projection policy")
    if expected_plant != sources["expected_plant_effective_vehicle"]:
        raise ValueError("Source report contains inconsistent expected plant projection")
    runtime = verify_runtime_sources(run_dir / "config", run_dir / "model", params)
    runtime_keys = ("config_sources_sha256", "controller_effective_vehicle", "solver_input_constraints",
                    "plant_effective_vehicle", "plant_actuator_command_limits", "model_report_sha256",
                    "plant_effective_yaml_sha256", "plant_sdf_sha256", "nominal_effective_yaml_sha256",
                    "runtime_effective_verified", "plant_generated_verified")
    if any(recorded_runtime.get(key) != runtime[key] for key in runtime_keys):
        raise ValueError("Recorded config_runtime disagrees with freshly read actual assets/dump")
    if flat["research_nominal_config_hash"] != runtime["nominal_effective_yaml_sha256"]:
        raise ValueError("Actual controller nominal hash does not bind nominal effective asset")
    model_report = read_json(run_dir / "model/model_report.json")
    physical_geometry = {key: model_report.get(key) for key in (
        "mass_kg", "waterline_beam_m", "displacement_m3", "yaw_inertia_at_com", "com_m")}
    for key in ("mass_kg", "waterline_beam_m", "displacement_m3", "yaw_inertia_at_com"):
        value = physical_geometry[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError("Missing/nonfinite actual generated model geometry field: " + key)
    com = physical_geometry["com_m"]
    if not isinstance(com, list) or len(com) != 3 or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in com):
        raise ValueError("Missing/nonfinite generated model com_m")
    if physical_geometry["mass_kg"] != runtime["plant_effective_vehicle"]["mass"]:
        raise ValueError("Generated report mass and effective plant mass disagree")
    model_identity = normalized_sdf_and_meshes(run_dir / "model")
    return {
        "experiment": str(run_dir), "run_id": flat["research_run_id"],
        "baseline_id": flat["research_baseline_id"], "sources": sources,
        "runtime": runtime, "flat_parameters": flat,
        "actual_dump_stdout_sha256": dump["stdout_sha256"],
        "evidence_sha256": {"config_sources.json": sha(source_path.read_bytes()),
                            "config_runtime.json": sha(runtime_path.read_bytes()),
                            "topic_graph.json": sha(graph_path.read_bytes())},
        "geometry": physical_geometry, "model_identity": model_identity,
    }


def compare_runs(baseline, plant, nominal):
    checks, failures = [], []

    def check(name, passed, detail=None):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        if not passed:
            failures.append(name)

    check("three_distinct_actual_runs", len({r["experiment"] for r in (baseline, plant, nominal)}) == 3
          and len({r["run_id"] for r in (baseline, plant, nominal)}) == 3)
    check("same_frozen_baseline_id", baseline["baseline_id"] == plant["baseline_id"] == nominal["baseline_id"])
    b, p, n = (r["runtime"] for r in (baseline, plant, nominal))
    bsrc, psrc, nsrc = (r["sources"] for r in (baseline, plant, nominal))
    check("nineteen_vehicle_keys", all(set(r[k]) == set(VEHICLE_KEYS) for r in (b, p, n)
          for k in ("controller_effective_vehicle", "plant_effective_vehicle")))
    check("baseline_f3_default_mass", b["controller_effective_vehicle"]["mass"] == DEFAULT_MASS
          and b["plant_effective_vehicle"]["mass"] == DEFAULT_MASS)
    check("baseline_nominal_plant_effective_nineteen_equal", b["controller_effective_vehicle"] == b["plant_effective_vehicle"])
    check("default_solver_and_physical_limits_25N", all(
        r["solver_input_constraints"]["T_max"] == 25.0 and r["solver_input_constraints"]["T_min"] == -25.0
        and r["plant_actuator_command_limits"]["max_N"] == 25.0
        and r["plant_actuator_command_limits"]["min_N"] == -25.0 for r in (b, p, n)))
    check("plant_mass_nominal_nineteen_unchanged", b["controller_effective_vehicle"] == p["controller_effective_vehicle"])
    check("plant_mass_nominal_solver_constraints_unchanged", b["solver_input_constraints"] == p["solver_input_constraints"])
    check("plant_mass_nominal_effective_sha_unchanged", b["nominal_effective_yaml_sha256"] == p["nominal_effective_yaml_sha256"])
    check("plant_mass_nominal_raw_source_sha_unchanged", bsrc["nominal"]["source_sha256"] == psrc["nominal"]["source_sha256"])
    plant_delta = differences(b["plant_effective_vehicle"], p["plant_effective_vehicle"])
    nominal_delta = differences(b["controller_effective_vehicle"], n["controller_effective_vehicle"])
    for label, delta in (("plant_mass", plant_delta), ("nominal_mass", nominal_delta)):
        check(label + "_only_one_effective_mass_change", set(delta) == {"mass"}
              and delta["mass"]["baseline"] == DEFAULT_MASS and delta["mass"]["probe"] == PROBE_MASS, delta)
    check("nominal_mass_nominal_identity_changes", b["nominal_effective_yaml_sha256"] != n["nominal_effective_yaml_sha256"])
    check("nominal_mass_solver_constraints_unchanged", b["solver_input_constraints"] == n["solver_input_constraints"])
    check("nominal_mass_plant_nineteen_unchanged", b["plant_effective_vehicle"] == n["plant_effective_vehicle"])
    check("nominal_mass_plant_actuator_limits_unchanged", b["plant_actuator_command_limits"] == n["plant_actuator_command_limits"])
    check("nominal_mass_plant_raw_source_sha_unchanged", bsrc["plant"]["source_sha256"] == nsrc["plant"]["source_sha256"])
    check("all_simulation_raw_source_sha_unchanged", len({s["simulation"]["source_sha256"] for s in (bsrc, psrc, nsrc)}) == 1)
    check("nominal_mass_plant_mesh_sha_unchanged", baseline["model_identity"]["mesh_sha256_by_relative_path"] == nominal["model_identity"]["mesh_sha256_by_relative_path"])
    check("nominal_mass_plant_sdf_equal_except_generated_mesh_uri_dir", baseline["model_identity"]["normalized_sdf_sha256"] == nominal["model_identity"]["normalized_sdf_sha256"])
    check("nominal_mass_generated_geometry_unchanged", baseline["geometry"] == nominal["geometry"])
    excluded_values = {r["run_id"]: {key: r["flat_parameters"][key] for key in IDENTITY_EXCLUSIONS}
                       for r in (baseline, plant, nominal)}
    control = [{key: value for key, value in r["flat_parameters"].items() if key not in IDENTITY_EXCLUSIONS}
               for r in (baseline, plant, nominal)]
    control_plant_delta = differences(control[0], control[1])
    control_nominal_delta = differences(control[0], control[2])
    check("plant_mass_all_other_actual_controller_parameters_unchanged", not control_plant_delta, control_plant_delta)
    check("nominal_mass_actual_controller_diff_only_vehicle_mass", set(control_nominal_delta) == {"vehicle.mass"}
          and control_nominal_delta["vehicle.mass"]["baseline"] == DEFAULT_MASS
          and control_nominal_delta["vehicle.mass"]["probe"] == PROBE_MASS, control_nominal_delta)
    beam_ratio = plant["geometry"]["waterline_beam_m"] / baseline["geometry"]["waterline_beam_m"]
    mesh_changed = baseline["model_identity"]["mesh_sha256_by_relative_path"] != plant["model_identity"]["mesh_sha256_by_relative_path"]
    check("plant_mass_generated_mesh_changes_as_renderer_geometry_coupling", mesh_changed)
    return {
        "schema": "p0-f4-actual-config-isolation-comparison/1", "passed": not failures,
        "exit_code": 0 if not failures else 2, "scope": "configuration isolation only",
        "checks": checks, "failures": failures,
        "actual_controller_comparison": {
            "identity_fields_excluded_exactly": list(IDENTITY_EXCLUSIONS),
            "excluded_actual_values_by_run": excluded_values,
            "plant_mass_differences_after_exclusions": control_plant_delta,
            "nominal_mass_differences_after_exclusions": control_nominal_delta,
            "intentional_nominal_parameter_change": {"vehicle.mass": {"from": DEFAULT_MASS, "to": PROBE_MASS}},
        },
        "runs": {role: {key: r[key] for key in (
            "experiment", "run_id", "baseline_id", "actual_dump_stdout_sha256",
            "evidence_sha256", "geometry", "model_identity", "runtime")}
                 for role, r in (("baseline", baseline), ("plant_mass", plant), ("nominal_mass", nominal))},
        "plant_probe_interpretation": {
            "name": "plant mass configuration probe with coupled procedural geometry",
            "renderer_source_fact": "hull_mesh derives waterline width from mass / density / unit-width submerged volume",
            "actual_waterline_beam_ratio": beam_ratio, "actual_mesh_sha_changed": mesh_changed,
            "formula_based_expected_ratio": PROBE_MASS / DEFAULT_MASS,
            "geometry_numbers_source": "actual generated model_report.json; configuration artifact, not measured motion",
            "expected_ratio_is_not_substituted_for_actual_generated_geometry": True,
            "not_a_pure_payload_step_performance_experiment": True,
        },
        "plant_equivalence_proven": False, "performance_improvement_proven": False,
        "P1_complete": False, "exact_execution_timing_available": False, "gp_labels_ready": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run", type=Path, required=True)
    parser.add_argument("--plant-run", type=Path, required=True)
    parser.add_argument("--nominal-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.expanduser().absolute()
    run_paths = [p.expanduser().resolve() for p in (args.baseline_run, args.plant_run, args.nominal_run)]
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        parser.error("output must be a new file with an existing parent directory")
    if any(output.resolve().is_relative_to(path) for path in run_paths):
        parser.error("write the new comparison outside all three original experiment directories")
    try:
        runs = [load_run(p) for p in run_paths]
        report = compare_runs(*runs)
    except Exception as exc:
        report = {"schema": "p0-f4-actual-config-isolation-comparison/1", "passed": False,
                  "exit_code": 1, "scope": "configuration isolation only",
                  "configuration_or_read_error": f"{type(exc).__name__}: {exc}",
                  "plant_equivalence_proven": False, "performance_improvement_proven": False,
                  "P1_complete": False, "exact_execution_timing_available": False, "gp_labels_ready": False}
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed": report["passed"], "exit_code": report["exit_code"], "output": str(output)}))
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
