"""Driver-independent temporal predicates on complete Source and Witness records."""


def need(value, why):
    if not value:
        raise ValueError(why)


def timing_accepts(case, origin, checked, last_receipt, reason):
    if any(type(x) is not int or x <= 0 for x in [origin, checked, last_receipt]):
        return False
    if checked < origin or checked < last_receipt:
        return False
    if case == 'active':
        return reason == 'active_watchdog' and checked - origin > 1_000_000_000 and checked - last_receipt <= 600_000_000
    if case == 'lease':
        return reason == 'worker_capability_expired' and origin == last_receipt and checked - origin > 600_000_000
    return False



def terminal_source_cause(terminal, source):
    raw = terminal['reason']
    known = {'active_watchdog', 'worker_capability_expired'}
    if raw in known:
        return raw
    prefix = 'legacy_ready_invalidated:worker_unusable:'
    need(raw.startswith(prefix) and raw[len(prefix):] in known, 'unknown_terminal_causal_chain')
    cause = raw[len(prefix):]
    invalidations = [r for r in source if r.get('type') == 'legacy_ready_invalidated'
                     and r.get('reason') == 'worker_unusable:' + cause
                     and r.get('check_ns') == terminal['check_ns']]
    need(len(invalidations) == 1 and invalidations[0]['terminal'] is True
         and invalidations[0]['measurement_eligible'] is False
         and source.index(invalidations[0]) < source.index(terminal), 'causal_invalidation_record_required')
    return cause


