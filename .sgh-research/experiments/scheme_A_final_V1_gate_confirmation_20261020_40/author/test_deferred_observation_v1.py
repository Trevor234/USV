import copy
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
import contract_identity_v1 as identity
import check_activation_alignment_v1 as audit

HERE=Path(__file__).resolve().parent
DRIVER=HERE.parents[1]/'scheme_A_deferred_observation_20261019_29/verify_and_run_deferred_v1.py'


class DeferredObservation(unittest.TestCase):
    def test_all_actual_identity_consumers_match_before_run(self):
        self.assertTrue(identity.verify_consumers(HERE,DRIVER)['passed'])

    def test_only_one_consumer_left_at_parent_SHA_is_rejected(self):
        for role,path,name in [('producer',HERE/'prepare_pair_wakeup_v1.py','PRODUCER_CONTRACT_SHA'),
                               ('checker',HERE/'check_pair_wakeup_v1.py','PROJECTED_CONTRACT_SHA'),
                               ('driver',DRIVER,'PREREG_CONTRACT_SHA')]:
            text=path.read_text();changed=re.sub(r'^'+name+r'=EXPECTED_CONTRACT_SHA$',name+"='162741dfb9c1454f8e19fbad41c7b96315544819a688029609488c3778eb510f'",text,flags=re.M)
            self.assertNotEqual(text,changed)
            with tempfile.TemporaryDirectory(prefix='deferred-consumer-') as tmp:
                p=Path(tmp)/path.name;p.write_text(changed)
                with self.assertRaises(ValueError):identity.verify_consumers(HERE,DRIVER,{role:(p,name)})

    def test_current_contract_is_parent_exact_bytes(self):
        old=HERE.parent/'authored_D1_activation_alignment_20261019_v28/pair_wakeup_contract_v1.json'
        self.assertEqual(old.read_bytes(),(HERE/'pair_wakeup_contract_v1.json').read_bytes())
        self.assertEqual(hashlib.sha256(old.read_bytes()).hexdigest(),identity.EXPECTED_CONTRACT_SHA)

    def test_unknown_consumer_identity_expression_rejected(self):
        with tempfile.TemporaryDirectory(prefix='deferred-expression-') as tmp:
            p=Path(tmp)/'consumer.py';p.write_text('CONTRACT_SHA=calculate_after_run()\n')
            with self.assertRaises(ValueError):identity.declared_hash(p,'CONTRACT_SHA')

    def trace(self):
        return dict(observation_policy='bounded_values_then_JSON_after_observer_publish_return_v1',
                    decision_commit_ns=100,observer_publish_return_ns=110,materialized_start_ns=130,materialized_end_ns=150)

    def test_deferred_materialization_order(self):
        self.assertTrue(audit.materialization_valid(self.trace(),dict(activation_commit_ns=100,end_ns=120)))

    def test_materialization_before_commit_publish_or_tick_end_rejected(self):
        for key,value in [('decision_commit_ns',99),('observer_publish_return_ns',99),
                           ('materialized_start_ns',105),('materialized_end_ns',129)]:
            trace=self.trace();trace[key]=value
            self.assertFalse(audit.materialization_valid(trace,dict(activation_commit_ns=100,end_ns=120)))

    def test_boolean_cannot_be_materialization_timestamp(self):
        trace=self.trace();trace['materialized_start_ns']=True
        self.assertFalse(audit.materialization_valid(trace,dict(activation_commit_ns=100,end_ns=120)))

    def test_no_new_JSON_conversion_in_activation_method(self):
        source=(HERE/'observer/src/shadow/regulator_shadow_observer.cpp').read_text()
        activation=source.split('  void activate_candidate(',1)[1].split('  void tick_loop()',1)[0]
        for name in ['full_snapshot_json','gate_reads_json','source_json','activation_alignment::json','materialize_activation_trace']:
            self.assertNotIn(name,activation)
        # This source-shape check supplements native branch tests; it is not a
        # latency or algorithmic performance test.


if __name__=='__main__':unittest.main()
