"""Combine independent finite C0 gates; do not grant R5 or physical execution."""
import re

BASE_FLAGS=('passed','diagnostic_complete','source_bag_contract_complete','logical_admission_contract_passed',
            'lifecycle_verified','raw_input_recording_complete','raw_inputs_unchanged','activation_source_contract_complete')
def _hashes(value):
    return (type(value) is dict and bool(value) and all(type(k) is str and type(v) is str
            and re.fullmatch('[0-9a-f]{64}',v) for k,v in value.items()))

def source_gate(base, required_paths, actual_hashes):
    issues=[]
    def fail(code):issues.append(code)
    if type(base) is not dict:return {'passed':False,'issues':['base_not_object']}
    for k in BASE_FLAGS:
        if base.get(k) is not True:fail('base_flag:'+k)
    if base.get('issues')!=[]:fail('base_issues')
    if base.get('reader_error') is not None:fail('base_reader_error')
    if base.get('normal_contract_complete') is not False or base.get('execute_qualified') is not False:fail('unexpected_execution_qualification')
    reg=base.get('regulator_summary');worker=base.get('worker_summary')
    counter=lambda x:type(x) is int and 0<=x<=(1<<64)-1
    if not (type(reg) is dict and reg.get('type')=='source_summary' and counter(reg.get('generated')) and counter(reg.get('emitted')) and reg['generated']==reg['emitted'] and type(reg.get('dropped')) is int and reg['dropped']==0 and reg.get('normal_source_complete') is True):fail('regulator_terminal_incomplete_or_drop')
    if not (type(worker) is dict and worker.get('type')=='worker_summary' and counter(worker.get('generated_candidates')) and counter(worker.get('published_candidates')) and worker['generated_candidates']==worker['published_candidates'] and worker.get('fatal') is False and worker.get('terminal_numerical_failure') is False and worker.get('normal_source_complete') is True):fail('worker_terminal_incomplete_or_fatal')
    before=base.get('input_sha256_before');after=base.get('input_sha256_after')
    if not _hashes(before) or not _hashes(after):fail('input_hash_inventory_missing')
    elif before!=after:fail('input_hash_inventory_changed')
    elif not _hashes(actual_hashes) or before!=actual_hashes:fail('input_current_hashes_changed_or_unknown')
    if type(required_paths) not in (list,tuple) or not required_paths or not _hashes(before) or not set(required_paths)<=set(before):fail('required_input_pins_missing')
    return {'passed':not issues,'issues':issues,'scope':'full_source_bag_and_lifecycle_with_unchanged_actual_inputs'}

