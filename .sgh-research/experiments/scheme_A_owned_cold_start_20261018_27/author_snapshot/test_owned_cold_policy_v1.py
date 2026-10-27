from pathlib import Path
import copy,json,unittest
import cold_start_contract_v1 as contract
from cold_start_policy_audit_v1 import causal_seed_valid,warm_restore_valid
HERE=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text())
class OwnedColdPolicyChecks(unittest.TestCase):
 def setUp(self):
  self.c=read(HERE/'pair_wakeup_contract_v1.json')
  self.candidate=read(HERE.parents[1]/'scheme_A_causal_cold_start_20261018_26/replay/native_causal_cold_v1.json')['candidate']
 def test_contract_only_declared_revision_and_policy_delta(self):
  old=read(HERE.parent/'authored_D1_reference_pair_wakeup_20261018_v22/pair_wakeup_contract_v1.json')
  self.assertEqual({k:v for k,v in self.c.items() if k not in ['diagnostic_contract_revision','cold_start_policy']},{k:v for k,v in old.items() if k!='diagnostic_contract_revision'})
  self.assertEqual(contract.validate(self.c),self.c)
 def test_old_missing_and_foreign_policy_rejected(self):
  for value in [None,'','free_only',False,1]:
   c=copy.deepcopy(self.c)
   if value is None:del c['cold_start_policy']
   else:c['cold_start_policy']=value
   with self.assertRaises(ValueError):contract.validate(c)
 def test_revision_types_unknown_and_numeric_guard_rejected(self):
  for key,value in [('diagnostic_contract_revision',8),('diagnostic_contract_revision',9.0),('deadline_ns',160000000),('reference_start_offset',0.0),('unknown_policy',True)]:
   c=copy.deepcopy(self.c);c[key]=value
   with self.assertRaises(ValueError):contract.validate(c)
 def test_actual_causal_seed_valid(self):
  c=self.candidate;self.assertTrue(causal_seed_valid(c['actual_job'],c['preliminary_free'],c['causal_seed'],self.c['hydro']))
 def test_changed_tail_and_memory_seed_rejected(self):
  c=self.candidate
  for key,index in [('U',4),('X_aug',6),('X_aug',10)]:
   seed=copy.deepcopy(c['causal_seed']);seed[key][index]+=.01
   self.assertFalse(causal_seed_valid(c['actual_job'],c['preliminary_free'],seed,self.c['hydro']))
 def test_actual_one_shift_and_restore_valid(self):
  c=self.candidate;self.assertTrue(warm_restore_valid(c['candidate_final'],c['warm_after_last_shift'],c['warm_after_withdrawal'],c['restored_first_bounds']))
 def test_changed_warm_or_bounds_rejected(self):
  c=self.candidate;warm=copy.deepcopy(c['warm_after_withdrawal']);warm['U'][0]+=.01
  self.assertFalse(warm_restore_valid(c['candidate_final'],c['warm_after_last_shift'],warm,c['restored_first_bounds']))
  bounds=copy.deepcopy(c['restored_first_bounds']);bounds['lbu']=[.5,.5]
  self.assertFalse(warm_restore_valid(c['candidate_final'],c['warm_after_last_shift'],c['warm_after_withdrawal'],bounds))
if __name__=='__main__':unittest.main()
