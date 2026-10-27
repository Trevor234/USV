#!/usr/bin/env python3
"""Finite diagnostic predicate mutations; these tests are not actual DDS runs."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
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


class QueuedPublicationOrder(unittest.TestCase):
    def check(self, mutation=None):
        pub = {'publish_start_ns': 10, 'publish_end_ns': 20}
        close = {'requested_ns': 30, 'read_completed_ns': 40, 'observed_ns': 50}
        if mutation: mutation(pub, close)
        return checker.publication_before_close(pub, 25, close)

    def test_completed_publication_before_request(self): self.assertTrue(self.check())

    def test_call_after_request_before_signal_still_rejected(self):
        self.assertFalse(self.check(lambda pub, close:pub.update(publish_end_ns=35)))

    def test_unordered_request_read_observation_rejected(self):
        for values in ({'requested_ns':41}, {'read_completed_ns':24}, {'observed_ns':39}):
            self.assertFalse(self.check(lambda pub, close:close.update(values)))

    def test_boolean_and_missing_time_rejected(self):
        self.assertFalse(self.check(lambda pub, close:pub.update(publish_end_ns=True)))
        self.assertFalse(self.check(lambda pub, close:close.pop('read_completed_ns')))

    def test_unordered_publication_call_rejected(self):
        self.assertFalse(self.check(lambda pub, close:pub.update(publish_start_ns=21)))

    def test_driver_checked_point_before_call_end_rejected(self):
        pub = {'publish_start_ns':10, 'publish_end_ns':20}
        close = {'requested_ns':30, 'read_completed_ns':40, 'observed_ns':50}
        self.assertFalse(checker.publication_before_close(pub, 19, close))


class CurrentAdapterConfiguration(unittest.TestCase):
    def data(self):
        run = Path('/tmp/finite-C39-current-run')
        pub = {k:'finite-'+k for k in ('run_id', 'boot_id', 'contract_sha256', 'producer_instance_id',
            'config_hash', 'exe', 'binary_sha256', 'source_bundle_sha256', 'effective_parameters_sha256')}
        pub.update(pid=1, process_start_ticks=2)
        params = {'mode':'shadow', 'adapter_peer_pins_file':str(run/'adapter_peer_pins.json'),
            'adapter_peer_pins_sha256':'a'*64, 'adapter_driver_close_file':str(run/'adapter_driver_close_request.json'),
            'diagnostic_c38_mode':'worker-gate', 'diagnostic_c38_pause_file':str(run/'c38_pause_request.json'),
            'diagnostic_c38_resume_file':str(run/'c38_resume_request.json')}
        obs = {'adapter_pins_sha256':'a'*64,
            'effective_parameters':{k:{'value':value} for k,value in params.items()}}
        peer = {'publisher_peer':dict(pub, manifest_path=str(run/'publisher/owned_manifest.json'),
                manifest_sha256='b'*64, topic=checker.c36.APPLIED, type=checker.c36.APPLIED_TYPE)}
        return run, obs, pub, peer

    def check(self, mutation=None):
        run, obs, pub, peer = self.data()
        if mutation: mutation(obs, pub, peer)
        return checker.current_adapter_bindings(run, obs, pub, peer, 'a'*64, 'b'*64)

    def test_current_concrete_pins_pass(self): self.assertTrue(self.check())

    def test_matching_declared_parameters_cannot_rebind_other_run_paths_or_mode(self):
        for key, value in (('adapter_peer_pins_file','/tmp/another-run/adapter_peer_pins.json'),
                          ('adapter_driver_close_file','/tmp/other-close.json'),
                          ('diagnostic_c38_pause_file','/tmp/other-pause.json'),
                          ('diagnostic_c38_resume_file','/tmp/other-resume.json'),
                          ('diagnostic_c38_mode','applied-gate'), ('adapter_peer_pins_sha256','c'*64)):
            self.assertFalse(self.check(lambda obs,pub,peer:obs['effective_parameters'][key].update(value=value)))

    def test_native_peer_sha_and_complete_publisher_process_asset_pins_exact(self):
        self.assertFalse(self.check(lambda obs,pub,peer:obs.update(adapter_pins_sha256='c'*64)))
        for key in ('pid','process_start_ticks','exe','binary_sha256','source_bundle_sha256',
                    'effective_parameters_sha256','manifest_sha256','manifest_path'):
            self.assertFalse(self.check(lambda obs,pub,peer:peer['publisher_peer'].update({key:'rebound'})))
        self.assertFalse(self.check(lambda obs,pub,peer:peer['publisher_peer'].update(extra='unregistered')))


class RoleAssetAndSupervisorPins(unittest.TestCase):
    def data(self, root):
        inputs = {'run_id':'finite-C39', 'builds':{}, 'source_bundles':{}}
        result = {'cleanup':{}}; manifests = {}; prep = {'schema_version':'p1-owned-fixture-preparation-v2',
            'fixture_only':True, 'production_execute_qualified':False, 'checked_ns':30, 'roles':{}}
        ledger = []
        for ordinal, role in enumerate(sorted(checker.c36.ROLES), 1):
            source_role = 'fixture' if role == 'synthetic_source' else role
            binary = str(root/'binary'/role); binary_sha = str(ordinal)*64; source_sha = 's'+str(ordinal)*63
            inputs['builds'][source_role] = {'binary':binary, 'binary_sha256':binary_sha,
                                          'source_bundle':{'sha256':source_sha}}
            inputs['source_bundles'][source_role] = {'sha256':source_sha}
            m = dict(exe=binary, binary_sha256=binary_sha, source_bundle_sha256=source_sha,
                     effective_parameters_sha256='e'*64, pid=ordinal, process_start_ticks=ordinal+10,
                     boot_id='finite-boot', run_id='finite-C39'+('-publisher' if role == 'publisher' else ''))
            manifests[role] = m
            (root/role).mkdir(); path = root/role/'owned_manifest.json'; path.write_text(json.dumps(m))
            owned = dict(exe=binary, exe_sha256=binary_sha, pid=ordinal, start_ticks=ordinal+10,
                         boot_id='finite-boot', pgid=ordinal, sid=ordinal, argv=[binary])
            prep['roles'][role] = {'owned':owned, 'manifest_sha256':checker.c36.sha(path),
                                  'source_bundle_sha256':source_sha, 'effective_parameters_sha256':'e'*64}
            ident = {k:v for k,v in owned.items() if k not in ('argv','boot_id')}
            ledger.append(dict(type='spawn', name=role, identity=ident, argv=[binary], boot_id='finite-boot',
                executable_verified=True, expected_exe=binary, expected_sha256=binary_sha, monotonic_ns=20))
            ledger.append(dict(type='signal', name=role, signal=2, boot_id='finite-boot', members=[ident]))
            cleanup = dict(name=role, cleanup_complete=True, qualification_clean=True,
                           remaining_members=[], resource_cleanup_complete=True, returncode=0, unexpected_descendants=[])
            result['cleanup'][role] = cleanup
            ledger.append(dict(cleanup, type='cleanup_result', boot_id='finite-boot', monotonic_ns=40))
        ledger.append(dict(type='supervisor_summary', children=deepcopy(result['cleanup']), cleanup_failed=False,
                           qualification_clean=True, unexpected_descendants=[], unverified_children=[]))
        return inputs, result, manifests, prep, ledger

    def check(self, mutation=None):
        with tempfile.TemporaryDirectory(prefix='finite-C39-pins-') as directory:
            root = Path(directory); inputs, result, manifests, prep, ledger = self.data(root)
            if mutation: mutation(inputs, result, manifests, prep, ledger)
            c = checker.c36.Checks()
            checker.role_pin_population(root, inputs, result, manifests, prep, ledger, c)
            return {r['code'] for r in c.issues}

    def test_same_run_native_assets_preparation_and_supervision_pass(self): self.assertEqual(self.check(), set())

    def test_native_manifest_rebinding_to_different_asset_rejected(self):
        for key in ('exe','binary_sha256','source_bundle_sha256'):
            issues = self.check(lambda i,r,m,p,l:m['worker'].update({key:'rebound'}))
            self.assertIn('native_role_manifest_exact_current_asset_and_process_binding', issues)

    def test_fixture_role_requires_fixture_asset_mapping(self):
        issues = self.check(lambda i,r,m,p,l:i['builds']['fixture'].update(binary='other'))
        self.assertIn('native_role_manifest_exact_current_asset_and_process_binding', issues)

    def test_live_preparation_process_or_manifest_rebinding_rejected(self):
        issues = self.check(lambda i,r,m,p,l:p['roles']['worker']['owned'].update(start_ticks=999))
        self.assertIn('live_preparation_authentication_exact_supervisor_spawn_identity_and_argv', issues)
        issues = self.check(lambda i,r,m,p,l:p['roles']['worker'].update(manifest_sha256='f'*64))
        self.assertIn('live_preparation_authentication_exact_supervisor_spawn_identity_and_argv', issues)

    def test_spawn_and_signal_target_rebinding_rejected(self):
        def edit(i,r,m,p,l):
            next(x for x in l if x['type']=='spawn' and x['name']=='worker')['identity']['pid']=999
        issues = self.check(edit)
        self.assertIn('live_preparation_authentication_exact_supervisor_spawn_identity_and_argv', issues)

    def test_cleanup_and_full_summary_omission_rejected(self):
        def edit(i,r,m,p,l):
            next(x for x in l if x['type']=='cleanup_result' and x['name']=='worker')['returncode']=9
            l[-1]['children'].pop('worker')
        issues = self.check(edit)
        self.assertIn('supervisor_cleanup_matches_complete_driver_cleanup_and_live_role', issues)
        self.assertIn('entire_supervisor_terminal_population_and_cleanup_conservation', issues)


if __name__ == '__main__': unittest.main()
