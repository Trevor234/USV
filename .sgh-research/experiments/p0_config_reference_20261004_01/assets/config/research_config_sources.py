"""Opt-in independent nominal/plant configuration evidence for dynamic B.

No renderer is called for nominal parameters. JSON is emitted as a YAML subset;
ordinary ROS YAML input uses the already-installed PyYAML dependency on Ubuntu.
This module records sources and compares actual runtime values. It does not claim
plant response equivalence, execution acknowledgment, or residual-label validity.
"""

import hashlib
import json
import math
import os
from pathlib import Path


VEHICLE_KEYS = (
    "mass", "Iz", "xg", "d_thruster", "Xu_dot", "Yv_dot", "Yr_dot",
    "Nv_dot", "Nr_dot", "Xu", "Yv", "Yr", "Nv", "Nr", "Xuu", "Yvv",
    "Yrr", "Nvv", "Nrr",
)
GEOMETRY_KEYS = ("length", "beam", "draft", "height")
THRUSTER_KEYS = ("T_max_forward", "T_max_reverse")
PWM_KEYS = ("pwm_min", "pwm_center", "pwm_max")


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def read_document(path):
    raw = Path(path).read_bytes()
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except json.JSONDecodeError:
        import yaml
        value = yaml.safe_load(raw.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Configuration must be a mapping: " + str(path))
    return raw, value


def numeric(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a finite numeric value: " + name)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite numeric value: " + name)
    return result


def parameter_mapping(document):
    """Accept direct actual dump values or one ROS node parameter mapping."""
    if "vehicle" in document or "vehicle.mass" in document:
        return document
    candidates = [v["ros__parameters"] for v in document.values()
                  if isinstance(v, dict) and "ros__parameters" in v]
    if len(candidates) != 1 or not isinstance(candidates[0], dict):
        raise ValueError("Expected exactly one ros__parameters mapping")
    return candidates[0]


def extract_vehicle(parameters, allow_geometry=True):
    nested = parameters.get("vehicle", {})
    if not isinstance(nested, dict):
        raise ValueError("vehicle must be a mapping")
    allowed = set(VEHICLE_KEYS) | (set(GEOMETRY_KEYS) if allow_geometry else set())
    if set(nested) - allowed:
        raise ValueError("Unexpected vehicle keys: " + repr(sorted(set(nested) - allowed)))
    result = {}
    for key in VEHICLE_KEYS:
        flat = "vehicle." + key
        if key not in nested and flat not in parameters:
            raise ValueError("Missing vehicle parameter: " + key)
        value = numeric(nested[key] if key in nested else parameters[flat], flat)
        if key in nested and flat in parameters and value != numeric(parameters[flat], flat):
            raise ValueError("Conflicting nested and flat vehicle parameter: " + key)
        result[key] = value
    if result["mass"] <= 0 or result["Iz"] <= 0 or result["d_thruster"] <= 0:
        raise ValueError("mass, Iz, d_thruster must be positive")
    a = result["mass"] - result["Xu_dot"]
    b = result["mass"] - result["Yv_dot"]
    c = result["mass"] * result["xg"] - result["Yr_dot"]
    d = result["mass"] * result["xg"] - result["Nv_dot"]
    e = result["Iz"] - result["Nr_dot"]
    if a <= 0 or b <= 0 or e <= 0 or b * e - c * d <= 0:
        raise ValueError("Nominal/plant planar inertia matrix is invalid")
    return result


def extract_thruster(parameters):
    thruster = parameters.get("thruster")
    if not isinstance(thruster, dict) or set(thruster) - set(THRUSTER_KEYS + PWM_KEYS):
        raise ValueError("Expected thruster limits and optional PWM metadata only")
    limits = {key: numeric(thruster[key], "thruster." + key) for key in THRUSTER_KEYS}
    if any(v <= 0 for v in limits.values()):
        raise ValueError("Both thruster command magnitudes must be positive")
    return limits


def load_asset(path, role):
    resolved = Path(path).expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("Configuration must be a regular file")
    raw, document = read_document(resolved)
    parameters = parameter_mapping(document)
    if set(parameters) - {"vehicle", "thruster"}:
        raise ValueError(role + " input may contain vehicle/thruster only")
    return {
        "source_path": str(resolved), "source_sha256": sha_bytes(raw),
        "vehicle": extract_vehicle(parameters), "thruster": extract_thruster(parameters),
        "raw": raw,
    }


def _write_json(path, document):
    raw = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True,
                      allow_nan=False) + "\n").encode("utf-8")
    with Path(path).open("xb") as stream:
        stream.write(raw)
    return sha_bytes(raw)


