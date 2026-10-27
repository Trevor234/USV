#!/usr/bin/env python3
"""Finite diagnostic predicate mutations; these tests are not actual DDS runs."""
from copy import deepcopy
import unittest
import check_c39_worker_close as checker
from test_c37_run_checker import fixture


def negative_row(kind='capability'):
    gid = [1]*15+[1 if kind == 'capability' else 2]
    state = dict(worker_instance='w'*64, worker_valid=False, worker_unusable=True,
        lease_last_valid_ns=15, candidate_present=False, admission_slots=0)
    topic, typ = checker.p.WORKER[kind]
    return dict(type='adapter_worker_callback', interface=kind, topic=topic, message_type=typ,
        callback_sequence=2, received_count=2, entry_ns=70, authentication_checked_ns=71,
        callback_completed_ns=72, processed_ns=72, actual_gid=gid, expected_gid=deepcopy(gid),
        authentication_reason='worker_process_exited', worker_process_alive_at_guard=False,
        later_worker_process_alive=False, resource_valid=True, resource_reason='',
        rmw_implementation_matches_registered=True, from_intra_process=False, raw_input=None,
        full_cdr_serialized=False, semantic_callback_invoked=False,
        before=deepcopy(state), after=deepcopy(state))


class EarlyGuard(unittest.TestCase):
    def check(self, mutation=None, proof=60):
        row = negative_row()
        if mutation: mutation(row)
        return checker.post_exit_rejection(row, [1]*16, proof)

    def test_exact_dead_peer_early_guard(self): self.assertTrue(self.check())

    def test_actual_gid_foreign_or_boolean_rejected(self):
        for gid in ([9]*16, [True]+[1]*15, [1]*15, [0]*16):
            self.assertFalse(self.check(lambda row: row.update(actual_gid=gid)))

    def test_declared_expected_gid_rebinding_rejected(self):
        self.assertFalse(self.check(lambda row: row.update(expected_gid=[9]*16)))

    def test_exit_reason_exact(self):
        for reason in ('', 'callback_foreign_gid', 'worker_peer_missing'):
            self.assertFalse(self.check(lambda row: row.update(authentication_reason=reason)))

    def test_before_exit_proof_and_boolean_times_rejected(self):
        self.assertFalse(self.check(proof=70)); self.assertFalse(self.check(proof=True))
        for key in ('entry_ns', 'authentication_checked_ns', 'callback_completed_ns', 'processed_ns'):
            self.assertFalse(self.check(lambda row: row.update({key: True})))

    def test_unordered_guard_or_nonfinal_completion_rejected(self):
        for change in ({'authentication_checked_ns':69}, {'processed_ns':73}, {'callback_completed_ns':70}):
            self.assertFalse(self.check(lambda row: row.update(change)))

    def test_received_payload_or_semantic_execution_cannot_be_claimed(self):
        for change in ({'raw_input':{}}, {'full_cdr_serialized':True}, {'semantic_callback_invoked':True}):
            self.assertFalse(self.check(lambda row: row.update(change)))

    def test_liveness_and_resource_facts_exact(self):
        for change in ({'worker_process_alive_at_guard':None}, {'later_worker_process_alive':True},
                       {'resource_valid':1}, {'resource_reason':'oversize'},
                       {'rmw_implementation_matches_registered':False}, {'from_intra_process':True}):
            self.assertFalse(self.check(lambda row: row.update(change)))

    def test_each_business_snapshot_mutation_rejected(self):
        replacements = dict(worker_instance='foreign', worker_valid=True, worker_unusable=False,
                            lease_last_valid_ns=16, candidate_present=True, admission_slots=1)
        for key, value in replacements.items():
            self.assertFalse(self.check(lambda row: row['after'].update({key:value})))

    def test_coherent_invalid_snapshot_types_or_shape_rejected(self):
        for key, value in (('worker_valid',1), ('lease_last_valid_ns',True), ('admission_slots',2)):
            def edit(row):
                row['before'][key] = value; row['after'][key] = value
            self.assertFalse(self.check(edit))
        def extra(row):
            row['before']['extra'] = 0; row['after']['extra'] = 0
        self.assertFalse(self.check(extra))


