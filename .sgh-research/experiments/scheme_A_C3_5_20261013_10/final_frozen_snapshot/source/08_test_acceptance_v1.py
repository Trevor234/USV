import copy,json,os,tempfile,unittest
from pathlib import Path
import acceptance_core_v1 as C
import check_acceptance_v1 as A

class StateQualification(unittest.TestCase):
    def sample(self):
        rules={'raw':{'status':'passed'},'closure':{'status':'passed'},'hard_clock':{'status':'unknown'},
               'stress':{'status':'not_run'},'takeover':{'status':'not_run'}}
        phases={'B4':['closure','stress'],'M0b':['B4','hard_clock'],'B5':['M0b','raw'],'M4':['B5','takeover']}
        return rules,phases
    def test_unknown_is_not_zero_and_missing_run_is_not_failure(self):
        rules,phases=self.sample();r=C.assess(rules,['raw','closure'],phases)
        self.assertTrue(r['component_acceptance_passed']);self.assertEqual(r['stages']['B4']['status'],'not_run')
        self.assertEqual(r['stages']['M0b']['status'],'unknown');self.assertFalse(any(r['qualifications'].values()))
    def test_all_passed_component_rows_still_cannot_qualify_execution_profile(self):
        rules,phases=self.sample()
        for row in rules.values():row['status']='passed'
        r=C.assess(rules,['raw','closure'],phases)
        self.assertTrue(all(s['all_required_passed'] for s in r['stages'].values()))
        self.assertFalse(any(s['qualified'] for s in r['stages'].values()))
    def test_true_false_integer_float_null_cannot_replace_status(self):
        for x in (True,False,0,1,0.0,1.0,None,[],{}):
            with self.subTest(x=x),self.assertRaisesRegex(ValueError,'exact_four_state'):
                C.combine(['passed',x])
    def test_failed_required_result_blocks_components_and_phases(self):
        rules,phases=self.sample();rules['raw']['status']='failed'
        r=C.assess(rules,['raw','closure'],phases)
        self.assertFalse(r['component_acceptance_passed']);self.assertEqual(r['stages']['B5']['status'],'failed')
    def test_missing_required_no_vacuous_promotion(self):
        rules,phases=self.sample()
        for required in ([],['missing'],['raw','raw']):
            with self.subTest(required=required),self.assertRaises(ValueError):C.assess(rules,required,phases)
    def test_missing_phase_forward_or_cycle_rejected(self):
        rules,phases=self.sample();phases['B4']=['M4']
        with self.assertRaisesRegex(ValueError,'forward_phase'):C.assess(rules,['raw'],phases)
    def test_subprocess_nonzero_blocks_forged_success_report(self):
        self.assertEqual(C.report_result({'passed':True},'passed',2),'failed')
        for bad in (1,0,'true',None):
            with self.subTest(bad=bad),self.assertRaises(ValueError):C.report_result({'passed':bad},'passed',0)
    def test_bool_cannot_masquerade_returncode(self):
        with self.assertRaises(ValueError):C.report_result({'passed':True},'passed',False)
    def test_unrecognized_scope_cannot_enable_stage(self):
        rules,phases=self.sample()
        with self.assertRaises(ValueError):C.assess(rules,['raw'],phases,'actual-execute')

class FileIdentity(unittest.TestCase):
    def test_symlink_parent_leaf_and_FIFO_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);original=root/'value.json';original.write_bytes(b'{"value":1}')
            (root/'link').symlink_to(original);(root/'parent').symlink_to(root,target_is_directory=True);os.mkfifo(root/'fifo')
            for p in (root/'link',root/'parent/value.json',root/'fifo'):
                with self.subTest(path=p),self.assertRaises((OSError,ValueError)):C.Reader().raw(p)
    def test_SHA_and_before_after_change_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x';p.write_bytes(b'original');reader=C.Reader();reader.verify({'path':str(p),'sha256':C.digest(b'original')})
            p.write_bytes(b'forged');self.assertFalse(reader.unchanged())
            with self.assertRaises(ValueError):C.Reader().verify({'path':str(p),'sha256':C.digest(b'original')})
    def test_duplicate_nonfinite_overflow_field_rejected(self):
        for raw in (b'{"a":1,"a":2}',b'{"x":NaN}',b'{"x":1e309}',b'{"x":18446744073709551616}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):C.strict_json(raw)
    def test_regular_size_limit_rejects_before_full_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x';p.write_bytes(b'01234')
            with self.assertRaises(ValueError):C.Reader().raw(p,limit=4)

if __name__=='__main__':unittest.main()