def prepare_config_sources(nominal_path, plant_path, simulation_path, output_dir):
    nominal = load_asset(nominal_path, "nominal")
    plant = load_asset(plant_path, "plant")
    if os.path.samefile(nominal["source_path"], plant["source_path"]):
        raise ValueError("Nominal and plant must be distinct source assets")
    simulation = Path(simulation_path).expanduser().resolve(strict=True)
    settings_raw, settings = read_document(simulation)
    policy = settings.get("added_mass_cross_policy")
    if policy not in ("symmetric_mean", "strict"):
        raise ValueError("Unsupported or missing explicit added_mass_cross_policy")
    expected_plant = dict(plant["vehicle"])
    if policy == "symmetric_mean":
        mean = (expected_plant["Yr_dot"] + expected_plant["Nv_dot"]) / 2.0
        expected_plant["Yr_dot"] = mean
        expected_plant["Nv_dot"] = mean
    elif expected_plant["Yr_dot"] != expected_plant["Nv_dot"]:
        raise ValueError("Strict plant policy requires Yr_dot == Nv_dot")
    output = Path(output_dir).expanduser().absolute()
    output.mkdir(parents=False, exist_ok=False)
    paths = {"nominal_input": output / "nominal_input.yaml",
             "plant_input": output / "plant_input.yaml",
             "simulation_input": output / "simulation_input.yaml",
             "nominal_effective": output / "nominal_effective.yaml"}
    for role, asset in (("nominal", nominal), ("plant", plant)):
        with paths[role + "_input"].open("xb") as stream:
            stream.write(asset["raw"])
    with paths["simulation_input"].open("xb") as stream:
        stream.write(settings_raw)
    nominal_effective_sha = _write_json(paths["nominal_effective"], {
        "/**": {"ros__parameters": {"vehicle": nominal["vehicle"],
                                     "thruster": nominal["thruster"]}}})
    report = {
        "schema": "p0-independent-config-sources/1",
        "nominal": {k: v for k, v in nominal.items() if k != "raw"},
        "plant": {k: v for k, v in plant.items() if k != "raw"},
        "simulation": {"source_path": str(simulation), "source_sha256": sha_bytes(settings_raw),
                       "added_mass_cross_policy": policy},
        "snapshot_paths": {k: str(v) for k, v in paths.items()},
        "nominal_effective_sha256": nominal_effective_sha,
        "nominal_projection": "none; exact nineteen explicit vehicle values",
        "expected_plant_effective_vehicle": expected_plant,
        "solver_input_constraints": {
            "T_max": nominal["thruster"]["T_max_forward"],
            "T_min": -nominal["thruster"]["T_max_reverse"],
            "source": "nominal thruster magnitudes; independent of plant limits"},
        "plant_actuator_command_limits": {
            "max_N": plant["thruster"]["T_max_forward"],
            "min_N": -plant["thruster"]["T_max_reverse"],
            "source": "plant thruster input; generated SDF confirmation required"},
        "source_snapshots_unchanged": True,
        "runtime_effective_verified": False,
        "plant_generated_verified": False,
        "plant_equivalence_proven": False,
        "exact_execution_timing_available": False,
        "gp_labels_ready": False,
    }
    # Source changes during capture fail the launch; do not silently accept a mix.
    for asset in (nominal, plant):
        if sha_bytes(Path(asset["source_path"]).read_bytes()) != asset["source_sha256"]:
            raise ValueError("Source changed while snapshotting")
    if sha_bytes(simulation.read_bytes()) != report["simulation"]["source_sha256"]:
        raise ValueError("Simulation source changed while snapshotting")
    _write_json(output / "config_sources.json", report)
    return report


