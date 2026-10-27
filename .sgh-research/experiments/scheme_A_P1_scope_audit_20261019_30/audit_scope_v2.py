#!/usr/bin/env python3
"""Read frozen bytes and recompute descriptive metrics; never load a ROS context or solver."""
import ast
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import time

D = Path(__file__).resolve().parent
W = D.parent
REPO = Path('/home/trevor/USV')
E = W / 'p1_execution_architecture_20261005_01'
N = E / 'authored_D1_deferred_observation_20261019_v29'
H = REPO / '.sgh-research/handoffs/scheme_A_20261010_01'
CPP = REPO / 'usv_mpc_ws/src/usv_mpc_cpp'
PINS = {}


def digest(b):
    return hashlib.sha256(b).hexdigest()


def read(path, snapshot=False):
    p = Path(path)
    b = p.read_bytes()
    pin = dict(bytes=len(b), sha256=digest(b), resolved_path=str(p.resolve()))
    if str(p) in PINS:
        assert PINS[str(p)] == pin, 'input changed: ' + str(p)
    else:
        PINS[str(p)] = pin
        if snapshot:
            q = D / 'evidence/sources' / ('%03d_' % len(PINS) + p.name)
            if q.exists():
                assert q.read_bytes() == b, 'prior attempt snapshot changed'
            else:
                with q.open('xb') as f:
                    f.write(b)
    return b


def load(p, snapshot=False):
    return json.loads(read(p, snapshot))


def lines(p):
    return [json.loads(s) for s in read(p).splitlines() if s.strip()]


def write(rel, value):
    with (D / rel).open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def near(a, b, tol=1e-12):
    assert abs(a-b) <= tol, (a, b)


def one(rows, typ):
    vals = [r for r in rows if r.get('type') == typ]
    assert len(vals) == 1, (typ, len(vals))
    return vals[0]


CASES = [
    (19, 'scheme_A_longitudinal_20261016_19', 'authored_D1_longitudinal_20261016_v19', 'longitudinal_s005_01', 'geometric_reference'),
    (20, 'scheme_A_reference_bias_20261016_20', 'authored_D1_reference_bias_20261016_v20', 'projected_s005_01', 'geometric_reference_reanchored'),
    (22, 'scheme_A_reference_pair_wakeup_20261018_22', 'authored_D1_reference_pair_wakeup_20261018_v22', 'pair_wakeup_s005_01', 'first_job_target_task_epoch'),
    (28, 'scheme_A_activation_alignment_20261019_28', 'authored_D1_activation_alignment_20261019_v28', 'activation_s005_01', 'first_job_target_task_epoch'),
    (29, 'scheme_A_deferred_observation_20261019_29', 'authored_D1_deferred_observation_20261019_v29', 'deferred_s005_01', 'first_job_target_task_epoch'),
]


