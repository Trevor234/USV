import unittest,copy
from check_C0_gates import source_gate,combine,BASE_FLAGS

def good_source():return {**{k:True for k in BASE_FLAGS},'mode':'no_output','run_id':'run','issues':[],
    'regulator_summary':{'type':'source_summary','generated':4,'emitted':4,'dropped':0,'normal_source_complete':True},
    'worker_summary':{'type':'worker_summary','generated_candidates':1,'published_candidates':1,'fatal':False,'terminal_numerical_failure':False,'normal_source_complete':True},
    'normal_contract_complete':False,'execute_qualified':False,'input_sha256_before':{'required':'a'*64},'input_sha256_after':{'required':'a'*64}}
def _good():
    false={'normal_contract_complete':False,'execute_qualified':False};pins={'contract_sha256':'a'*64,'boot_id':'boot','diagnostic_source_sha256':'b'*64,'worker_binary_sha256':'c'*64,'regulator_binary_sha256':'d'*64}
    return dict(context={'run_id':'run','mode':'no_output','contract_sha256':'a'*64,'boot_id':'boot','diagnostic_source':{'sha256':'b'*64},'binaries':{'worker':{'sha256':'c'*64},'regulator':{'sha256':'d'*64}},'declaration':{'duration_s':10,'expected_fault':'none',**{k:0 for k in ('test_delay_ms','test_native_block_ms','test_prepare_block_ms','test_tick_block_ms')}},'fixed_witness':{'enabled':True,'test_sink_pause_ms':0}},
        summary={'run_id':'run','failure':None,'cleanup_complete':True,'cleanup_failed':False,'supervision_evidence_complete':True,'graph_no_physical_publishers':True,'stop_reason':'declared_duration_elapsed','normal_window_complete':True,'window_completion':{'window_started_ns':1,'window_finished_ns':10000000001,'observed_duration_ns':10000000000,'required_duration_ns':10000000000,'normal_window_complete':True,'stop_reason':'declared_duration_elapsed'},**false},
        postrun={'run_id':'run','passed':True,'normal_window_complete':True,**false},base=good_source(),delivery={'run_id':'run','passed':True,'application_delivery_accounting_complete':True,'issues':[]},comparison={'run_id':'run','passed':True,'source_join_verified':True,'issues':[],**false},policy={'run_id':'run','pins':pins},required_paths=['required'],actual_hashes={'required':'a'*64},artifact_hashes={'base_report_sha256':'a'*64},returncodes={'runner':0,'base':0,'delivery':0,'comparison':0},assets_unchanged=True,host_clean=True)

def good():
    a=_good();pins=a['policy']['pins'];pins['boot_id']='5a417cdc-1c7f-4c5c-8186-6d7e9a85ddcb';a['context']['boot_id']=pins['boot_id']
    for k in ('runner_sha256','supervisor_sha256','witness_checker_sha256','base_checker_sha256'):pins[k]='e'*64
    a['context'].update(runner_sha256=pins['runner_sha256'],supervisor_sha256=pins['supervisor_sha256']);a['base']['checker_sha256']=pins['base_checker_sha256']
    a['policy'].update(schema='p1-C0-predeclared-policy-v1',declared_duration_ns=10000000000,mode='no_output',log_capacity=512)
    a['postrun'].update(fixed_witness_check={'requested':True,'passed':True,'witness_complete':True,'issues':[],'report_write_succeeded':True,'checker_sha256':pins['witness_checker_sha256']},normal_source_check={'passed':True,'checker_returncode':0,'contract_report_sha256':'a'*64},window_completion=copy.deepcopy(a['summary']['window_completion']))
    return a

class SourceGate(unittest.TestCase):
    def test_complete_pins_required(self):self.assertTrue(source_gate(good_source(),['required'],{'required':'a'*64})['passed'])
    def test_reader_exception_cannot_preserve_prior_pass(self):
        b=good_source();b['reader_error']='PermissionError';b['issues']=[{'code':'reader_or_source_error'}];self.assertFalse(source_gate(b,['required'],{'required':'a'*64})['passed'])
    def test_missing_after_inventory_even_with_true_flag(self):
        b=good_source();del b['input_sha256_after'];self.assertFalse(source_gate(b,['required'],{'required':'a'*64})['passed'])
    def test_changed_current_file_after_checker_rejected(self):self.assertFalse(source_gate(good_source(),['required'],{'required':'b'*64})['passed'])
    def test_empty_or_missing_required_pins_rejected(self):
        for required in ([],['absent']):self.assertFalse(source_gate(good_source(),required,{'required':'a'*64})['passed'])
    def test_unknown_lifecycle_cannot_join(self):
        b=good_source();b['lifecycle_verified']=None;self.assertFalse(source_gate(b,['required'],{'required':'a'*64})['passed'])
    def test_missing_or_boolean_drop_and_worker_terminal_rejected(self):
        for value in (None,False,1):
            b=good_source();b['regulator_summary']['dropped']=value;self.assertFalse(source_gate(b,['required'],{'required':'a'*64})['passed'])
        b=good_source();b['worker_summary']['fatal']=True;self.assertFalse(source_gate(b,['required'],{'required':'a'*64})['passed'])
    def test_issue_and_input_change_rejected(self):
        b=good_source();b['issues']=[{'code':'late'}];b['input_sha256_after']['required']='b'*64;self.assertFalse(source_gate(b,['required'],{'required':'a'*64})['passed'])

