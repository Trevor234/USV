"""Pure local tests; no ROS, remote access, process launches or pressure run."""
import copy
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import inspect
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

if importlib.util.find_spec('owned_process_supervisor') is None:
    sys.path.append(str(Path(__file__).resolve().parents[2]/'m0b_contract_implementation_20261007/runtime'))
import run_R5_pressure as r

SHA='a'*64
BOOT='12345678-1234-1234-1234-123456789abc'


def args():
    return SimpleNamespace(contract=Path('contract.json'),contract_hash=SHA,worker_sha256=SHA,regulator_sha256=SHA,
        diagnostic_source_sha256=SHA,diagnostic_bin=Path('p1_regulator_r5_diag'),diagnostic_source=Path('regulator_r5_diag.cpp'),
        test_delay_ms=0,test_native_block_ms=0,test_prepare_block_ms=0,test_tick_block_ms=0,test_sink_pause_ms=5000,
        duration=15.,witness_enabled=True,witness_file=Path('fixed_witness.json'),run_id='r5_unit',experiment_root=Path('/never-create'))


def chains_fixture():
    header={'run_id':'r5_unit','boot_id':BOOT,'contract_sha256':SHA,'worker_instance':'b'*64}
    reg=[];worker=[];typed=[]
    for jid in (1,2):
        t=jid*200
        job={'schema':'p1-solve-job-v1','run_id':header['run_id'],'boot_id':BOOT,'contract_hash':SHA,
             'worker_instance':header['worker_instance'],'nominal_hash':'c'*64,'N':20,'dt':.2,'job_id':jid,
             'target_tick':jid,'task_generation':1,'model_generation':1,'config_generation':1,
             'schedule_generation':1,'clock_epoch':0,'freeze_ns':t+10,'frozen_state':[0]*6}
        decision={'type':'decision','schema':'p1-execution-decision-v2','run_id':header['run_id'],'boot_id':BOOT,
            'contract_hash':SHA,'worker_instance':header['worker_instance'],'mode':'no_output','diagnostic_only':True,
            'accepted':True,'reason':'','job_id':jid,'tick':jid,'sequence':jid+1,
            'task_generation':1,'model_generation':1,'config_generation':1,'schedule_generation':1,'epoch':0,
            'ready_commit_ns':t+90,'activation_commit_ns':t+100}
        reg.extend([{'type':'job','job':copy.deepcopy(job),'submit_commit_ns':t+19,'publish_start_ns':t+20},
                    {'type':'candidate_registration','job':copy.deepcopy(job),'accepted_registration':True,'ready_commit_ns':t+90,
                     'worker_instance':header['worker_instance'],'solve_start_ns':t+40,'solve_end_ns':t+50,'first_control':[0]*2,'reason':''},decision])
        candidate={'type':'candidate','job':copy.deepcopy(job),'worker_instance':header['worker_instance'],
                   'backend':'acados','solver_invoked':True,'success':True,'prediction_available':True,'reason':'',
                   'receive_ns':t+30,'solve_start_ns':t+40,'solve_end_ns':t+50,'publish_start_ns':t+60,
                   'first_control':[0]*2,'X':[0]*126,'U':[0]*40}
        worker.extend([{'type':'job_received','job':copy.deepcopy(job),'receive_ns':t+30,'commit_ns':t+31,'worker_instance':header['worker_instance']},candidate,
            {'type':'candidate_publish_result','job_id':jid,'worker_instance':header['worker_instance'],
             'solve_start_ns':t+40,'solve_end_ns':t+50,'publish_start_ns':t+61,'publish_end_ns':t+62,'success':True}])
        typed.append({**decision,'received_ns':t+101,'clock_epoch':0})
    return header,reg,worker,typed


class PressureRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        self.header,self.reg,self.worker,self.typed=chains_fixture()

    def chains(self):
        return r.accepted_native_chains(self.reg,self.worker,self.header,'c'*64,self.typed,1,1000)

    def test_valid_configuration(self):
        r.validate_pressure_parameters(args())

    def test_fault_hook_type_and_nonzero_rejected_before_mkdir(self):
        for name in ('test_delay_ms','test_native_block_ms','test_prepare_block_ms','test_tick_block_ms'):
            for value in (True,False,1,-1,0.):
                with self.subTest(name=name,value=value):
                    a=args();setattr(a,name,value)
                    with patch.object(Path,'mkdir') as mkdir:
                        with self.assertRaises(ValueError):r.run(a)
                        mkdir.assert_not_called()

    def test_pause_exact_int5000(self):
        for value in (None,True,0,1,4999,5001,5000.):
            a=args();a.test_sink_pause_ms=value
            with self.subTest(value=value),self.assertRaises(ValueError):r.validate_pressure_parameters(a)

    def test_maximum_window_exact15_nonbool_finite(self):
        for value in (True,False,0,10,14.9,15.1,16,float('nan'),float('inf')):
            a=args();a.duration=value
            with self.subTest(value=value),self.assertRaises(ValueError):r.validate_pressure_parameters(a)

    def test_witness_enabled_fixed_owned_filename(self):
        for enabled,path in ((False,Path('fixed_witness.json')),(1,Path('fixed_witness.json')),(True,None),(True,Path('../fixed_witness.json')),(True,Path('/fixed_witness.json'))):
            a=args();a.witness_enabled=enabled;a.witness_file=path
            with self.subTest(enabled=enabled,path=path),self.assertRaises(ValueError):r.validate_pressure_parameters(a)

    def test_all_independent_hashes_required(self):
        for name in ('contract_hash','worker_sha256','regulator_sha256','diagnostic_source_sha256'):
            for value in (None,'A'*64,'x'*64,True):
                a=args();setattr(a,name,value)
                with self.subTest(name=name,value=value),self.assertRaises(ValueError):r.validate_pressure_parameters(a)

    def test_contract_faulttrue_capacity512_required(self):
        for bad in ({'fault_injection_enabled':False,'log_capacity':512},{'fault_injection_enabled':True,'log_capacity':True},{'fault_injection_enabled':True,'log_capacity':513}):
            with patch.object(r,'_base_load_contract',return_value=(bad,SHA)),self.assertRaises(ValueError):r.load_contract(Path('not-read'))
        with patch.object(r,'_base_load_contract',return_value=({'fault_injection_enabled':True,'log_capacity':512},SHA)):
            self.assertEqual(r.load_contract(Path('not-read'))[1],SHA)

    def test_two_real_native_accepted_chains(self):
        result=self.chains();self.assertEqual([x['job_id'] for x in result],[1,2])
        self.assertTrue(all(x['native_solver_invoked'] and x['native_success'] and x['prediction_available'] for x in result))

    def test_only_one_complete_chain_pending_not_ready(self):
        self.worker=[x for x in self.worker if not(x['type']=='candidate_publish_result' and x['job_id']==2)]
        self.assertEqual(len(self.chains()),1)

    def test_uninvoked_or_failed_native_cannot_arm(self):
        for field,value in (('solver_invoked',False),('solver_invoked',1),('success',False),('prediction_available',False),('backend','fake')):
            self.header,self.reg,self.worker,self.typed=chains_fixture()
            next(x for x in self.worker if x['type']=='candidate')[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):self.chains()

    def test_source_typed_acceptance_exact_identity(self):
        for field,value in (('activation_commit_ns',999),('ready_commit_ns',999),('tick',9),('clock_epoch',2),('accepted',False),('reason','shutdown')):
            self.header,self.reg,self.worker,self.typed=chains_fixture();self.typed[0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.chains()

    def test_missing_typed_acceptance_does_not_count_source_only(self):
        self.typed=self.typed[:1];self.assertEqual(len(self.chains()),1)

    def test_duplicate_job_or_accepted_decision_rejected(self):
        self.reg.append(copy.deepcopy(self.reg[0]))
        with self.assertRaises(ValueError):self.chains()
        self.header,self.reg,self.worker,self.typed=chains_fixture();self.reg.append(copy.deepcopy(self.reg[2]))
        with self.assertRaises(ValueError):self.chains()

    def test_foreign_run_job_rejected(self):
        self.reg[0]['job']['run_id']='foreign'
        with self.assertRaises(ValueError):self.chains()

    def test_job_payload_and_version_mismatch_rejected(self):
        self.worker[0]['job']['frozen_state'][0]=1
        with self.assertRaises(ValueError):self.chains()

    def test_job_echo_bool_zero_and_float_integer_types_cannot_compare_equal(self):
        self.worker[0]['job']['frozen_state'][0]=False
        with self.assertRaises(ValueError):self.chains()
        self.header,self.reg,self.worker,self.typed=chains_fixture();self.worker[0]['job']['frozen_state'][0]=0.
        with self.assertRaises(ValueError):self.chains()
        self.header,self.reg,self.worker,self.typed=chains_fixture();self.reg[2]['task_generation']=2
        with self.assertRaises(ValueError):self.chains()

    def test_ready_commit_and_native_chronology_rejected(self):
        self.reg[1]['ready_commit_ns']=999
        with self.assertRaises(ValueError):self.chains()

    def test_native_prediction_shape_and_finite_rejected(self):
        for field,value in (('X',[]),('U',[0]*39),('first_control',[True,0]),('X',[float('nan')]*126)):
            self.header,self.reg,self.worker,self.typed=chains_fixture()
            self.worker[1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.chains()

    def test_candidate_receive_publication_and_typed_future_rejected(self):
        self.worker[1]['receive_ns']+=1
        with self.assertRaises(ValueError):self.chains()
        self.header,self.reg,self.worker,self.typed=chains_fixture();self.worker[2]['publish_end_ns']=1001
        with self.assertRaises(ValueError):self.chains()
        self.header,self.reg,self.worker,self.typed=chains_fixture();self.typed[0]['received_ns']=1001
        with self.assertRaises(ValueError):self.chains()
        self.header,self.reg,self.worker,self.typed=chains_fixture();self.worker[1]['solve_start_ns']=999
        with self.assertRaises(ValueError):self.chains()

    def test_receipt_and_registration_own_worker_identity_required(self):
        for rows,index in (('worker',0),('reg',1)):
            self.header,self.reg,self.worker,self.typed=chains_fixture()
            getattr(self,rows)[index]['worker_instance']='foreign'
            with self.subTest(rows=rows),self.assertRaises(ValueError):self.chains()

    def test_registration_matches_native_result_fields_and_types(self):
        for field,value in (('solve_start_ns',999),('solve_end_ns',250.),('first_control',[1,0]),('ready_commit_ns',290.)):
            self.header,self.reg,self.worker,self.typed=chains_fixture();self.reg[1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.chains()

    def test_candidate_diagnostic_string_and_registration_reason_separate(self):
        for value in (None,False,1,[]):
            self.header,self.reg,self.worker,self.typed=chains_fixture();self.worker[1]['reason']=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.chains()
        self.header,self.reg,self.worker,self.typed=chains_fixture();self.reg[1]['reason']='rejected'
        with self.assertRaises(ValueError):self.chains()

    def test_successful_native_nonempty_diagnostic_can_arm(self):
        self.worker[1]['reason']='native completed with diagnostic detail'
        self.arm_setup();fact=self.arm()
        self.assertEqual(self.messages,[True]);self.assertEqual(len(fact['accepted_chains']),2)
        self.assertEqual(fact['accepted_chains'][0]['worker_candidate']['reason'],'native completed with diagnostic detail')
        self.header,self.reg,self.worker,self.typed=chains_fixture()
        self.worker[1].update(success=False,reason='native completed with diagnostic detail')
        with self.assertRaises(ValueError):self.chains()

    def test_original_delivery_no_argument_entry_preserves_actual_failure(self):
        original_argv=sys.argv;calls=[]
        def original_main():
            calls.append(list(sys.argv))
            output=self.directory/'strict_application_delivery';output.mkdir()
            (output/'resource_delivery_check.json').write_text(json.dumps({'passed':False,'run_id':'r5_unit'}))
            return 2
        module=SimpleNamespace(__file__=str(self.directory/'check_resource_delivery.py'),main=original_main)
        with patch.dict(sys.modules,{'check_resource_delivery':module}):result=r.terminal_application_delivery(self.directory)
        self.assertIs(sys.argv,original_argv);self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][1:],[str(self.directory),'--base-report',str(self.directory/'normal_source_check/contract_report.json'),'--output',str(self.directory/'strict_application_delivery')])
        self.assertEqual(result['checker_returncode'],2);self.assertFalse(result['passed'])
        self.assertEqual(result['report_sha256'],r.sha256_file(self.directory/result['report_relative_path']))

    def test_delivery_entry_exception_restores_argv_and_records_unknown_rc(self):
        original_argv=sys.argv
        def original_main():raise OSError('actual reader failure')
        module=SimpleNamespace(__file__=str(self.directory/'check_resource_delivery.py'),main=original_main)
        with patch.dict(sys.modules,{'check_resource_delivery':module}):result=r.terminal_application_delivery(self.directory)
        self.assertIs(sys.argv,original_argv);self.assertIsNone(result['checker_returncode']);self.assertFalse(result['passed'])
        self.assertEqual(json.loads((self.directory/'strict_application_delivery_error.json').read_text()),result)

    def test_receipt_commit_and_typed_receipt_cannot_precede_real_commit(self):
        for value in (-1,False,229,241):
            self.header,self.reg,self.worker,self.typed=chains_fixture();self.worker[0]['commit_ns']=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.chains()
        self.header,self.reg,self.worker,self.typed=chains_fixture();self.typed[0]['received_ns']=299
        with self.assertRaises(ValueError):self.chains()

    def test_prefix_reads_completed_lines_only_without_forcing_flush(self):
        p=self.directory/'source.jsonl';p.write_bytes(b'{"type":"job"}\n{"type":')
        rows,pin=r.read_complete_prefix(p)
        self.assertEqual(rows,[{'type':'job'}]);self.assertEqual(pin['complete_bytes'],15)
        self.assertEqual(pin['tail_bytes'],8);self.assertEqual(pin['sha256'],hashlib.sha256(b'{"type":"job"}\n').hexdigest())
        self.assertEqual(p.read_bytes(),b'{"type":"job"}\n{"type":')

    def test_absent_unflushed_prefix_is_pending_empty(self):
        self.assertEqual(r.read_complete_prefix(self.directory/'absent')[0],[])
        p=self.directory/'source';p.write_bytes(b'{"type":')
        rows,pin=r.read_complete_prefix(p);self.assertEqual(rows,[]);self.assertEqual(pin['complete_bytes'],0)

    def test_malformed_complete_prefix_is_error(self):
        for raw in (b'{bad}\n',b'{"type":"a","type":"b"}\n',b'{"type":"x","value":1e999}\n',b'{"type":"x","value":NaN}\n',b'\xff\n'):
            p=self.directory/'source';p.write_bytes(raw)
            with self.subTest(raw=raw),self.assertRaises((ValueError,UnicodeError)):r.read_complete_prefix(p)

    def arm_setup(self):
        self.publisher=SimpleNamespace(publish=lambda message: self.messages.append(message.data))
        self.messages=[];self.events=[];self.supervisor=SimpleNamespace(evidence_failed=False,event=lambda kind,**details:self.events.append((kind,details)))
        self.state={'attempted':False};self.context={'run_id':'r5_unit','boot_id':BOOT,'contract_sha256':SHA}
        self.times=iter((1000,1001,1002))

    def arm(self,chains=None):
        return r.publish_pressure_arm(self.publisher,SimpleNamespace,self.state,self.directory,self.supervisor,
                                      self.context,{},self.chains() if chains is None else chains,{},clock=lambda:next(self.times))

    def test_arm_exactly_once_with_persisted_intent_then_publication(self):
        self.arm_setup();fact=self.arm()
        self.assertEqual(self.messages,[True]);self.assertEqual(fact['arm_attempts'],1)
        self.assertEqual((fact['publish_start_ns'],fact['publish_end_ns']),(1001,1002))
        self.assertTrue((self.directory/'pressure_arm_intent.json').exists())
        self.assertEqual(json.loads((self.directory/'pressure_arm.json').read_text()),fact)
        self.assertFalse(fact['R5_complete']);self.assertFalse(fact['arm_sink_acceptance_known'])
        with self.assertRaises(RuntimeError):self.arm()
        self.assertEqual(self.messages,[True])

    def test_insufficient_chain_does_not_publish(self):
        self.arm_setup()
        with self.assertRaises(RuntimeError):self.arm(self.chains()[:1])
        self.assertEqual(self.messages,[]);self.assertFalse(self.state['attempted'])

    def test_duplicate_chains_cannot_arm(self):
        self.arm_setup();chain=self.chains()[0]
        with self.assertRaises(RuntimeError):self.arm([chain,chain])
        self.assertEqual(self.messages,[]);self.assertFalse(self.state['attempted'])

    def test_intent_persistence_failure_does_not_publish_or_retry(self):
        self.arm_setup();self.supervisor.evidence_failed=True
        with self.assertRaises(RuntimeError):self.arm()
        self.assertEqual(self.messages,[]);self.assertTrue(self.state['attempted'])

    def test_publish_exception_keeps_single_attempt_no_success_fact(self):
        self.arm_setup();self.publisher.publish=lambda message:(_ for _ in ()).throw(RuntimeError('publish failed'))
        with self.assertRaises(RuntimeError):self.arm()
        self.assertTrue(self.state['attempted']);self.assertNotIn('fact',self.state)
        self.assertFalse((self.directory/'pressure_arm.json').exists())

    def test_arm_output_create_only_no_publish_if_preexisting_intent(self):
        self.arm_setup();(self.directory/'pressure_arm_intent.json').write_text('{}')
        with self.assertRaises(FileExistsError):self.arm()
        self.assertEqual(self.messages,[])

    def test_pressure_window_is_maximum_not_normal_elapsed_success(self):
        result=r.pressure_window_completion({'started_ns':10},'expected_sink_failure_exit',20)
        self.assertTrue(result['pressure_window_bounded']);self.assertFalse(result['normal_window_complete']);self.assertFalse(result['R5_complete'])
        self.assertEqual(result['window_origin'],'arm_publish_start_ns')
        self.assertFalse(r.pressure_window_completion({'started_ns':10},'pressure_window_max_elapsed',10+r.MAX_PRESSURE_NS+1)['pressure_window_bounded'])
        self.assertFalse(r.pressure_window_completion({'started_ns':True},'expected_sink_failure_exit',20)['pressure_window_bounded'])

    def test_collection_never_uses_normal_report_as_mechanism_success(self):
        summary={'failure':None,'cleanup_complete':True,'supervision_evidence_complete':True,'graph_no_physical_publishers':True,
                 'pressure_arm':{'publish_success':True,'arm_attempts':1},'stop_reason':'expected_sink_failure_exit',
                 'actual_returncodes':{'regulator':2},'window_completion':{'pressure_window_bounded':True}}
        audit={'passed':True,'report_write_succeeded':True}
        self.assertTrue(r.pressure_collection_complete(summary,audit))
        for field,value in (('cleanup_complete',False),('failure','x'),('stop_reason','operator_stop'),('graph_no_physical_publishers',False)):
            changed=copy.deepcopy(summary);changed[field]=value
            with self.subTest(field=field):self.assertFalse(r.pressure_collection_complete(changed,audit))
        for code in (0,1,-15,True,None):
            changed=copy.deepcopy(summary);changed['actual_returncodes']['regulator']=code
            self.assertFalse(r.pressure_collection_complete(changed,audit))

    def test_diagnostic_command_contains_only_declared_pause_and_no_physical_mode(self):
        a=args();b={'regulator':{'path':'/diag/p1_regulator_r5_diag','sha256':SHA},'worker':{'sha256':SHA}}
        command=r.diagnostic_regulator_command(a,[],123,{'regulator':Path('/run/regulator_source.jsonl')},b,
            Path('/diag/regulator_r5_diag.cpp'),SHA,Path('/run/fixed_witness.json'),'b'*64)
        self.assertIn('mode:=no_output',command);self.assertIn('test_sink_pause_ms:=5000',command)
        self.assertIn('test_prepare_block_ms:=0',command);self.assertIn('test_tick_block_ms:=0',command)
        self.assertNotIn('mode:=execute',command)

    def test_cli_nonzero_unrelated_fault_rejected_before_run(self):
        cli=['--contract','c','--contract-hash',SHA,'--worker-sha256',SHA,'--regulator-sha256',SHA,'--diagnostic-source-sha256',SHA,
             '--diagnostic-bin','bin','--diagnostic-source','src','--experiment-root','root','--run-id','r5_unit',
             '--duration','15','--test-sink-pause-ms','5000','--witness-enabled','--witness-file','fixed_witness.json']
        with patch.object(r,'run') as run,contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):r.main(cli+['--test-tick-block-ms','1'])
            run.assert_not_called()
            run.return_value=0;self.assertEqual(r.main(cli),0);run.assert_called_once()

    def test_internal_fixture_rejects_pressure_options(self):
        with patch.object(r,'fixture_child') as fixture,contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):r.main(['--fixture-child','--contract','c','--contract-hash',SHA,'--fixture-source','s','--test-sink-pause-ms','5000'])
            fixture.assert_not_called()

    def test_only_main_guard_runs_after_pressure_helpers_and_derived_run(self):
        tree=ast.parse(Path(r.__file__).read_text(encoding='utf-8'))
        guards=[n for n in tree.body if isinstance(n,ast.If) and '__name__' in ast.unparse(n.test)]
        mains=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main']
        self.assertEqual(len(guards),1);self.assertGreater(guards[0].lineno,mains[-1].end_lineno)
        self.assertIs(r.validate_normal_parameters,r.validate_pressure_parameters)
        self.assertIs(r.normal_window_completion,r.pressure_window_completion)
        body=inspect.getsource(r.run)
        self.assertIn('publish_pressure_arm(',body);self.assertIn('expected_sink_failure_exit',body)
        self.assertIn('pressure_collection_complete(',body)
        self.assertEqual(Path(r.run.__globals__['__file__']).resolve(),Path(r.__file__).resolve())
        self.assertIn('"runner_sha256": sha256_file(Path(__file__))',body)

    def test_frozen_baseline_byte_identity(self):
        spec=importlib.util.find_spec('run_r5_diag_validation')
        path=Path(spec.origin) if spec and spec.origin else Path(__file__).resolve().parents[2]/'m0b_witness_implementation_20261007/runtime/run_r5_diag_validation.py'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),r.BASE_RUNNER_SHA256)


if __name__=='__main__':unittest.main()