def frozen_metrics():
    baseline = load(W / CASES[0][1] / 'postrun/ladder_metrics_v1.json', True)['cases'][0]
    assert baseline['case'] == 's005'
    threshold = baseline['measured_surge_RMSE_m_s'] * .5
    results = []
    for batch, folder, author, runid, policy in CASES:
        report_path = W / folder / 'runs/s005_01/check_result.json'
        report = load(report_path, True)
        root = E / author / 'runs' / runid
        ob = lines(root / 'observer/source.jsonl')
        pub = lines(root / 'publisher/controlled_source.jsonl')
        model = lines(root / 'synthetic_source/nominal_steps.jsonl')
        wk = lines(root / 'worker/source.jsonl')
        close = load(root / 'adapter_driver_close_request.json', True)
        start, end = report['window']['start_ready_ns'], report['window']['end_driver_requested_ns']
        assert start == one(ob, 'legacy_ready')['readiness']['legacy_ready_ns']
        assert end == close['request_ns']
        steps = [r for r in model if r.get('schema') == 'p1-controlled-nominal-model-step-v1']
        samples = [r for r in steps if start <= r['target_ns'] < end]
        assert len({r['sensor_sequence'] for r in steps}) == len(steps)
        assert all(a['target_ns'] < b['target_ns'] for a, b in zip(steps, steps[1:]))
        assert all(len(r['state']) == 6 and all(math.isfinite(x) for x in r['state']) for r in samples)
        sse = math.fsum((r['state'][3]-.05)**2 for r in samples)
        rmse = math.sqrt(sse/len(samples))
        last = [r for r in samples if r['target_ns'] >= end-5_000_000_000]
        lastmean = math.fsum(r['state'][3] for r in last)/len(last)
        expected = baseline if batch == 19 else report['performance']
        assert len(samples) == expected['measurement_sensor_count']
        near(rmse, expected['measured_surge_RMSE_m_s'])
        near(lastmean, expected['last5s_mean_surge_m_s'])
        if batch != 19:
            near(threshold, expected['RMSE_limit_m_s'])
            assert not report['passed'] and not expected['RMSE_passed']
        dec = [r for r in ob if r.get('type') == 'decision' and r.get('accepted') and start <= r['activation_commit_ns'] < end]
        assert len(dec) == report['window']['accepted']
        first = dec[0]
        physical = [r for r in pub if r.get('type') == 'controlled_decision_physical_return'
                    and r['decision_sequence'] == first['sequence']]
        assert len(physical) == 1
        applied = [r for r in pub if r.get('type') == 'controlled_Applied_emitted'
                   and r['applied_sequence'] == physical[0]['applied_sequence']]
        assert len(applied) == 1
        a = applied[0]
        assert a['final_n'] == first['final_n'] == physical[0]['actual_n']
        api_start, api_end = min(a['left_start_ns'], a['right_start_ns']), max(a['left_end_ns'], a['right_end_ns'])
        actual_jobs = [r for r in ob if r.get('type') == 'job']
        assert actual_jobs[0]['job']['job_id'] == 1
        jrow = actual_jobs[0]
        j = jrow['job']
        worker_first = next(r for r in wk if r.get('type') == 'candidate' and r['job']['job_id'] == 1)
        epochs = [r for r in ob if r.get('type') == 'reference_epoch_committed']
        assert len(epochs) == (0 if batch in [19, 20] else 1)
        prefix = []
        for ns in [api_start-start, 500_000_000, 1_000_000_000, 2_000_000_000, 5_000_000_000]:
            sub = [r for r in samples if r['target_ns'] < start+ns]
            ss = math.fsum((r['state'][3]-.05)**2 for r in sub)
            prefix.append(dict(duration_ns=ns, samples=len(sub), SSE=ss,
                               fraction_of_full_SSE=ss/sse, fraction_of_original_allowance=ss/(len(samples)*threshold**2),
                               full_RMSE_floor_if_other_errors_zero=math.sqrt(ss/len(samples))))
        cumulative = 0.
        crossing = None
        for i, r in enumerate(samples):
            cumulative += (r['state'][3]-.05)**2
            if cumulative > len(samples)*threshold**2:
                crossing = dict(sample_index=i+1, ready_offset_ns=r['target_ns']-start, cumulative_SSE=cumulative)
                break
        # The initial hold lasts until each channel's actual API call. Later
        # transport/plant receipt is deliberately not inferred from these times.
        second = next((r for r in pub if r.get('type') == 'controlled_Applied_emitted' and r['applied_sequence'] > a['applied_sequence']), None)
        row = dict(batch=batch, frozen_report=str(report_path), raw_run=str(root), run_id=runid,
                   inherited_original_case_passed=report['passed'], reference_policy=policy,
                   Ready_ns=start, close_requested_ns=end, duration_ns=end-start,
                   first_job_submit_offset_ns=jrow['submit_commit_ns']-start,
                   first_job_target_offset_ns=j['target_ns']-start, first_job_target_sim_ns=j['target_sim_ns'],
                   first_job_frozen_state=j['frozen_state'], first_job_target_state=j['target_state'],
                   first_reference_state=j['reference'][:6], first_native_entry_ms=(worker_first['solve_end_ns']-worker_first['solve_start_ns'])/1e6,
                   task_epoch=epochs[0]['reference_epoch'] if epochs else None,
                   first_API_start_offset_ns=api_start-start, first_API_both_returned_offset_ns=api_end-start,
                   first_Applied_DDS_return_offset_ns=a['applied_publish_end_ns']-start,
                   first_command_n=a['final_n'], first_per_channel_API_start_ns=[a['left_start_ns'],a['right_start_ns']],
                   first_per_channel_API_end_ns=[a['left_end_ns'],a['right_end_ns']],
                   first_hold_to_next_API_ns=None if second is None else [second['left_start_ns']-a['left_start_ns'],second['right_start_ns']-a['right_start_ns']],
                   initial_model_state=steps[0]['initial_state'], first_sample_after_ready=samples[0]['state'],
                   first_sample_offset_ns=samples[0]['target_ns']-start,
                   accepted=len(dec), attempts=report['window']['attempts'], consecutive=report['window']['consecutive_accepted'],
                   sensor_count=len(samples), full_SSE=sse, full_RMSE_m_s=rmse,
                   diagnostic_comparison_threshold_m_s=threshold, original_allowable_SSE=len(samples)*threshold**2,
                   threshold_was_preregistered_for_this_case=batch != 19,
                   last5s_sensor_count=len(last), last5s_mean_surge_m_s=lastmean,
                   last5s_SSE=math.fsum((r['state'][3]-.05)**2 for r in last),
                   sampled_x_progress_m=samples[-1]['state'][0]-samples[0]['state'][0],
                   sampled_progress_duration_ns=samples[-1]['target_ns']-samples[0]['target_ns'],
                   fixed_speed_distance_for_same_sample_span_m=.05*(samples[-1]['target_ns']-samples[0]['target_ns'])/1e9,
                   final_sample_state=samples[-1]['state'], prefixes=prefix, first_allowance_crossing=crossing,
                   model_generations=sorted({r['job']['model_generation'] for r in actual_jobs}),
                   nominal_hashes=sorted({r['job']['nominal_hash'] for r in actual_jobs}),
                   plant_ACK_or_measured_force_proven=False, stage_qualified=False)
        results.append(row)
    return dict(schema='P1-frozen-startup-comparison/v1', passed=True, cases=results,
                method='Independent stdlib arithmetic from complete frozen Source files and exact original report windows; historical Source/Storage joins referenced, not rerun',
                new_ROS_run=False, original_reports_rewritten=False, unique_cross_run_cause_identified=False,
                scope='post-hoc descriptive comparison, five single runs at 0.05m/s; no paired experimental inference or universal infeasibility theorem',
                threshold_provenance='batch20 diagnostic half of batch19 RMSE; batch19 column is retrospective comparison only',
                interval_metrics_use_shutdown_tail=False, stage_qualified=False, execute_qualified=False, research_conclusion=False)


