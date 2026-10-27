"""Create immutable local defaults and preregistration from verified F3 evidence."""

import hashlib
import json
from pathlib import Path

from research_config_sources import VEHICLE_KEYS


HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1]
METADATA = WORK / "p0_model_consistency_2026-10-04/metadata_summary.json"
MIRROR = WORK / "p0_contract_impl_2026-10-03/source"


def emit(path, document):
    raw = (json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def main():
    metadata_raw = METADATA.read_bytes()
    if hashlib.sha256(metadata_raw).hexdigest() != "f597cfc3f4a8826d6b721205bfb97cc399014225b957b7cece4438545d68c80a":
        raise ValueError("Unexpected F3 metadata source identity")
    metadata = json.loads(metadata_raw)
    baseline = metadata["baselines"]["F3_20261004_quaternion_gate_01"]
    runtime = metadata["f3_pilot"]["context"]["runtime_effective_parameters"]
    assert metadata["f3_pilot"]["run_id"] == "p0_f3_gate_straight_20261004_03"
    assert metadata["f3_pilot"]["context"]["frozen_baseline_verified"]
    assets = {a["path"]: a["sha256"] for a in baseline["source_hashes"]}
    plant_rel = "usv_mpc_ws/src/usv_bringup/config/usv_params_sim.yaml"
    settings_rel = "usv_mpc_ws/src/usv_simulation/config/vrx_model.yaml"
    plant_raw = (MIRROR / plant_rel).read_bytes()
    settings_raw = (MIRROR / settings_rel).read_bytes()
    for rel, raw in ((plant_rel, plant_raw), (settings_rel, settings_raw)):
        if hashlib.sha256(raw).hexdigest() != assets[rel]:
            raise ValueError("Local source differs from F3: " + rel)
    nominal = {"/**": {"ros__parameters": {
        "vehicle": {key: runtime["vehicle"][key] for key in VEHICLE_KEYS},
        "thruster": {"T_max_forward": runtime["dynamic"]["T_max"],
                     "T_max_reverse": -runtime["dynamic"]["T_min"]},
    }}}
    generated = {}
    generated["p0_nominal_f3.yaml"] = emit(HERE / "p0_nominal_f3.yaml", nominal)
    for filename, raw in (("p0_plant_f3.yaml", plant_raw),):
        with (HERE / filename).open("xb") as stream:
            stream.write(raw)
        generated[filename] = hashlib.sha256(raw).hexdigest()
    fixture = {
        "schema": "p0-config-decoupling-preregistration/1",
        "status": "planned; no production mutation or Ubuntu experiment executed by this generator",
        "f3_manifest_sha256": baseline["manifest_sha256"],
        "metadata_sha256": hashlib.sha256(metadata_raw).hexdigest(),
        "defaults_sha256": generated,
        "simulation_source_sha256": assets[settings_rel],
        "default_nominal_parameters": nominal["/**"]["ros__parameters"]["vehicle"],
        "default_nominal_solver_bounds_N": {"T_max": 25.0, "T_min": -25.0},
        "default_physical_plant_bounds_N": {"max": 25.0, "min": -25.0},
        "plant_projection": "symmetric_mean on raw Yr_dot=0,Nv_dot=-0.363545; effective both=-0.1817725",
        "nominal_projection": "none; directly use nineteen effective F3 values",
        "cases": [
            {"id": "default", "change": None, "normal_pilot_required": True},
            {"id": "plant_mass_only", "side": "plant", "key": "vehicle.mass",
             "from": 14.2, "to": 17.04, "normal_pilot_required": True,
             "invariant": "all actual controller parameters and nominal_effective SHA unchanged"},
            {"id": "nominal_mass_only", "side": "nominal", "key": "vehicle.mass",
             "from": 14.2, "to": 17.04, "normal_pilot_required": True,
             "invariant": "plant raw source, effective nineteen parameters and actuator limits unchanged; canonicalized generated SDF unchanged"},
            {"id": "plant_thruster_only", "side": "plant", "key": "thruster.T_max_forward",
             "from": 25.0, "to": 20.0, "normal_pilot_required": False,
             "invariant": "B solver T_max/T_min and nominal identity unchanged",
             "purpose": "helper/actual launch wiring test; intentional plant clamp change kept outside three normal pilots"},
            {"id": "nominal_thruster_only", "side": "nominal", "key": "thruster.T_max_forward",
             "from": 25.0, "to": 20.0, "normal_pilot_required": False,
             "invariant": "plant actual command bounds remain +/-25 N",
             "purpose": "helper/actual launch wiring test; not a tracking-performance claim"},
        ],
        "normal_pilot_protocol": {
            "duration_wall_s": 60.0, "scheme": "B", "dt_s": 0.2, "horizon": 20,
            "profile_u_m_s": 0.8, "fallback_u_m_s": 0.6,
            "weights": "unchanged from F3", "independent_domains": True,
            "fresh_directories": True, "retain_all_failures": True,
        },
        "required_evidence": [
            "immutable config_sources.json and nominal_effective.yaml SHA",
            "actual controller ROS parameter dump and exact file SHA",
            "generated plant model_report/effective YAML/SDF hashes and projected nineteen values",
            "independent solver input constraints and physical plant command limits",
            "config-only comparisons exclude run/baseline/output/producer identity and observational switches, with excluded keys explicitly listed",
            "cross-run SDF comparisons canonicalize only generated mesh/output paths; retain exact raw SHA separately",
            "new frozen source/install/model baseline and real runtime overlay hashes",
            "reference_prediction stream source/recorded counts and actual nominal hash binding",
            "original thirteen-topic raw bags read-only checker and final end_unknown intervals",
        ],
        "not_proven": ["plant response equivalence", "P1 independent scheduling", "safety certificate",
                       "performance improvement", "exact execution timing", "GP label readiness"],
    }
    emit(HERE / "preregistered_fixture.json", fixture)
    print(json.dumps({"created": generated, "fixture": str(HERE / "preregistered_fixture.json")}, indent=2))


if __name__ == "__main__":
    main()