def check(case, source, worker, witness, observation):
    transitions = [r for r in source if r.get('type') == 'worker_unusable_transition']
    need(len(transitions) == 1, 'exact_first_terminal_transition')
    terminal = transitions[0]
    t = terminal['check_ns']
    cause = terminal_source_cause(terminal, source)
    admissions = [r for r in source if r.get('type') == 'capability_admission']
    before = sorted([r for r in admissions if r['validation_commit_ns'] < t and r['renewed']],
                    key=lambda r: r['validation_commit_ns'])
    need(before, 'prior_actual_renewed_capability')
    last = before[-1]['validation_commit_ns']
    need(last == terminal['capability_last_valid_commit_ns'] and terminal['capability_timeout_ns'] == 600_000_000,
         'last_valid_receipt_origin')
    need(terminal['candidate_after'] is False and terminal['pending_after'] is False, 'terminal_invalidates_work')
    need(not any(r['commit_ns'] > t for r in witness['submit']), 'new_submit_authorization_after_terminal')
    need(not any(r['accepted'] and r['commit_ns'] > t for r in witness['activation']), 'new_activation_after_terminal')
    suffix = [r for r in admissions if r['validation_commit_ns'] > t]
    need(len([r for r in suffix if r['identity_valid'] and r['valid']]) >= 2, 'actual_valid_identity_terminal_suffix')
    need(all(not r['renewed'] and r['terminal_run'] and r['lease_last_after_ns'] == last for r in suffix),
         'same_run_cannot_revive')
    summary = [r for r in source if r.get('type') == 'source_summary']
    need(len(summary) == 1 and summary[0] == source[-1] and summary[0]['dropped'] == 0
         and summary[0]['generated'] == summary[0]['emitted'], 'complete_Observer_Source')
    need(witness['closed'] and witness['observation_complete'] and not witness['overflow'] and not witness['incomplete'],
         'complete_Witness')
    need(observation['first_transition'] == terminal and observation['case'] == case
         and observation['finished_ns'] <= observation['deadline_ns'], 'driver_observation_bound_to_actual_Source')
    need(not any(r.get('type') == 'diagnostic_c38_gate_timeout' for r in source), 'unexpected_gate_timeout')
    details = {}
    if case == 'active':
        enters = [r for r in worker if r.get('type') == 'diagnostic_v2_pre_native_enter']
        exits = [r for r in worker if r.get('type') == 'diagnostic_v2_pre_native_release']
        need(len(enters) == len(exits) == 1, 'one_shot_work_thread_barrier')
        entry, exit = enters[0], exits[0]
        job = entry['job_id']
        need(entry['policy'] == exit['policy'] == 'pre_native_once_after_completed_v1'
             and entry['duration_ms'] == 1700 and entry['completed_jobs_before'] >= 1
             and exit['job_id'] == job and not entry['actual_native_invoked'] and not exit['actual_native_invoked']
             and entry['start_ns'] < t < exit['released_ns']
             and exit['released_ns'] - entry['start_ns'] >= 1_700_000_000, 'actual_pre_native_barrier_extent')
        active, since = 0, 0
        for row in before:
            if row['capability']['active_job'] != active:
                active = row['capability']['active_job']
                since = row['validation_commit_ns']
        need(active == job == terminal['active_job'] and 0 < since < t and since <= entry['start_ns'] + 200_000_000, 'active_origin_from_actual_valid_receipt')
        need(timing_accepts(case, since, t, last, cause), 'active_watchdog_strict_time_and_live_lease')
        period_capabilities = [r for r in before if entry['start_ns'] <= r['validation_commit_ns'] < t
                               and r['capability']['active_job'] == job]
        publications = [r for r in worker if r.get('type') == 'capability_publish_result' and r['returned']
                        and entry['start_ns'] <= r['publish_start_ns'] < t]
        need(len(period_capabilities) >= 3 and len(publications) >= 3, 'main_capability_continues_while_work_thread_blocked')
        expiry = [r for r in worker if r.get('type') == 'pending_expired_before_native' and r['job_id'] == job]
        need(len(expiry) == 1 and expiry[0]['solver_invoked'] is False and expiry[0]['now_ns'] >= exit['released_ns'],
             'blocked_job_cannot_invoke_native_after_absolute_deadline')
        start = entry['start_ns']
        details = {'blocked_job_id': job, 'active_origin_ns': since, 'transition_delay_ns': t - since,
                   'last_receipt_age_at_transition_ns': t - last,
                   'continued_valid_capability_receipts': len(period_capabilities),
                   'continued_actual_capability_publish_returns': len(publications),
                   'barrier_elapsed_ns': exit['released_ns'] - start, 'actual_native_invoked_for_blocked_job': False}
    elif case == 'lease':
        pauses = [r for r in source if r.get('type') == 'diagnostic_c38_gate_paused']
        resumes = [r for r in source if r.get('type') == 'diagnostic_c38_gate_resumed']
        need(len(pauses) == len(resumes) == 1, 'one_actual_pause_and_resume')
        pause, resume = pauses[0], resumes[0]
        start, end = pause['gate']['paused_ns'], resume['gate']['resumed_ns']
        need(pause['gate_interface'] == resume['gate_interface'] == 'worker'
             and pause['group_registered'] is False and resume['group_registered'] is True
             and last <= start < t < end < pause['gate']['deadline_ns'], 'receipt_expiry_inside_actual_callback_gate')
        need(timing_accepts(case, last, t, last, cause), 'receipt_lease_strict_expiry')
        need(not any(start < r['validation_commit_ns'] < end for r in admissions), 'capability_callback_during_removed_group')
        publications = [r for r in worker if r.get('type') == 'capability_publish_result' and r['returned']
                        and start < r['publish_start_ns'] < end]
        need(len(publications) >= 3, 'actual_Worker_publications_continue_while_callback_paused')
        resumed_valid = [r for r in suffix if r['validation_commit_ns'] > end and r['identity_valid'] and r['valid']]
        need(len(resumed_valid) >= 2, 'actual_resumed_callbacks_required')
        need(not any(r.get('type') == 'diagnostic_v2_pre_native_enter' for r in worker), 'lease_case_has_no_work_thread_barrier')
        details = {'last_valid_receipt_ns': last, 'transition_delay_ns': t - last,
                   'pause_ns': start, 'resume_ns': end, 'pause_elapsed_ns': end - start,
                   'actual_capability_publish_returns_while_paused': len(publications),
                   'actual_resumed_valid_identity_callbacks': len(resumed_valid)}
    else:
        raise ValueError('unknown_V2_case')
    decisions = [r for r in source if r.get('type') == 'decision'
                 and start <= r['start_ns'] <= observation['finished_ns']]
    need(len(decisions) >= 4, 'ongoing_tick_Decisions_during_fault')
    need(not any(r['accepted'] and r['activation_commit_ns'] > t for r in decisions), 'Source_accepted_after_terminal')
    gaps = [b['start_ns'] - a['start_ns'] for a, b in zip(decisions, decisions[1:])]
    max_jitter = max(max(r['start_ns'] - r['planned_ns'], r['activation_commit_ns'] - r['planned_ns']) for r in decisions)
    need(not any(r['skipped_ticks'] for r in decisions) and max(gaps) <= 240_000_000
         and max_jitter <= 20_000_000, 'finite_tick_continuity_engineering_gate')
    return {'case': case, 'V2_fault_local_gate_passed': True, 'first_reason': terminal['reason'], 'first_cause': cause,
            'first_transition_ns': t, 'terminal_suffix_callbacks': len(suffix),
            'ongoing_Decisions_in_observation': len(decisions), 'maximum_start_gap_ns': max(gaps),
            'maximum_observed_start_or_activation_jitter_ns': max_jitter,
            'same_run_revival': False, 'no_post_terminal_submit_or_activation': True,
            'native_C_hang_proven': False, 'source_packet_freshness_proven': False,
            'WCET_or_plant_hard_bound_proven': False, 'details': details}