class WholeReceivedPopulation(unittest.TestCase):
    def run_case(self, mutation=None):
        rows, decoded, manifest, messages = fixture()
        for row in rows:
            if row.get('type') == 'adapter_worker_callback':
                row.update(topic=checker.p.WORKER[row['interface']][0],
                    message_type=checker.p.WORKER[row['interface']][1],
                    rmw_implementation_matches_registered=True, from_intra_process=False)
        rows[-2].update(capability_received=2, candidate_received=2,
                        capability_callback_sequence=2, candidate_callback_sequence=2)
        for kind, (topic, typ) in checker.p.WORKER.items():
            rows.insert(-2, negative_row(kind))
            if kind == 'candidate': decoded[topic].append({'message':deepcopy(messages[kind])})
        if mutation: mutation(rows, decoded, manifest, messages)
        c = checker.c36.Checks()
        report, raw = checker.worker_population(rows, decoded, manifest, 60, c,
            decode=lambda raw, label:deepcopy(messages[label['interface']]))
        return c, report, raw

    def test_whole_population_separates_live_CDR_and_no_CDR_denial(self):
        c, report, raw = self.run_case(); self.assertEqual(c.issues, [])
        for kind in checker.p.WORKER:
            self.assertEqual(report[kind]['received'], 2)
            self.assertEqual(report[kind]['live_typed_received'], 1)
            self.assertEqual(len(report[kind]['post_exit_early_rejected']), 1)
            self.assertFalse(report[kind]['complete_received_CDR_population'])
            self.assertIsNone(report[kind]['all_recorded_received'])
            self.assertFalse(report[kind]['rejected_payload_identity_available'])
            self.assertEqual(set(raw[kind]), {1})

    def test_one_interface_denial_absent_rejected(self):
        def edit(rows, decoded, manifest, messages):
            rows[:] = [r for r in rows if not (r.get('interface') == 'candidate'
                and r.get('authentication_reason') == 'worker_process_exited')]
            rows[-2].update(candidate_received=1, candidate_callback_sequence=1)
        c, _, _ = self.run_case(edit)
        self.assertIn('actual_post_exit_callback_on_each_Worker_interface', {r['code'] for r in c.issues})

    def test_receiver_counter_omission_rejected(self):
        c, _, _ = self.run_case(lambda rows, d, m, v:rows[-2].update(candidate_received=1))
        self.assertIn('Worker_native_receiver_terminal_counter_conservation', {r['code'] for r in c.issues})

    def test_illicit_semantic_receipt_for_post_exit_callback_rejected(self):
        def edit(rows, decoded, manifest, messages):
            extra = deepcopy(next(r for r in rows if r.get('type') == 'capability_admission'))
            extra.update(callback_sequence=2, received_count=2)
            rows.insert(-2, extra)
        c, _, _ = self.run_case(edit)
        self.assertIn('exact_live_Worker_semantic_population_excludes_all_post_exit_callbacks',
                      {r['code'] for r in c.issues})

    def test_live_payload_coherent_forgery_still_rejected_by_actual_Storage(self):
        c, _, _ = self.run_case(lambda rows, d, m, v:v['capability'].update(nominal_hash='x'*64))
        self.assertIn('live_received_Worker_full_typed_occurrence_in_Storage', {r['code'] for r in c.issues})

    def test_post_exit_received_count_cannot_exceed_whole_Storage_population(self):
        c, _, _ = self.run_case(lambda rows, d, m, v:d[checker.p.WORKER['candidate'][0]].pop())
        self.assertIn('entire_Worker_received_count_bounded_by_Storage_without_denied_payload_assignment',
                      {r['code'] for r in c.issues})


if __name__ == '__main__': unittest.main()
