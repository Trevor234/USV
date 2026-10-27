#!/usr/bin/env python3
"""C3.7 checker v2 finite predicates; no DDS or actual-run claims."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import check_c37_owned_run_v2 as checker
from test_c37_run_checker import fixture,WorkerPopulation,WitnessSourcePopulation
import test_c37_run_checker as prior

# Re-run the original finite predicate cases against the versioned new helper;
# prior source/helper/pins remain untouched.
prior.checker=checker


class ContractFlagSource(unittest.TestCase):
    def data(self,directory,flag=True):
        root=Path(directory);(root/'worker').mkdir()
        contract=root/'contract.json';cfg={'fault_injection_enabled':flag,'nominal_hash':'n'*64}
        contract.write_text(json.dumps(cfg,sort_keys=True))
        digest=checker.c36.sha(contract)
        o,d,manifest,messages=fixture()
        manifest.update(contract_configuration=deepcopy(cfg),contract_sha256=digest,
            process_start_ticks=100,effective_parameters={'contract_file':{'type':4,'value':str(contract)},
            'contract_hash':{'type':4,'value':digest}})
        cap=deepcopy(messages['capability']);cap['fault_injection_enabled']=flag;cap['contract_hash']=digest
        mpath=root/'worker/owned_manifest.json';mpath.write_text(json.dumps(manifest,sort_keys=True))
        inputs={'contract':str(contract),'contract_sha256':digest,
            'builds':{'worker':{'binary_sha256':'2'*64}},'source_bundles':{'worker':{'sha256':'3'*64}}}
        ep=manifest['endpoints'][0]
        header=dict(type='capability_source_header',schema='p1-capability-source-header-v1',
            run_id=manifest['run_id'],boot_id=manifest['boot_id'],pid=manifest['pid'],
            process_start_ticks=manifest['process_start_ticks'],worker_instance=manifest['worker_instance'],
            contract_hash=digest,nominal_hash=manifest['nominal_hash'],binary_sha256='2'*64,
            source_bundle_sha256='3'*64,owned_manifest_sha256=checker.c36.sha(mpath),
            clock='CLOCK_MONOTONIC',endpoint=ep,startup_ns=cap['startup_ns'])
        blob=b'finite typed decoder stub; no CDR/network evidence'
        valuehash=checker.capability_digest(cap)
        attempt=dict(type='capability_publish_attempt',schema='p1-capability-publish-attempt-v1',
            publish_seq=1,snapshot_ns=20,attempt_record_ns=21,payload=cap,payload_sha256=valuehash,
            typed_digest_encoding='p1-capability-typed-ieee754-v1',
            cdr={'bytes':len(blob),'hex':blob.hex(),'sha256':hashlib.sha256(blob).hexdigest(),
                'representation':'typed_reserialization_cdr'})
        result=dict(type='capability_publish_result',schema='p1-capability-publish-result-v1',
            publish_seq=1,publish_start_ns=22,publish_end_ns=23,returned=True,threw=False,payload_sha256=valuehash)
        terminal=dict(type='worker_summary',finished_ns=30,source_rows_before_terminal=3,
            source_rows_emitted_before_terminal=3,source_io_failed=False,normal_source_complete=True,
            capability_source=dict(schema='p1-capability-source-terminal-v1',capability_generated=1,
                capability_attempt_records=1,capability_publish_calls=1,capability_publish_returned=1,
                capability_publish_threw=0,capability_result_records=1,capability_aborted_before_publish=0,
                capability_source_io_failed=False,capability_last_publish_seq=1,
                capability_last_payload_sha256=valuehash,capability_last_publish_end_ns=23,
                capability_source_complete=True))
        worker=[header,attempt,result,terminal]
        decoded={checker.WORKER['capability'][0]:[{'message':cap}]}
        return root,inputs,manifest,cap,worker,decoded

    def check(self,flag=True,mutation=None):
        with tempfile.TemporaryDirectory(prefix='c37_checker_contract_') as directory:
            root,inp,m,cap,w,d=self.data(directory,flag)
            if mutation:mutation(root,inp,m,cap,w,d)
            c=checker.c36.Checks()
            checker.worker_contract_configuration(inp,m,c)
            result=checker.worker_publication_population(root,inp,w,[],d,m,c,
                decode=lambda blob,typ:deepcopy(cap))
            return c,result

    def test_contract_permission_true_without_worker_ros_flag_parameter(self):
        c,r=self.check(True);self.assertEqual(c.issues,[]);self.assertTrue(r['passed'])

    def test_contract_permission_false_without_worker_ros_flag_parameter(self):
        c,r=self.check(False);self.assertEqual(c.issues,[]);self.assertTrue(r['passed'])

    def test_contract_flag_wrong_types_and_missing_rejected(self):
        for value in (1,0,'true',None,[],{}):
            c,_=self.check(True,lambda root,i,m,cap,w,d:m['contract_configuration'].update(fault_injection_enabled=value))
            self.assertIn('Worker_fault_permission_exact_contract_boolean',{x['code'] for x in c.issues})
        def missing(root,i,m,cap,w,d):m['contract_configuration'].pop('fault_injection_enabled')
        c,_=self.check(True,missing)
        self.assertIn('Worker_fault_permission_exact_contract_boolean',{x['code'] for x in c.issues})

    def test_worker_ros_flag_parameter_cannot_override_contract(self):
        def edit(root,i,m,cap,w,d):
            m['effective_parameters']['fault_injection_enabled']={'type':1,'value':False}
        c,r=self.check(True,edit);self.assertEqual(c.issues,[]);self.assertTrue(r['passed'])

    def test_full_actual_contract_configuration_mismatch_rejected(self):
        def edit(root,i,m,cap,w,d):m['contract_configuration']['nominal_hash']='x'*64
        c,_=self.check(True,edit)
        self.assertIn('Worker_complete_actual_contract_configuration_binding',{x['code'] for x in c.issues})

    def test_contract_sha_rebinding_rejected(self):
        def edit(root,i,m,cap,w,d):i['contract_sha256']='x'*64
        c,_=self.check(True,edit)
        self.assertIn('Worker_complete_contract_file_manifest_SHA_binding',{x['code'] for x in c.issues})

    def test_contract_parameter_path_rebinding_rejected(self):
        def edit(root,i,m,cap,w,d):m['effective_parameters']['contract_file']['value']='/tmp/other.json'
        c,_=self.check(True,edit)
        self.assertIn('Worker_actual_typed_contract_parameter_source_binding',{x['code'] for x in c.issues})

    def test_published_fault_flag_must_match_contract(self):
        def edit(root,i,m,cap,w,d):cap['fault_injection_enabled']=False
        c,_=self.check(True,edit)
        self.assertIn('Worker_Capability_Source_normal_pinned_contract',{x['code'] for x in c.issues})


if __name__=='__main__':unittest.main()