def combine(*,context,summary,postrun,base,delivery,comparison,policy,required_paths,actual_hashes,artifact_hashes,returncodes,assets_unchanged,host_clean):
    issues=[]
    def require(ok,code):
        if not ok:issues.append(code)
    sg=source_gate(base,required_paths,actual_hashes);require(sg['passed'],'base_source_bag_lifecycle')
    dictionaries=(context,summary,postrun,base,delivery,comparison,policy,returncodes,artifact_hashes)
    if not all(type(x) is dict for x in dictionaries):return {'schema':'p1-C0-combined-gates-v1','passed':False,'C0_complete':False,'issues':['input_objects'],'R5_complete':False,'execute_qualified':False}
    run=policy.get('run_id');require(type(run) is str and bool(run),'run_identity')
    require(policy.get('schema')=='p1-C0-predeclared-policy-v1' and type(policy.get('declared_duration_ns')) is int and policy['declared_duration_ns']==10000000000 and policy.get('mode')=='no_output' and type(policy.get('log_capacity')) is int and policy['log_capacity']==512,'predeclared_policy')
    for name,item in (('context',context),('summary',summary),('postrun',postrun),('base',base),('delivery',delivery),('comparison',comparison)):
        require(item.get('run_id')==run,'run_identity:'+name)
    require(context.get('mode')=='no_output' and base.get('mode')=='no_output','no_output_mode')
    dec=context.get('declaration',{});wit=context.get('fixed_witness',{});pins=policy.get('pins',{})
    require(type(dec) is dict and type(wit) is dict and type(pins) is dict,'configuration_objects')
    if type(dec) is dict and type(wit) is dict and type(pins) is dict:
        for k in ('contract_sha256','diagnostic_source_sha256','worker_binary_sha256','regulator_binary_sha256','runner_sha256','supervisor_sha256','witness_checker_sha256','base_checker_sha256'):
            require(type(pins.get(k)) is str and re.fullmatch('[0-9a-f]{64}',pins[k]) is not None,'predeclared_pin:'+k)
        require(type(pins.get('boot_id')) is str and re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',pins['boot_id']) is not None,'predeclared_boot')
        require(type(dec.get('duration_s')) in (int,float) and dec['duration_s']==10,'declared_10_seconds')
        for k in ('test_delay_ms','test_native_block_ms','test_prepare_block_ms','test_tick_block_ms'):
            require(type(dec.get(k)) is int and dec[k]==0,'fault_zero:'+k)
        require(dec.get('expected_fault')=='none','expected_normal_run')
        require(wit.get('enabled') is True and type(wit.get('test_sink_pause_ms')) is int and wit['test_sink_pause_ms']==0,'witness_on_pause_zero')
        require(context.get('contract_sha256')==pins.get('contract_sha256') and context.get('boot_id')==pins.get('boot_id'),'context_contract_boot_pins')
        require(context.get('runner_sha256')==pins.get('runner_sha256') and context.get('supervisor_sha256')==pins.get('supervisor_sha256'),'runtime_dependency_pins')
        require(base.get('checker_sha256')==pins.get('base_checker_sha256'),'base_checker_pin')
        binaries=context.get('binaries',{});source=context.get('diagnostic_source',{})
        require(type(binaries) is dict and type(source) is dict,'context_asset_objects')
        if type(binaries) is dict and type(source) is dict:
            require(source.get('sha256')==pins.get('diagnostic_source_sha256'),'diagnostic_source_pin')
            for k in ('worker','regulator'):
                require(type(binaries.get(k)) is dict and binaries[k].get('sha256')==pins.get(k+'_binary_sha256'),'binary_pin:'+k)
    if type(pins) is not dict:pins={}
    require(summary.get('failure') is None and summary.get('cleanup_complete') is True and summary.get('cleanup_failed') is False,'run_error_and_cleanup')
    require(summary.get('supervision_evidence_complete') is True and summary.get('graph_no_physical_publishers') is True,'supervision_and_physical_endpoints')
    require(summary.get('stop_reason')=='declared_duration_elapsed' and summary.get('normal_window_complete') is True,'normal_window_summary')
    wc=summary.get('window_completion',{})
    if type(wc) is dict:
        s,e=wc.get('window_started_ns'),wc.get('window_finished_ns');observed=wc.get('observed_duration_ns')
        require(type(s) is int and type(e) is int and type(observed) is int and 0<s<=e and e-s==observed and observed>=10000000000 and wc.get('required_duration_ns')==10000000000 and wc.get('normal_window_complete') is True and wc.get('stop_reason')=='declared_duration_elapsed','measured_10_seconds')
    else:require(False,'measured_10_seconds')
    require(postrun.get('passed') is True and postrun.get('normal_window_complete') is True,'postrun_collection')
    require(postrun.get('window_completion')==summary.get('window_completion') and type(postrun.get('window_completion')) is dict,'same_normal_window')
    audit=postrun.get('fixed_witness_check',{});normal=postrun.get('normal_source_check',{})
    require(type(audit) is dict and audit.get('requested') is True and audit.get('passed') is True and audit.get('witness_complete') is True and audit.get('issues')==[] and audit.get('report_write_succeeded') is True and audit.get('checker_sha256')==pins.get('witness_checker_sha256'),'independent_witness_gate')
    require(type(normal) is dict and normal.get('passed') is True and type(normal.get('checker_returncode')) is int and normal['checker_returncode']==0,'independent_normal_source_gate')
    require(_hashes(artifact_hashes) and 'base_report_sha256' in artifact_hashes and type(normal) is dict and _hashes({'base_report':normal.get('contract_report_sha256')}) and normal['contract_report_sha256']==artifact_hashes['base_report_sha256'],'independent_base_report_bytes')
    require(delivery.get('passed') is True and delivery.get('application_delivery_accounting_complete') is True and delivery.get('issues')==[],'application_ledger')
    require(comparison.get('passed') is True and comparison.get('source_join_verified') is True and comparison.get('issues')==[],'source_witness_comparison')
    require(set(returncodes)=={'runner','base','delivery','comparison'} and all(type(v) is int and v==0 for v in returncodes.values()),'actual_returncodes')
    require(assets_unchanged is True and host_clean is True,'asset_and_host_guards')
    for name,item in (('summary',summary),('postrun',postrun),('comparison',comparison)):
        require(item.get('normal_contract_complete') is False and item.get('execute_qualified') is False,'scope_flags:'+name)
    return {'schema':'p1-C0-combined-gates-v1','run_id':run,'passed':not issues,'C0_complete':not issues,
            'source_bag_lifecycle_gate':sg,'source_witness_join_verified':comparison.get('source_join_verified') is True,
            'source_bag_join_verified':sg['passed'],'issues':issues,'scope':'finite_normal_no_output_full_owned_C0',
            'R5_complete':False,'expected_log_overflow_mechanism_passed':False,'M0b_formally_complete':False,
            'M4_complete':False,'F6_complete':False,'P1_complete':False,'normal_contract_complete':False,
            'plant_acceptance_observed':False,'execute_qualified':False}
