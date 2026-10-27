from pathlib import Path
import hashlib, json, shlex, subprocess, sys
ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT / "implementation/t2_author"
BUILD = ROOT / "build/cmake"
RUNS = ROOT / "implementation/runs"
OUT = ROOT / "evidence/freeze"
OUT.mkdir(parents=True, exist_ok=True)
RUNS.mkdir(parents=True, exist_ok=True)
BUILD.mkdir(parents=True, exist_ok=True)
def pin(p):
    raw = p.read_bytes(); return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
files = {str(p.relative_to(TREE)): {"path": str(p), **pin(p)} for p in sorted(TREE.rglob("*")) if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
bundle = OUT / "source_bundle.json"
bundle.write_text(json.dumps({"schema": "M4-owned-source-bundle/v1", "files": files, "file_count": len(files), "physical_production_release": False, "scope": "M4_owned_local_nominal_only_v1"}, indent=2, sort_keys=True) + chr(10))
bundle_sha = pin(bundle)["sha256"]
driver = TREE / "t2_scenario_driver_v1.py"
driver_sha = pin(driver)["sha256"]
print(f"bundle: {bundle_sha[:16]} driver: {driver_sha[:16]} files: {len(files)}")
SETUP = "set -e; export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; unset VIRTUAL_ENV PYTHONHOME PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH; source /opt/ros/jazzy/setup.bash; source /home/trevor/USV/vrx_ws/install/local_setup.bash; source /home/trevor/USV/usv_mpc_ws/install/local_setup.bash; export LD_LIBRARY_PATH=/home/trevor/acados/lib:\"
V4 = "/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/p1_execution_contract_v4.json"
V3 = "/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json"
rc = subprocess.run(["/bin/bash", "-c", SETUP, "bash", "cmake", "-S", str(TREE), "-B", str(BUILD), "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG", "-DP1_OWNED_SOURCE_BUNDLE_SHA256=" + bundle_sha, "-DP1_DRIVER_TOOL_SHA256=" + driver_sha, "-DP1_V4_CONTRACT_FILE=" + V4, "-DP1_V3_CONTRACT_FILE=" + V3], capture_output=True, text=True, timeout=300).returncode
assert rc == 0, "configure failed"
rc = subprocess.run(["/bin/bash", "-c", SETUP, "bash", "cmake", "--build", str(BUILD), "--target", "p1_m4_worker_owned", "p1_m4_regulator_owned", "p1_m4_fixture_owned", "-j2"], capture_output=True, text=True, timeout=1800).returncode
assert rc == 0, "build failed"
print("ELFs built")
REG66 = json.loads(Path("/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_owned_takeover_20261023_66/implementation/selected_runtime_registry_w2_v1.json").read_bytes())
roles = {}
for name, role in (("p1_m4_worker_owned", "worker"), ("p1_m4_regulator_owned", "regulator"), ("p1_m4_fixture_owned", "fixture")):
    binary = BUILD / name
    roles[role] = {"binary": str(binary), "binary_sha256": pin(binary)["sha256"], "source_bundle": {"path": str(bundle), "sha256": bundle_sha}}
roles["recorder"] = REG66["roles"]["recorder"]
registry = {"schema": "M4-owned-runtime-registry/v2", "scope": "M4_owned_local_nominal_only_v1", "driver": str(driver), "driver_tool_sha256": driver_sha, "regulator_source": str(TREE / "observer/src/shadow/regulator_owned_execute.cpp"), "regulator_source_sha256": pin(TREE / "observer/src/shadow/regulator_owned_execute.cpp")["sha256"], "roles": roles, "acados_runtime": REG66["acados_runtime"]}
registry_path = ROOT / "implementation/t2_registry.json"
registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True) + chr(10))
sys.path.insert(0, str(TREE))
import t2_action_contract as t2
from w2_runtime_contract import registration_preflight_t2
ENV = {"ROS_DOMAIN_ID": "120", "ROS_LOCALHOST_ONLY": "1", "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp"}
table = {"schema": "M4-t2-action-table-v1", "run_id": "T2-T2C-G4C", "case": "T2C-driver-shutdown-interleave", "contract_sha256": t2.V3_CONTRACT_SHA, "actions": [{"id": "a1", "action": "driver_shutdown_request", "parameters": {"reason": "G4C"}, "trigger": {"phase": "ready_window", "job_id": 2, "delay_ms": 0}}], "clauses": {"ordering": "ready_commit<request<=stopping_observed<=activation_guard", "stop_must_precede_activation_guard": True, "guard_rejects_target": True, "full_exit_and_storage_required": True}}
t2.validate_table(table, {"run_id": table["run_id"], "case": table["case"], "contract_sha256": t2.V3_CONTRACT_SHA})
tp = ROOT / "implementation/T2C_table.json"
tp.write_text(json.dumps(table, indent=2, sort_keys=True) + chr(10))
TOPICS = "/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/implementation/m4_topics_v1.json"
reg = {"schema": t2.REGISTRATION_SCHEMA, "scope": t2.ORDINARY_SCOPE, "case": "T2C-driver-shutdown-interleave", "run_id": "T2-T2C-G4C", "production_physical_release_enabled": False, "fault_injection_enabled": False, "domain_id": 120, "max_seconds": 45, "automatic_retries": 0, "contract": V3, "contract_sha256": t2.V3_CONTRACT_SHA, "action_table": str(tp), "action_table_sha256": pin(tp)["sha256"], "registry": str(registry_path), "registry_sha256": pin(registry_path)["sha256"], "topics": TOPICS, "topics_sha256": pin(TOPICS)["sha256"], "output": str(RUNS / "T2C_G4C"), "audit_tool": {"path": str(TREE / "audit_t2.py"), "sha256": pin(TREE / "audit_t2.py")["sha256"]}, "executed": False}
rp = ROOT / "implementation/T2C_registration.json"
rp.write_text(json.dumps(reg, indent=2, sort_keys=True) + chr(10))
registration_preflight_t2(reg, driver, environment=ENV)
print("T2C PREFLIGHT PASSED")
print("FREEZE COMPLETE")