def verify_runtime_sources(config_dir, model_dir, runtime_parameters):
    """Return new evidence; never mutate the original static source report."""
    config_dir = Path(config_dir)
    report = json.loads((config_dir / "config_sources.json").read_text(encoding="utf-8"))
    for role in ("nominal", "plant", "simulation"):
        snapshot = Path(report["snapshot_paths"][role + "_input"])
        if sha_bytes(snapshot.read_bytes()) != report[role]["source_sha256"]:
            raise ValueError("Modified source snapshot: " + role)
    nominal_effective = Path(report["snapshot_paths"]["nominal_effective"])
    if sha_bytes(nominal_effective.read_bytes()) != report["nominal_effective_sha256"]:
        raise ValueError("Modified nominal effective snapshot")
    if isinstance(runtime_parameters, (str, Path)):
        dump_path = Path(runtime_parameters).resolve(strict=True)
        dump_raw, runtime_parameters = read_document(dump_path)
        dump_evidence = {"path": str(dump_path), "sha256": sha_bytes(dump_raw),
                         "source": "actual external ROS parameter dump file"}
    else:
        dump_evidence = {"path": None, "sha256": None,
                         "source": "caller mapping only; bind actual dump identity externally"}
    params = parameter_mapping(runtime_parameters)
    actual_vehicle = extract_vehicle(params)
    if actual_vehicle != report["nominal"]["vehicle"]:
        raise ValueError("Runtime controller vehicle does not match independent nominal")
    dynamic = params.get("dynamic", {})
    for key in ("T_max", "T_min"):
        actual = numeric(dynamic[key] if key in dynamic else params["dynamic." + key], key)
        if actual != report["solver_input_constraints"][key]:
            raise ValueError("Runtime solver bound does not match independent nominal: " + key)
    model_dir = Path(model_dir)
    model_report_path = model_dir / "model_report.json"
    _, model_report = read_document(model_report_path)
    actual_plant = extract_vehicle({"vehicle": model_report["effective_vehicle"]})
    if actual_plant != report["expected_plant_effective_vehicle"]:
        raise ValueError("Generated plant effective vehicle mismatch")
    plant_effective_path = model_dir / "effective_vehicle.yaml"
    _, plant_document = read_document(plant_effective_path)
    plant_params = parameter_mapping(plant_document)
    if extract_vehicle(plant_params) != actual_plant:
        raise ValueError("Plant model report/effective YAML disagree")
    if extract_thruster(plant_params) != report["plant"]["thruster"]:
        raise ValueError("Plant thruster limits do not match plant source")
    import xml.etree.ElementTree as ET
    sdf_path = model_dir / "model.sdf"
    model = ET.parse(sdf_path).getroot().find("model")
    thrusters = model.findall("plugin[@name='gz::sim::systems::Thruster']")
    if len(thrusters) != 2:
        raise ValueError("Expected two generated plant Thruster plugins")
    for thruster in thrusters:
        for tag, expected in (("max_thrust_cmd", report["plant_actuator_command_limits"]["max_N"]),
                              ("min_thrust_cmd", report["plant_actuator_command_limits"]["min_N"])):
            if numeric(float(thruster.findtext(tag)), tag) != expected:
                raise ValueError("Generated SDF actuator bound mismatch")
    return {
        "schema": "p0-independent-config-runtime/1",
        "runtime_parameter_dump": dump_evidence,
        "config_sources_sha256": sha_bytes((config_dir / "config_sources.json").read_bytes()),
        "controller_effective_vehicle": actual_vehicle,
        "solver_input_constraints": report["solver_input_constraints"],
        "plant_effective_vehicle": actual_plant,
        "plant_actuator_command_limits": report["plant_actuator_command_limits"],
        "plant_projection": report["simulation"],
        "model_report_sha256": sha_bytes(model_report_path.read_bytes()),
        "plant_effective_yaml_sha256": sha_bytes(plant_effective_path.read_bytes()),
        "plant_sdf_sha256": sha_bytes(sdf_path.read_bytes()),
        "nominal_effective_yaml_sha256": report["nominal_effective_sha256"],
        "runtime_effective_verified": True,
        "plant_generated_verified": True,
        "plant_equivalence_proven": False,
        "exact_execution_timing_available": False,
        "gp_labels_ready": False,
    }