def interface_audit():
    script = read(CPP/'scripts/regenerate_acados_codegen.py', True).decode()
    tree = ast.parse(script)
    mapping = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'PG_INDICES' for t in n.targets))
    assert sorted(mapping.values()) == list(range(19))
    hdr = read(CPP/'acados_generated/acados_solver_usv_dyn_nmpc.h', True).decode()
    dims = {k:int(re.search(r'^#define USV_DYN_NMPC_'+k+r'\s+(\d+)',hdr,re.M)[1]) for k in ['NX','NU','NP','NP_GLOBAL','N']}
    assert dims == dict(NX=8, NU=2, NP=6, NP_GLOBAL=30, N=20)
    install = REPO/'usv_mpc_ws/install/usv_mpc_cpp'
    assert read(install/'include/usv_mpc_cpp/acados_generated/acados_solver_usv_dyn_nmpc.h') == hdr.encode()
    generated = read(CPP/'acados_generated/acados_solver_usv_dyn_nmpc.c', True).decode()
    backend = read(CPP/'src/acados_backend.cpp', True).decode()
    raw = read(N/'worker/raw_backend_v1.hpp', True).decode()
    owned = read(N/'worker/owned_cold_backend.hpp', True).decode()
    worker = read(N/'worker/solver_worker.cpp', True).decode()
    public_h = read(CPP/'include/usv_mpc_cpp/acados_backend.hpp', True).decode()
    assert backend.count('usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies(') == 1
    assert raw.count('usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies(') == 1
    assert 'int np_global = 30;' in generated and 'in->global_data' in generated
    assert 'continuous_ode_expr(xp, uu, p_global' in script and 'x_ref = p' in script
    assert 'model.disc_dyn_expr = disc_phi' in script
    msg = REPO/'usv_mpc_ws/src/usv_research_interfaces/msg'
    job = read(msg/'SolveJob.msg', True).decode()
    candidate = read(msg/'SolveCandidate.msg', True).decode()
    assert 'model_generation' in job and 'nominal_hash' in job
    assert not any(s in job for s in ['p_global','model_snapshot_hash','hydro_params'])
    assert 'usv_research_interfaces/SolveJob job' in candidate
    # Capture actual archive and selected actual Worker symbols without executing them.
    build = W/'scheme_A_activation_alignment_20261019_28/build/activation_worker_attempt02'
    links = load(build/'static_link_inputs_before.json', True)
    for p,row in links['files'].items():
        assert digest(read(p)) == row['sha256']
    binary = build/'cmake_build/p1_solver_worker_owned_v2'
    assert digest(read(binary)) == '1462e6be4ffec0079319cb6fb1aed8c3067df1065e9d167351092cd586e595f1'
    read('/usr/bin/nm')
    symbol_evidence = []
    for p in [install/'lib/libcodegen_lib.a', binary]:
        cmd = ['nm','-g','--defined-only',str(p)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=True)
        hits = [s for s in r.stdout.splitlines() if any(s.endswith(v) for v in [
            'usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies',
            'usv_dyn_nmpc_dyn_disc_phi_fun','usv_dyn_nmpc_p_global_precompute_fun'])]
        assert len(hits) == 3
        symbol_evidence.append(dict(command=cmd, returncode=r.returncode, selected_defined_symbols=hits,
                                    complete_stdout_sha256=digest(r.stdout.encode()), stderr=r.stderr))
    contract = load(N/'pair_wakeup_contract_v1.json', True)
    pg = [contract['hydro'][name] for name,_ in sorted(mapping.items(), key=lambda x:x[1])]
    pg += contract['Q']+contract['R']+contract['Rd']+[contract['Qf_scale']]
    assert len(pg) == 30
    assert contract['execute_qualified'] is False
    # Merely design two known hydro snapshots; no capsule creation or optimization.
    p1 = list(pg); p1[9] = 1.2*pg[9]
    return dict(schema='dynamic-NMPC-actual-interface-audit/v1', passed=True,
                dimensions=dims, p_global_layout={str(i):name for name,i in mapping.items()},
                weight_layout={'19..24':'Q[6]','25..26':'R[2]','27..28':'Rd[2]','29':'Qf_scale'},
                stage_parameters='reference x,y,psi,u,v,r only; no residual or obstacle slots',
                observed_current_contract_p_global=pg, proposed_finite_hydro_model_1_p_global=p1,
                proposed_only_changed_index=9, proposed_Xu_scale=1.2,
                proposed_values_are_design_not_runtime_evidence=True,
                generated_setter_and_dynamics_symbols_present_in_selected_actual_Worker=symbol_evidence,
                installed_header_equal_current_source_header=True,
                public_backend_global_setter_call_count=1, raw_backend_global_setter_call_count=1,
                setter_calls_are_constructor_only=True,
                current_Worker_constructs_one_immutable_contract_backend=True,
                current_Job_has_model_generation_and_nominal_hash=True,
                current_Job_has_independent_model_snapshot_hash_or_numeric_model_payload=False,
                candidate_echoes_entire_Job=True,
                current_run_model_parameters_dynamically_switched=False,
                existing_API_can_recompute_global_data_for_same_graph=True,
                existing_public_Cpp_runtime_model_update_method=False,
                codegen_needed_for_same_layout_hydro_values=False,
                codegen_needed_for_new_residual_obstacle_or_shape=True,
                static_interface_inspection_is_runtime_model_switch_validation=False,
                no_new_codegen_build_ROS_or_solver_execution=True,
                stage_qualified=False, execute_qualified=False, research_conclusion=False)