class CombinedGate(unittest.TestCase):
    def test_complete_C0_never_grants_later_gates(self):
        r=combine(**good());self.assertTrue(r['C0_complete']);self.assertFalse(r['R5_complete']);self.assertFalse(r['normal_contract_complete']);self.assertFalse(r['execute_qualified'])
    def test_operator_stop_and_short_window_rejected(self):
        for key,value in (('stop_reason','operator_stop'),('normal_window_complete',False)):
            a=good();a['summary'][key]=value;self.assertFalse(combine(**a)['passed'])
        a=good();a['summary']['window_completion']['observed_duration_ns']=9999999999;self.assertFalse(combine(**a)['passed'])
    def test_nonzero_or_boolean_fault_pause_rejected(self):
        for value in (1,False):
            a=good();a['context']['fixed_witness']['test_sink_pause_ms']=value;self.assertFalse(combine(**a)['passed'])
    def test_identity_and_binary_pin_mismatch_rejected(self):
        a=good();a['delivery']['run_id']='other';self.assertFalse(combine(**a)['passed'])
        a=good();a['context']['binaries']['regulator']['sha256']='e'*64;self.assertFalse(combine(**a)['passed'])
    def test_independent_source_and_witness_results_not_interchangeable(self):
        for item,flag in (('base','passed'),('comparison','source_join_verified'),('delivery','application_delivery_accounting_complete')):
            a=good();a[item][flag]=False;self.assertFalse(combine(**a)['passed'])
    def test_cleanup_host_asset_and_actual_RC_required(self):
        for key in ('assets_unchanged','host_clean'):
            a=good();a[key]=False;self.assertFalse(combine(**a)['passed'])
        a=good();a['summary']['cleanup_complete']=False;self.assertFalse(combine(**a)['passed'])
        a=good();a['returncodes']['runner']=2;self.assertFalse(combine(**a)['passed'])
    def test_source_true_but_reader_unknown_rejected(self):
        a=good();a['base']['reader_error']='OSError';self.assertFalse(combine(**a)['passed'])
    def test_scope_claim_cannot_be_widened(self):
        a=good();a['comparison']['execute_qualified']=True;self.assertFalse(combine(**a)['passed'])
    def test_missing_independent_witness_gate_cannot_pass(self):
        a=good();del a['postrun']['fixed_witness_check'];self.assertFalse(combine(**a)['passed'])
    def test_missing_or_changed_predeclared_dependencies_rejected(self):
        a=good();del a['policy']['pins']['base_checker_sha256'];self.assertFalse(combine(**a)['passed'])
        a=good();a['context']['supervisor_sha256']='f'*64;self.assertFalse(combine(**a)['passed'])
    def test_summary_and_postrun_window_and_report_bytes_must_match(self):
        a=good();a['postrun']['window_completion']['window_finished_ns']+=1;self.assertFalse(combine(**a)['passed'])
        a=good();a['artifact_hashes']['base_report_sha256']='b'*64;self.assertFalse(combine(**a)['passed'])
    def test_missing_base_rejects_without_exception(self):
        a=good();a['base']=None;self.assertFalse(combine(**a)['passed'])
    def test_null_nested_pins_and_normal_reject_without_exception(self):
        for value in (None,[]):
            a=good();a['policy']['pins']=value;self.assertFalse(combine(**a)['passed'])
            a=good();a['postrun']['normal_source_check']=value;self.assertFalse(combine(**a)['passed'])
    def test_absent_hashes_cannot_equal_as_none(self):
        a=good();del a['postrun']['normal_source_check']['contract_report_sha256'];a['artifact_hashes']={'other_sha256':'a'*64};self.assertFalse(combine(**a)['passed'])

if __name__=='__main__':unittest.main()
