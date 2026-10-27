#!/usr/bin/env python3
"""Read-only diagnosis of the frozen failed case; no gate or report rewriting."""
import hashlib
import json
from collections import Counter
from pathlib import Path

D = Path(__file__).resolve().parent
N = D.parent / 'p1_execution_architecture_20261005_01/authored_D1_owned_cold_start_20261018_v27'
R = N / 'runs/owned_cold_s005_01'
OUT = D / 'postrun/activation_refusal_audit_v1.json'


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def main():
    report_path = D / 'runs/s005_01/check_result.json'
    report = load(report_path)
    require(report['passed'] is False and len(report['issues']) == 6, 'preserve_actual_NoGo')
    require(report['input_sha256_before'] == report['input_sha256_after'], 'original_reader_read_only')
    inputs = dict(report['input_sha256_after'])
    for p in [report_path, R / 'result.json', N / 'pair_wakeup_contract_v1.json',
              D / 'preregister/owned_cold_v1.json', R / 'publisher/controlled_source.jsonl',
              R / 'worker/source.jsonl', R / 'observer/source.jsonl',
              N / 'observer/src/shadow/regulator_shadow_observer.cpp',
              N / 'observer/src/shadow/p1_input_core.cpp']:
        if p.exists():
            inputs[str(p)] = sha(p)
    before = {p: sha(p) for p in inputs}
    require(before == inputs, 'frozen_reader_input_changed')
    observer = lines(R / 'observer/source.jsonl')
    worker = lines(R / 'worker/source.jsonl')
    publisher = lines(R / 'publisher/controlled_source.jsonl')
    contract = load(N / 'pair_wakeup_contract_v1.json')
    result = load(R / 'result.json')
    start = report['window']['start_ready_ns']
    end = report['window']['end_driver_requested_ns']
    decisions = [r for r in observer if r.get('type') == 'decision' and
                 r.get('job_id', 0) > 0 and start <= r['activation_commit_ns'] < end]
    rejected = [r for r in decisions if not r['accepted']]
    candidates = {r['job']['job_id']: r for r in worker if r.get('type') == 'candidate'}
    policies = [r for r in worker if r.get('type') == 'cold_start_policy_result']
    require(len(decisions) == 100 and len(rejected) == 10, 'entire_measurement_attempts')
    require(len(candidates) == len(policies) == 101, 'entire_native_population')
    require(all(r['metadata']['backend_entries_completed'] == (4 if r['job_id'] == 1 else 1)
                and r['metadata']['candidate_applied'] == (r['job_id'] == 1)
                and r['metadata']['successful'] and not r['metadata']['terminal'] for r in policies),
            'exact_once_internal_policy_and_no_native_failures')
    odom = [r for r in observer if r.get('type') == 'odom_admission' and r['valid']]
    for r in odom:
        raw = r['raw_input']
        data = bytes.fromhex(raw['cdr_hex'])
        require(len(data) == raw['cdr_bytes'] and hashlib.sha256(data).hexdigest() == raw['cdr_sha256'],
                'historical_odom_full_cdr_integrity')
    rows = []
    for d in rejected:
        jid = d['job_id']
        source = d['d0_observation']
        s, final = source['validation_snapshot'], source['final_snapshot']
        candidate = candidates[jid]
        target = candidate['job']['target_sim_ns']
        row = dict(job_id=jid, reason=d['reason'], predict_status=source['predict_status'],
                   candidate_registered_before_activation=True,
                   ready_margin_ms=(d['planned_ns'] - d['ready_commit_ns']) / 1e6,
                   native_total_ms=(candidate['solve_end_ns'] - candidate['solve_start_ns']) / 1e6,
                   target_minus_latest_odom_ns=target - s['odom_stamp_ns'],
                   validation_r_from_imu=s['r_from_imu'], final_r_from_imu=final['r_from_imu'],
                   validation_odom_sequence=s['odom_sequence'], final_odom_sequence=final['odom_sequence'],
                   validation_imu_sequence=s['imu_sequence'], final_imu_sequence=final['imu_sequence'],
                   validation_copy_to_activation_commit_ns=d['activation_commit_ns'] - s['copy_capture_ns'],
                   validation_snapshot_capture_ns=s['copy_capture_ns'],
                   activation_commit_ns=d['activation_commit_ns'],
                   version_unchanged=s['version'] == final['version'],
                   gate_reads=source['gate_reads'])
        require(d['ready_commit_ns'] < candidate['job']['deadline_ns'] < d['planned_ns'],
                'rejected_candidate_ready_before_original_cutoff')
        if d['reason'] == 'activation_history_or_time':
            require(target < s['odom_stamp_ns'] and not s['r_from_imu'] and
                    source['predict_status'] == 'history_or_time_failed', 'negative_horizon_evidence')
            # A source existed at the capture. This does not prove a new runtime
            # selection algorithm, admission, prediction error or atomic commit.
            eligible = [o for o in odom if o['input_commit_ordinal'] <= s['input_commit_ordinal']
                        and o['receive_ns'] <= s['copy_capture_ns'] and o['stamp_ns'] <= target]
            require(bool(eligible), 'older_received_causal_odom_exists')
            old = max(eligible, key=lambda o: (o['stamp_ns'], o['input_commit_ordinal']))
            channels = {e['channel'] for e in s['held_history'] if e['sim_ns'] <= old['stamp_ns']}
            receipt_age = s['sample_ns'] - old['receive_ns']
            row['historical_odom_availability_only'] = dict(
                accepted_sequence=old['accepted_sequence'], input_commit_ordinal=old['input_commit_ordinal'],
                sim_stamp_ns=old['stamp_ns'], receive_ns=old['receive_ns'],
                full_cdr_sha256=old['raw_input']['cdr_sha256'], state=old['state'],
                target_forward_horizon_ns=target - old['stamp_ns'],
                capture_receipt_age_ns=receipt_age,
                within_original_odom_receipt_age=0 <= receipt_age <= contract['odom_age_ns'],
                history_has_both_initial_channels=channels == {0, 1},
                current_snapshot_history_count=len(s['held_history']),
                actual_runtime_selected_this_point=False, qualification_claimed=False)
        elif d['reason'] == 'activation_input_changed_during_validation':
            require(source['predict_success'] and source['input_change_gate_ran'] and
                    source['input_change_gate_unchanged'] is False, 'optimistic_snapshot_race_detected')
        else:
            raise RuntimeError('unexpected_refusal_category:' + d['reason'])
        rows.append(row)

    retries = []
    versions = {kind: [x for x in observer if x.get('type') == kind + '_version']
                for kind in ['path', 'profile']}
    for r in [x for x in observer if x.get('type') == 'reference_pair_retry']:
        trigger = r['trigger']
        opposite = 'path' if trigger == 'profile' else 'profile'
        triggering = [x for x in versions[trigger] if x['input_commit_ordinal'] == r['input_commit_ordinal']
                      and x['received_sequence'] == r[trigger + '_sequence'] and x['valid']]
        require(len(triggering) == 1 and triggering[0]['processed_ns'] <= r['started_ns'] <= r['completed_ns'],
                'retry_actual_valid_trigger_commit')
        exact_old_positive_domain = r['path_sequence'] > 0 and r['profile_sequence'] > 0
        startup_absent = (r[opposite + '_sequence'] == 0 and not r['froze'] and r['phase_still_awaiting']
                          and r[opposite + '_stamp_ns'] == -1000000001
                          and not any(x['input_commit_ordinal'] <= r['input_commit_ordinal']
                                      for x in versions[opposite]))
        require(exact_old_positive_domain or startup_absent, 'classify_all_retry_source_events')
        retries.append(dict(r, frozen_checker_positive_sequence_domain=exact_old_positive_domain,
                            actually_missing_opposite_reference_at_commit=startup_absent,
                            diagnostic_domain_gap=startup_absent))
    require(len(retries) == 8 and sum(r['diagnostic_domain_gap'] for r in retries) == 1,
            'one_original_source_domain_bookkeeping_issue')

    first = candidates[1]
    first_d = next(r for r in rejected if r['job_id'] == 1)
    first_p = next(r['metadata'] for r in policies if r['job_id'] == 1)
    first_emitted = [r for r in publisher if r.get('type') == 'controlled_Applied_emitted'
                     and r.get('cycle_sequence') == first_d['sequence']]
    accepted = [r for r in decisions if r['accepted']]
    first_accepted = accepted[0]
    accepted_emitted = [r for r in publisher if r.get('type') == 'controlled_Applied_emitted'
                        and r.get('cycle_sequence') == first_accepted['sequence']]
    require(first['first_control'] == [.5, .5] and not first_d['accepted'] and
            len(first_emitted) == 1 and first_emitted[0]['final_n'] == [0., 0.] and
            len(accepted_emitted) == 1 and first_accepted['job_id'] == 2,
            'first_cold_candidate_not_published_as_applied')
    counts = dict(Counter(d['reason'] for d in rejected))
    require(counts == {'activation_history_or_time': 7, 'activation_input_changed_during_validation': 3},
            'exact_rejection_counts')
    require(result['cleanup_complete'] and all(v == 0 for v in result['owned_role_returncodes'].values()),
            'five_role_normal_exit_and_cleanup')
    after = {p: sha(p) for p in inputs}
    require(before == after, 'postrun_diagnosis_is_read_only')
    audit = dict(schema='owned-cold-activation-postrun/v1', passed=True,
                 passed_semantics='read-only source diagnosis and availability audit only; frozen experiment remains NoGo',
                 input_sha256_before=before, input_sha256_after=after,
                 original_case_passed=False, original_case_issues=report['issues'],
                 original_report_sha256=before[str(report_path)],
                 original_checker_not_rewritten=True, original_thresholds_unchanged=True,
                 measurement_attempts=100, accepted=90, maximum_consecutive_accepted=19,
                 rejection_counts=counts, all_rejections=rows,
                 no_rejected_candidate_was_late_to_registration=True,
                 minimum_rejected_candidate_ready_margin_ms=min(r['ready_margin_ms'] for r in rows),
                 native_policy_events=101, cold_policy_native_application_count=1,
                 cold_candidate_job_id=1, cold_candidate_native_calls=4, later_free_one_call_jobs=100,
                 first_candidate_control_n=first['first_control'],
                 first_candidate_kernel_sum_ms=first_p['kernel_sum_ms'],
                 first_candidate_native_adapter_ms=first_p['native_entry_elapsed_ms'],
                 first_candidate_Worker_solve_entry_ms=(first['solve_end_ns'] - first['solve_start_ns']) / 1e6,
                 first_candidate_ready_margin_ms=(first_d['planned_ns'] - first_d['ready_commit_ns']) / 1e6,
                 first_candidate_accepted=False, first_candidate_applied=False,
                 first_rejection_owner_emitted_n=first_emitted[0]['final_n'],
                 first_actual_accepted_job_id=2, first_actual_accepted_command_n=accepted_emitted[0]['final_n'],
                 independent_first_job_subcalls=report['cold_start_policy']['independent_first_job_subcalls'],
                 valid_odom_callback_full_cdrs_checked=len(odom),
                 historical_point_selection_not_implemented=True,
                 historical_point_availability_is_not_predicted_acceptance=True,
                 reference_pair_retry_events=retries,
                 retry_domain_gaps=1, retry_domain_gap_changes_overall_NoGo=False,
                 performance=report['performance'], model=report['model'],
                 closed_loop_performance_of_applied_050_policy_proven=False,
                 all_owned_roles_exit_zero_and_cleanup_complete=True,
                 stage_qualified=False, execute_qualified=False, true_plant_qualified=False,
                 research_conclusion=False,
                 next_order=['freeze failure and current evidence',
                             'offline causal activation-state selection and atomic commit design',
                             'new revision finite native positive and refusal tests',
                             'new exact contract/config authentication and one original s005 case'])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('x') as f:
        f.write(json.dumps(audit, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps({k: audit[k] for k in ['passed', 'original_case_passed', 'rejection_counts',
                    'first_candidate_Worker_solve_entry_ms', 'first_candidate_ready_margin_ms',
                    'first_candidate_applied', 'retry_domain_gaps', 'valid_odom_callback_full_cdrs_checked']}))


if __name__ == '__main__':
    main()
