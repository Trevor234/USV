#!/usr/bin/env python3
from pathlib import Path
import copy
import json
import unittest
from runner_verdict_v2 import baseline_verdict, mutation_verdict, complete_verdict

ROOT = Path(__file__).resolve().parents[1]
B68 = ROOT.parent / 'scheme_A_M4_t1_component_wiring_20261024_68'


def document(failed=False):
    row = {'name': 'Case', 'status': 'RUN', 'result': 'COMPLETED'}
    if failed:
        row['failures'] = [{'failure': 'Expected: current Job2 registration; actual: absent'}]
    return {'tests': 1, 'failures': int(failed), 'errors': 0, 'disabled': 0,
            'testsuites': [{'name': 'T', 'testsuite': [row]}]}


class VerdictTests(unittest.TestCase):
    def test_actual_original_baseline_is_accepted(self):
        verification = json.loads((B68 / 'evidence/t1_wiring/verification_v1.json').read_text())
        doc = json.loads((Path(verification['nominal_run']['run_dir']) / 'gtest.json').read_text())
        expected = list(verification['nominal_run']['results'])
        self.assertEqual(len(baseline_verdict(doc, 0, expected)), 25)

    def test_actual_original_three_assertion_mutations_are_accepted(self):
        verification = json.loads((B68 / 'evidence/t1_wiring/verification_v1.json').read_text())
        expected = list(verification['nominal_run']['results'])
        for row in verification['mutations']:
            with self.subTest(name=row['name']):
                doc = json.loads((Path(row['run_dir']) / 'gtest.json').read_text())
                self.assertTrue(mutation_verdict(doc, 1, expected, row['expected_subset'], True, 0))

    def test_RUN_with_assertion_failure_is_not_a_pass(self):
        with self.assertRaises(AssertionError):
            baseline_verdict(document(True), 1, ['T.Case'])

    def test_skipped_RUN_is_not_a_pass(self):
        doc = document()
        doc['testsuites'][0]['testsuite'][0]['result'] = 'SKIPPED'
        with self.assertRaises(AssertionError):
            baseline_verdict(doc, 0, ['T.Case'])

    def test_missing_case_is_not_a_pass(self):
        with self.assertRaises(AssertionError):
            baseline_verdict(document(), 0, ['T.Case', 'T.Other'])

    def test_duplicate_names_are_rejected(self):
        doc = document()
        doc['testsuites'][0]['testsuite'].append(copy.deepcopy(doc['testsuites'][0]['testsuite'][0]))
        doc['tests'] = 2
        with self.assertRaises(AssertionError):
            baseline_verdict(doc, 0, ['T.Case'])

    def test_assertion_JSON_with_zero_process_return_is_not_a_mutation_catch(self):
        with self.assertRaises(AssertionError):
            mutation_verdict(document(True), 0, ['T.Case'], ['T.Case'], True, 0)

    def test_signal_exit_is_not_an_assertion_catch(self):
        with self.assertRaises(AssertionError):
            mutation_verdict(document(True), -11, ['T.Case'], ['T.Case'], True, 0)

    def test_shorter_prefix_is_not_the_named_assertion(self):
        with self.assertRaises(AssertionError):
            mutation_verdict(document(True), 1, ['T.Case'], ['T.CaseSuffix'], True, 0)

    def test_unprepared_mutation_is_rejected(self):
        with self.assertRaises(AssertionError):
            mutation_verdict(document(True), 1, ['T.Case'], ['T.Case'], False, 0)

    def test_build_error_is_not_a_mutation_catch(self):
        with self.assertRaises(AssertionError):
            mutation_verdict(document(True), 1, ['T.Case'], ['T.Case'], True, 2)

    def test_empty_mutation_population_cannot_complete(self):
        with self.assertRaises(AssertionError):
            complete_verdict(True, [], ['M1', 'M2', 'M3'], True)

    def test_uncaught_mutation_blocks_complete(self):
        with self.assertRaises(AssertionError):
            complete_verdict(True, [{'name': 'M1', 'prepared': True, 'assertion_caught': False}], ['M1'], True)

    def test_identity_change_blocks_complete(self):
        with self.assertRaises(AssertionError):
            complete_verdict(True, [{'name': 'M1', 'prepared': True, 'assertion_caught': True}], ['M1'], False)

    def test_case_failures_cannot_be_hidden_by_top_level_zero(self):
        doc = document(True)
        doc['failures'] = 0
        with self.assertRaises(AssertionError):
            mutation_verdict(doc, 1, ['T.Case'], ['T.Case'], True, 0)

    def test_missing_JSON_is_not_a_rejection_success(self):
        with self.assertRaises(AssertionError):
            mutation_verdict(None, 1, ['T.Case'], ['T.Case'], True, 0)

    def test_valid_aggregate_completes(self):
        self.assertTrue(complete_verdict(True,
            [{'name': 'M1', 'prepared': True, 'assertion_caught': True}], ['M1'], True))


if __name__ == '__main__':
    output = ROOT / 'evidence/verdict_tests'
    output.mkdir()
    with (output / 'unittest.log').open('x') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(VerdictTests))
    report = {'schema': 'T1-reviewed-runner-verdict-tests-v69', 'tests': result.testsRun,
              'failures': [{'test': str(test), 'traceback': trace} for test, trace in result.failures],
              'errors': [{'test': str(test), 'traceback': trace} for test, trace in result.errors],
              'passed': result.wasSuccessful(), 'ROS_initialized': False}
    with (output / 'verification_v1.json').open('x') as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if result.wasSuccessful() else 2)
