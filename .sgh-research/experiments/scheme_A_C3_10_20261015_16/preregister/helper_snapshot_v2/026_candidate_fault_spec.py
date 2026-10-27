"""Declared transport mutations of an actual native candidate, never native failures."""
from copy import deepcopy
import math

# (label, changed field, operation, value, expected registration reason)
CASES=[
 ("schema","job.schema_version","set","foreign_fixture","foreign"),
 ("run","job.run_id","set","foreign_fixture","foreign"),
 ("boot","job.boot_id","set","foreign_fixture","foreign"),
 ("contract","job.contract_hash","set","foreign_fixture","foreign"),
 ("nominal","job.nominal_hash","set","foreign_fixture","foreign"),
 ("job_worker","job.worker_instance","set","foreign_fixture","foreign"),
 ("worker","worker_instance","set","foreign_fixture","foreign_worker"),
 ("backend","backend","set","foreign_fixture","foreign_worker"),
 ("N","job.horizon_steps","set",19,"shape_or_time_contract"),
 ("dt","job.prediction_dt","set",.1,"shape_or_time_contract"),
 ("deadline","job.deadline_steady_ns","add",1,"shape_or_time_contract"),
 ("target_time","job.target_steady_ns","add",1,"shape_or_time_contract"),
 ("X_nan","x_prediction.7","special","nan","nonfinite_or_timing"),
 ("U_nan","u_prediction.7","special","nan","nonfinite_or_timing"),
 ("first_inf","first_control.0","special","inf","nonfinite_or_timing"),
 ("backend_nan","backend_ms","special","nan","nonfinite_or_timing"),
 ("backend_negative","backend_ms","set",-1.,"nonfinite_or_timing"),
 ("end_reverse","solve_end_ns","relative","solve_start_ns:-1","nonfinite_or_timing"),
 ("first_mismatch","first_control.0","add",.125,"first_control_mismatch"),
 ("initial_mismatch","x_prediction.0","add",.125,"prediction_initial_mismatch"),
 ("echo_reference","job.reference.0","add",.125,"job_echo_mismatch"),
 ("echo_job_id","job.job_id","add",100000,"job_echo_mismatch"),
 ("echo_target_tick","job.target_tick","add",1,"job_echo_mismatch"),
 ("echo_task","job.task_generation","add",1,"job_echo_mismatch"),
 ("echo_model","job.model_generation","add",1,"job_echo_mismatch"),
 ("echo_config","job.config_generation","add",1,"job_echo_mismatch"),
 ("receive_before_freeze","worker_receive_ns","relative","job.freeze_steady_ns:-1","native_timing_order"),
 ("end_future","solve_end_ns","add",1000000000,"native_timing_order"),
 ("success_false","success","set",False,"solver_failed"),
 ("prediction_false","prediction_available","set",False,"solver_failed"),
 ("invoked_false","solver_invoked","set",False,"solver_failed"),
 ("freeze_future","job.freeze_steady_ns","add",1000000000,"invalid_time_order"),
 ("reference_nan","job.reference.0","special","nan","nonfinite"),
 ("anchor_unknown","job.anchor_known.0","set",False,"unknown_or_invalid_anchor"),
 ("history_shape","job.history_channel","append",0,"history_shape_or_time"),
 ("duplicate",None,"same",None,"duplicate"),
 ("reordered",None,"previous",None,"wrong_tick"),
 ("late",None,"late",None,"late"),
]
assert len(CASES)==38 and len({v[0] for v in CASES})==38

def get_field(obj,path):
    for key in path.split("."):obj=obj[int(key)] if key.isdecimal() else getattr(obj,key)
    return obj

def mutate(base,case):
    m=deepcopy(base);_,field,operation,value,_=case
    if field is None:return m
    keys=field.split(".");parent=m
    for key in keys[:-1]:parent=parent[int(key)] if key.isdecimal() else getattr(parent,key)
    key=keys[-1]
    old=parent[int(key)] if key.isdecimal() else getattr(parent,key)
    if operation=="set":new=value
    elif operation=="add":new=old+value
    elif operation=="special":new=math.nan if value=="nan" else math.inf
    elif operation=="relative":
        source,offset=value.split(":");new=get_field(base,source)+int(offset)
    elif operation=="append":new=list(old)+[value]
    else:raise ValueError("unknown declared mutation")
    if key.isdecimal():parent[int(key)]=new
    else:setattr(parent,key,new)
    return m