def main():
    started = time.monotonic_ns()
    # Consume complete primary handoff/material bytes and preserve their unchanged copies.
    read(H/'方案A_UbuntuCodex交接与全面推进计划_2026-10-10.md', True)
    load(H/'handoff_manifest.json', True)
    names = ['首选A_现有ROS平台可行性与实施方案_2026-10-03.md',
             'P1_M0b_B4_D1_启动握手组件_实施与验收_2026-10-09.md',
             'P1_M0b_B4_D1_启动握手组件_状态_2026-10-09.json',
             'P1_M0b_B4_D1_owned端点与配置认证_最小计划_2026-10-09.md',
             'P1_剩余环境差异_最小修复与验证记录_2026-10-10.md',
             'P1_剩余环境差异_修复审计_2026-10-10.json','startup_handshake_build_manifest_v1.json',
             'P1_M0b_B4_参数来源与版本适用审查_2026-10-09.md',
             'P1_M0b_B4_参数来源与冻结决策_2026-10-09.json']
    for name in names:
        read(H/'source_docs'/name, True)
    for rel in ['observer/src/shadow/regulator_shadow_observer.cpp','worker/protocol.hpp',
                'observer/src/shadow/p1_full_contract.hpp','observer/src/shadow/p1_admission.hpp',
                'runtime/p1_contract_spec_v1.json','build_manifest_current.json',
                'check_activation_alignment_v1.py','contract_identity_v1.py']:
        read(N/rel, True)
    read(CPP/'src/usv_model_dynamic.cpp', True)
    read(CPP/'include/usv_mpc_cpp/usv_model_dynamic.hpp', True)
    read(CPP/'acados_generated/usv_dyn_nmpc_model/usv_dyn_nmpc_dyn_disc_phi_fun.c', True)
    read(CPP/'acados_generated/usv_dyn_nmpc_p_global_precompute_fun.c', True)
    load(W/'scheme_A_deferred_observation_20261019_29/postrun/performance_gate_lineage_v1.json', True)
    metrics = frozen_metrics()
    interface = interface_audit()
    write('analysis/frozen_run_comparison_v1.json', metrics)
    write('analysis/dynamic_model_interface_v1.json', interface)
    initial = dict(PINS)
    for path in initial:
        read(path)
    assert PINS == initial
    write('evidence/audit_input_lock_v1.json', dict(schema='P1-scope-input-lock/v1', passed=True,
          input_sha256_before=initial, input_sha256_after=PINS, input_count=len(PINS),
          started_monotonic_ns=started, finished_monotonic_ns=time.monotonic_ns(),
          no_external_module_import_or_endpoint_authority=True, snapshots_are_copies_not_new_run_evidence=True))
    print(json.dumps(dict(passed=True, input_count=len(PINS), batches=[r['batch'] for r in metrics['cases']],
                         dims=interface['dimensions'], source_or_runtime_assets_modified=False)))


if __name__ == '__main__':
    main()
