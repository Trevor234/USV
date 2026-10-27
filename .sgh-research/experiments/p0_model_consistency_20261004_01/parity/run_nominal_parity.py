#!/usr/bin/env python3
"""Parity test of actual workspace Python and unchanged C++ USV nominal models.

Only compiles an independent driver into a new experiment directory. It does
not regenerate acados, change production files, or infer plant equivalence.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import ctypes
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
from pathlib import Path
import platform
import random
import shutil
import subprocess
import sys
import traceback

# Loading the real Python model must not create bytecode in its production tree.
sys.dont_write_bytecode=True

HYDRO_KEYS=["mass","Iz","xg","d_thruster","Xu_dot","Yv_dot","Yr_dot","Nv_dot","Nr_dot",
            "Xu","Yv","Yr","Nv","Nr","Xuu","Yvv","Yrr","Nvv","Nrr"]
MODEL_FILES=["usv_rl/usv_rl/dynamics.py",
             "usv_mpc_ws/src/usv_mpc_cpp/src/usv_model_dynamic.cpp",
             "usv_mpc_ws/src/usv_mpc_cpp/include/usv_mpc_cpp/usv_model_dynamic.hpp"]
TOLERANCES={"ode":{"atol":1e-10,"rtol":1e-10},"step":{"atol":1e-9,"rtol":1e-9},
            "trajectory":{"atol":1e-8,"rtol":1e-8}}
NATIVE_FILES=["usv_mpc_ws/src/usv_mpc_cpp/acados_generated/usv_dyn_nmpc_p_global_precompute_fun.c",
              "usv_mpc_ws/src/usv_mpc_cpp/acados_generated/usv_dyn_nmpc_model/usv_dyn_nmpc_dyn_disc_phi_fun.c"]

class NativeDiscrete:
    """Actual frozen generated C ABI, verified before passing numeric buffers."""
    def __init__(self,path):
        self.library=ctypes.CDLL(str(path))
        self.double_pointer=ctypes.POINTER(ctypes.c_double)
        self.precompute,self.precompute_info=self.bind("usv_dyn_nmpc_p_global_precompute_fun",[(30,1)],[(96,1)])
        self.discrete,self.discrete_info=self.bind("usv_dyn_nmpc_dyn_disc_phi_fun",[(8,1),(2,1),(6,1),(96,1)],[(8,1)])
        self.call_count=0

    def bind(self,name,input_shapes,output_shapes):
        def integer_meta(suffix):
            function=getattr(self.library,name+suffix)
            function.argtypes=[];function.restype=ctypes.c_int
            return function()
        n_in,n_out=integer_meta("_n_in"),integer_meta("_n_out")
        if n_in!=len(input_shapes) or n_out!=len(output_shapes):
            raise ValueError(f"{name} input/output count differs from verified ABI")
        shapes={}
        for side,expected_shapes in (("in",input_shapes),("out",output_shapes)):
            sparsity=getattr(self.library,name+"_sparsity_"+side)
            sparsity.argtypes=[ctypes.c_int];sparsity.restype=ctypes.POINTER(ctypes.c_int)
            observed=[]
            for index,(rows,cols) in enumerate(expected_shapes):
                pointer=sparsity(index)
                if not pointer: raise ValueError(f"{name} null sparsity metadata")
                # Real frozen generated C uses casadi_int=int and dense flag 1.
                schema=(pointer[0],pointer[1],pointer[2])
                if schema!=(rows,cols,1):
                    raise ValueError(f"{name} {side}[{index}] sparsity differs: {schema}")
                observed.append({"rows":rows,"cols":cols,"dense_flag":1})
            shapes[side]=observed
        work=getattr(self.library,name+"_work")
        work.argtypes=[ctypes.POINTER(ctypes.c_int)]*4;work.restype=ctypes.c_int
        counts=[ctypes.c_int() for _ in range(4)]
        status=work(*(ctypes.byref(count) for count in counts))
        sizes=[count.value for count in counts]
        if status!=0 or sizes!=[n_in,n_out,0,0]:
            raise ValueError(f"{name} work buffers differ from verified no-workspace ABI: {sizes}")
        function=getattr(self.library,name)
        function.argtypes=[ctypes.POINTER(self.double_pointer),ctypes.POINTER(self.double_pointer),
                           ctypes.POINTER(ctypes.c_int),self.double_pointer,ctypes.c_int]
        function.restype=ctypes.c_int
        return function,{"symbol":name,"n_in":n_in,"n_out":n_out,"sparsity":shapes,"work_sizes":sizes,
                         "casadi_int_type":"int","casadi_real_type":"double"}

    def evaluate(self,function,inputs,output_size):
        buffers=[(ctypes.c_double*len(values))(*values) for values in inputs]
        pointers=(self.double_pointer*len(inputs))(*(ctypes.cast(buffer,self.double_pointer) for buffer in buffers))
        result=(ctypes.c_double*output_size)()
        output_pointers=(self.double_pointer*1)(ctypes.cast(result,self.double_pointer))
        status=function(pointers,output_pointers,ctypes.POINTER(ctypes.c_int)(),self.double_pointer(),0)
        self.call_count+=1
        if status!=0: raise ValueError(f"native generated C returned {status}")
        values=list(result)
        if not all(math.isfinite(value) for value in values): raise ValueError("native generated C output is nonfinite")
        return values

    def global_data(self,global30):
        if len(global30)!=30: raise ValueError("native p_global requires 30 values")
        return self.evaluate(self.precompute,[global30],96)

    def step(self,state6,control2,previous2,global96):
        if [len(state6),len(control2),len(previous2),len(global96)]!=[6,2,2,96]:
            raise ValueError("native numerical input shape differs from verified ABI")
        return self.evaluate(self.discrete,[state6+previous2,control2,[0.]*6,global96],8)

def write_json(path:Path,value):
    with path.open("x",encoding="utf-8") as handle:
        json.dump(value,handle,ensure_ascii=False,indent=2,allow_nan=False)
        handle.write("\n")

def sha256(path:Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load_json(path:Path):
    return json.loads(path.read_text(encoding="utf-8"))

def compare_vector(actual,expected,mode):
    if len(actual)!=6 or len(expected)!=6 or not all(math.isfinite(v) for v in actual+expected):
        raise ValueError("six finite model outputs required")
    raw=[float(a)-float(b) for a,b in zip(actual,expected)]
    errors=list(raw)
    if mode!="ode":
        errors[2]=math.atan2(math.sin(raw[2]),math.cos(raw[2]))
    tolerance=TOLERANCES[mode]
    allowed=[tolerance["atol"]+tolerance["rtol"]*abs(b) for b in expected]
    return {"passed":all(abs(error)<=limit for error,limit in zip(errors,allowed)),
            "comparison_errors":errors,"raw_errors":raw,"allowed_component_errors":allowed,
            "max_abs_error":max(abs(error) for error in errors),
            "heading_uses_wrapped_difference":mode!="ode"}

def build_requests(fixture,seed=20261004,random_cases=16):
    dt=fixture["dt_s"]; substeps=fixture["rk4_substeps"]
    if dt!=.2 or substeps!=4:
        raise ValueError("this frozen parity gate requires production dt=.2 and RK4 substeps=4")
    if fixture["parameter_order"]!=HYDRO_KEYS:
        raise ValueError("fixture parameter order differs from frozen model contract")
    rng=random.Random(seed)
    extra=[]
    for i in range(random_cases):
        extra.append({"case_id":f"extra_random_{i:03d}",
                      "state_6":[rng.uniform(-100,100),rng.uniform(-100,100),rng.uniform(-math.pi,math.pi),
                                 rng.uniform(-1.2,1.2),rng.uniform(-.4,.4),rng.uniform(-.5,.5)],
                      "control_n":[rng.uniform(-25,25),rng.uniform(-25,25)]})
    random_commands=[[rng.uniform(-20,20),rng.uniform(-20,20)] for _ in range(40)]
    requests=[{"request_id":"defaults","mode":"defaults"}]
    for name,params in fixture["parameter_sets"].items():
        if set(params)!=set(HYDRO_KEYS):
            raise ValueError("every parameter set must explicitly declare all 19 hydro values")
        for case in fixture["one_step_and_ode_cases"]+extra:
            for mode in ("ode","step"):
                requests.append({"request_id":f"{name}:{mode}:{case['case_id']}","parameter_set":name,
                                 "case_id":case["case_id"],"mode":mode,"params":params,
                                 "dt_s":dt,"rk4_substeps":substeps,"state_6":case["state_6"],"control_n":case["control_n"]})
        trajectories=fixture["short_trajectory_cases"]+[
            {"case_id":"extra_random_trajectory_40","initial_state_6":[2.,-3.,math.pi-1e-7,.3,.02,.2],
             "controls_n":random_commands}]
        for case in trajectories:
            requests.append({"request_id":f"{name}:trajectory:{case['case_id']}","parameter_set":name,
                             "case_id":case["case_id"],"mode":"trajectory","params":params,
                             "dt_s":dt,"rk4_substeps":substeps,"state_6":case["initial_state_6"],"controls_n":case["controls_n"]})
    return requests

def baseline_identity(workspace:Path,baseline:Path,fixture:dict):
    manifest_path=baseline/"baseline_manifest.json"
    source_path=baseline/"source_hashes.json"
    installed_path=baseline/"installed_hashes.json"
    manifest=load_json(manifest_path)
    if manifest.get("baseline_id")!=fixture["baseline_id"]:
        raise ValueError("baseline identity differs from fixture")
    if manifest.get("integrity",{}).get("frozen_baseline_verified") is not True:
        raise ValueError("baseline collector integrity did not verify frozen baseline")
    source=load_json(source_path)
    if isinstance(source,dict): source=source["files"]
    index={entry["path"]:entry for entry in source}
    selected=list(MODEL_FILES)
    selected.extend(entry["path"] for entry in source if "acados_generated/" in entry["path"])
    if len(selected)!=len(set(selected)): selected=list(dict.fromkeys(selected))
    identities=[]
    for relative in selected:
        path=workspace/relative
        expected=index.get(relative,{}).get("sha256")
        actual=sha256(path)
        identities.append({"path":relative,"actual_sha256":actual,"baseline_sha256":expected,"matches_baseline":actual==expected})
    installed=load_json(installed_path)
    files=installed["files"] if isinstance(installed,dict) else installed
    binaries=[entry for entry in files if entry["path"].endswith("/lib/usv_mpc_cpp/mpc_node")]
    if len(binaries)!=1:
        raise ValueError("baseline must contain exactly one installed MPC node identity")
    entry=binaries[0];actual=sha256(workspace/entry["path"])
    identities.append({"path":entry["path"],"actual_sha256":actual,"baseline_sha256":entry["sha256"],
                       "matches_baseline":actual==entry["sha256"],
                       "usage":"installed production binary identity only; independent CLI compiles actual nominal source"})
    return {"baseline_id":manifest["baseline_id"],"baseline_manifest_sha256":sha256(manifest_path),
            "baseline_source_hashes_sha256":sha256(source_path),"baseline_installed_hashes_sha256":sha256(installed_path),
            "files":identities,"frozen_source_identity_verified":all(entry["matches_baseline"] for entry in identities)}

def run(args,output):
    workspace=args.workspace.expanduser().resolve()
    baseline=args.baseline.expanduser().resolve()
    fixture_path=args.fixture.expanduser().resolve()
    fixture=load_json(fixture_path)
    identity=baseline_identity(workspace,baseline,fixture)
    write_json(output/"source_identity_before.json",identity)
    if not identity["frozen_source_identity_verified"]:
        raise ValueError("current source/generated/installed identity differs from frozen F2")
    cpp_driver=Path(__file__).with_name("nominal_cpp_cli.cpp")
    if not cpp_driver.is_file():
        raise FileNotFoundError("nominal_cpp_cli.cpp must be staged next to this driver")
    compiler=shutil.which(args.compiler)
    if not compiler:
        raise FileNotFoundError("existing C++ compiler not found; dependencies were not installed")
    executable=output/"nominal_cpp_cli"
    compile_command=[compiler,"-std=c++17","-O2","-I",str(workspace/"usv_mpc_ws/src/usv_mpc_cpp/include"),
                     "-I",str(args.eigen_include),str(cpp_driver),
                     str(workspace/"usv_mpc_ws/src/usv_mpc_cpp/src/usv_model_dynamic.cpp"),"-o",str(executable)]
    write_json(output/"compiler_command.json",compile_command)
    build=subprocess.run(compile_command,text=True,capture_output=True,timeout=120)
    (output/"build_stdout.txt").write_text(build.stdout,encoding="utf-8")
    (output/"build_stderr.txt").write_text(build.stderr,encoding="utf-8")
    if build.returncode:
        raise RuntimeError(f"independent driver compile failed with code {build.returncode}")
    native_compiler=shutil.which(args.native_compiler)
    if not native_compiler: raise FileNotFoundError("existing native C compiler not found")
    native_library=output/"actual_acados_discrete.so"
    native_compile_command=[native_compiler,"-shared","-fPIC","-O2",*(str(workspace/path) for path in NATIVE_FILES),"-lm","-o",str(native_library)]
    write_json(output/"native_compiler_command.json",native_compile_command)
    native_build=subprocess.run(native_compile_command,text=True,capture_output=True,timeout=120)
    (output/"native_build_stdout.txt").write_text(native_build.stdout,encoding="utf-8")
    (output/"native_build_stderr.txt").write_text(native_build.stderr,encoding="utf-8")
    if native_build.returncode: raise RuntimeError(f"native existing generated C compilation failed: {native_build.returncode}")
    native=NativeDiscrete(native_library)
    native_data={name:native.global_data(global30) for name,global30 in fixture["acados_extra"]["global_parameter_30_by_parameter_set"].items()}
    write_json(output/"native_abi_and_global_data.json",{"abi":[native.precompute_info,native.discrete_info],
                                                     "global96_by_parameter_set":native_data,
                                                     "compiled_library_sha256":sha256(native_library),
                                                     "actual_generated_source_hashes":{path:sha256(workspace/path) for path in NATIVE_FILES}})
    sys.path.insert(0,str(workspace/"usv_rl"))
    dynamics=importlib.import_module("usv_rl.dynamics")
    if Path(dynamics.__file__).resolve()!=(workspace/MODEL_FILES[0]).resolve():
        raise ValueError("imported Python model is not the frozen actual workspace source")
    np=importlib.import_module("numpy")
    yaml=importlib.import_module("yaml")
    versions={"python_executable":sys.executable,"python_version":sys.version,"numpy":np.__version__,"yaml":yaml.__version__,
              "compiler":subprocess.run([compiler,"--version"],text=True,capture_output=True,timeout=10).stdout,
              "python_model_file":str(Path(dynamics.__file__).resolve()),"host":platform.node(),
              "production_sources_not_modified":True}
    write_json(output/"dependency_versions.json",versions)
    requests=build_requests(fixture,args.seed,args.random_cases)
    request_text="".join(json.dumps(request,ensure_ascii=False,allow_nan=False)+"\n" for request in requests)
    (output/"cpp_requests.jsonl").write_text(request_text,encoding="utf-8")
    cpp=subprocess.run([str(executable)],input=request_text,text=True,capture_output=True,timeout=120)
    (output/"cpp_stdout.jsonl").write_text(cpp.stdout,encoding="utf-8")
    (output/"cpp_stderr.txt").write_text(cpp.stderr,encoding="utf-8")
    if cpp.returncode:
        raise RuntimeError(f"actual C++ model evaluation failed with code {cpp.returncode}")
    responses=[json.loads(line) for line in cpp.stdout.splitlines() if line]
    if len(responses)!=len(requests):
        raise ValueError("C++ response count differs from request count")
    cpp_defaults=responses[0]["params"]
    py_defaults=asdict(dynamics.HydroParams())
    defaults={"python":py_defaults,"cpp":cpp_defaults,
              "differences":{key:{"python":py_defaults[key],"cpp":cpp_defaults[key]} for key in HYDRO_KEYS if py_defaults[key]!=cpp_defaults[key]},
              "status":"descriptive default parameter difference; explicit same-parameter parity is assessed separately"}
    write_json(output/"defaults_difference.json",defaults)
    group_counts=Counter();group_failures=Counter();max_by_group=defaultdict(float)
    native_group_counts=Counter();native_group_failures=Counter();native_max_by_group=defaultdict(float)
    rows=[]
    for request,response in zip(requests[1:],responses[1:]):
        if response.get("request_id")!=request["request_id"] or response.get("received_params")!=request["params"]:
            raise ValueError("C++ input/parameter echo mismatch")
        if response.get("dt_s")!=request["dt_s"] or response.get("rk4_substeps")!=request["rk4_substeps"]:
            raise ValueError("C++ integration configuration echo mismatch")
        params=dynamics.HydroParams(**request["params"])
        model=dynamics.USVDynamicModel(dt=request["dt_s"],rk4_substeps=request["rk4_substeps"],params=params)
        state=np.asarray(request["state_6"],dtype=np.float64)
        mode=request["mode"]
        row={"request":request,"cpp_response":response,"tolerance":TOLERANCES[mode]}
        if mode=="ode":
            expected=model.continuous_ode(state,np.asarray(request["control_n"],dtype=np.float64),params).tolist()
            comparison=compare_vector(response["result"],expected,mode)
            row.update(python_result=expected,comparison=comparison)
            passed=comparison["passed"];largest=comparison["max_abs_error"]
            row["cpp_python_passed"]=passed
        elif mode=="step":
            expected=model.forward(state,np.asarray(request["control_n"],dtype=np.float64)).tolist()
            comparison=compare_vector(response["result"],expected,mode)
            row.update(python_result=expected,comparison=comparison)
            passed=comparison["passed"];largest=comparison["max_abs_error"]
            row["cpp_python_passed"]=passed
            native_results=[native.step(request["state_6"],request["control_n"],list(previous),native_data[request["parameter_set"]])
                            for previous in fixture["acados_extra"]["previous_control_cases_n"]]
            native_comparisons=[compare_vector(result[:6],expected,mode) for result in native_results]
            memory=[result[6:]==request["control_n"] for result in native_results]
            prev_independent=all(all(abs(a-b)<=1e-9 for a,b in zip(native_results[0][:6],result[:6])) for result in native_results[1:])
            native_passed=all(c["passed"] for c in native_comparisons) and all(memory) and prev_independent
            row.update(native_augmented_results=native_results,native_comparisons=native_comparisons,
                       native_previous_control_cases=fixture["acados_extra"]["previous_control_cases_n"],
                       native_memory_exact_current_control=memory,native_physical_previous_control_independent=prev_independent,
                       native_passed=native_passed)
            passed=passed and native_passed
            native_group=request["parameter_set"]+":"+mode
            native_group_counts[native_group]+=1;native_group_failures[native_group]+=not native_passed
            native_max_by_group[native_group]=max(native_max_by_group[native_group],max(c["max_abs_error"] for c in native_comparisons))
        else:
            states=[state.tolist()]
            for command in request["controls_n"]:
                state=model.forward(state,np.asarray(command,dtype=np.float64));states.append(state.tolist())
            if len(response["states"])!=len(states): raise ValueError("trajectory output length mismatch")
            comparisons=[compare_vector(actual,expected,mode) for actual,expected in zip(response["states"],states)]
            row.update(python_states=states,comparisons=comparisons)
            passed=all(c["passed"] for c in comparisons);largest=max(c["max_abs_error"] for c in comparisons)
            row["cpp_python_passed"]=passed
            row["worst_step_index"]=max(range(len(comparisons)),key=lambda i:comparisons[i]["max_abs_error"])
            native_state=list(request["state_6"])
            previous=list(fixture["acados_extra"]["previous_control_cases_n"][1])
            native_states=[native_state]
            native_memory=[]
            for command in request["controls_n"]:
                result=native.step(native_state,command,previous,native_data[request["parameter_set"]])
                native_memory.append(result[6:]==command)
                native_state=result[:6];previous=result[6:];native_states.append(native_state)
            native_comparisons=[compare_vector(actual,expected,mode) for actual,expected in zip(native_states,states)]
            native_passed=all(c["passed"] for c in native_comparisons) and all(native_memory)
            row.update(native_states=native_states,native_comparisons=native_comparisons,
                       native_memory_exact_current_control_per_step=native_memory,native_passed=native_passed)
            passed=passed and native_passed
            native_group=request["parameter_set"]+":"+mode
            native_group_counts[native_group]+=1;native_group_failures[native_group]+=not native_passed
            native_max_by_group[native_group]=max(native_max_by_group[native_group],max(c["max_abs_error"] for c in native_comparisons))
        row["passed"]=passed
        rows.append(row)
        group=request["parameter_set"]+":"+mode
        group_counts[group]+=1;group_failures[group]+=not row["cpp_python_passed"];max_by_group[group]=max(max_by_group[group],largest)
    with (output/"case_results.jsonl").open("x",encoding="utf-8") as handle:
        for row in rows: handle.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+"\n")
    after=baseline_identity(workspace,baseline,fixture)
    write_json(output/"source_identity_after.json",after)
    stable=identity==after
    failures=[row["request"]["request_id"] for row in rows if not row["passed"]]
    summary={"schema":"p0-python-cpp-nominal-parity/1","passed":not failures and stable,
             "baseline_id":fixture["baseline_id"],"source_and_installed_identity_verified":identity["frozen_source_identity_verified"] and stable,
             "actual_models":"workspace usv_rl.dynamics and actual usv_model_dynamic.cpp compiled unchanged",
             "tolerances_frozen_before_execution":TOLERANCES,"seed":args.seed,"extra_random_cases":args.random_cases,
             "case_count":len(rows),"group_counts":dict(group_counts),"group_failures":dict(group_failures),
             "max_absolute_error_by_group":dict(max_by_group),"failed_request_ids":failures,
             "default_parameter_difference_count":len(defaults["differences"]),
             "python_cpp_nominal_verified":not any(group_failures.values()) and stable,
             "acados_native_generated_dynamics_verified":not any(native_group_failures.values()) and stable,
             "native_group_counts":dict(native_group_counts),"native_group_failures":dict(native_group_failures),
             "native_max_absolute_error_by_group":dict(native_max_by_group),"native_function_call_count":native.call_count,
             "plant_equivalence_proven":False,
             "real_boat_validated":False,"gp_labels_ready":False,
             "limitations":["Nominal software parity does not validate plant forces, transport, 6DOF physics, or physical execution intervals.",
                            "Actual acados discrete/precompute C functions are evaluated; OCP solver optimality and parameter-update cache dispatch are not certified.",
                            "Default parameter differences are reported; all parity cases explicitly override all 19 parameters."]}
    write_json(output/"results.json",summary)
    manifest={"schema":"p0-nominal-parity-run/1","created_utc":datetime.now(timezone.utc).isoformat(),
              "workspace":str(workspace),"output":str(output),"baseline":str(baseline),"fixture":str(fixture_path),
              "fixture_sha256":sha256(fixture_path),"python_driver_sha256":sha256(Path(__file__)),
              "cpp_driver_sha256":sha256(cpp_driver),"compiled_binary_sha256":sha256(executable),
              "native_compiled_library_sha256":sha256(native_library),
              "source_identity_before":identity,"source_identity_stable":stable,
              "evidence_hashes":{path.name:sha256(path) for path in output.iterdir() if path.is_file()},
              "production_files_written":False,"new_codegen_generated":False}
    write_json(output/"run_manifest.json",manifest)
    return summary

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace",required=True,type=Path)
    parser.add_argument("--baseline",required=True,type=Path,help="frozen F2 baseline directory")
    parser.add_argument("--fixture",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path,help="new independent experiment directory")
    parser.add_argument("--compiler",default="g++")
    parser.add_argument("--native-compiler",default="gcc")
    parser.add_argument("--eigen-include",type=Path,default=Path("/usr/include/eigen3"))
    parser.add_argument("--seed",type=int,default=20261004)
    parser.add_argument("--random-cases",type=int,default=16)
    args=parser.parse_args(argv)
    if args.random_cases<0: parser.error("random-cases must be nonnegative")
    output=args.output.expanduser().resolve()
    if output.exists(): parser.error("output already exists; do not overwrite experiments")
    output.mkdir(parents=True,exist_ok=False)
    try:
        summary=run(args,output)
        print(json.dumps({"passed":summary["passed"],"case_count":summary["case_count"],"output":str(output),
                          "acados_native_generated_dynamics_verified":summary["acados_native_generated_dynamics_verified"],"plant_equivalence_proven":False}))
        return 0 if summary["passed"] else 2
    except Exception as exc:
        report={"schema":"p0-python-cpp-nominal-parity/1","passed":False,
                "error":f"{type(exc).__name__}: {exc}","numerical_parity_claimed":False,
                "acados_native_generated_dynamics_verified":False,"plant_equivalence_proven":False,"gp_labels_ready":False}
        write_json(output/"execution_error.json",report)
        (output/"error_traceback.txt").write_text(traceback.format_exc(),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False))
        return 1

if __name__=="__main__":
    sys.exit(main())
