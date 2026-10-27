#!/usr/bin/env python3
"""Create-only C3.5 final preservation audit and source/contract byte copies."""
import hashlib, json, os, re, stat, subprocess, sys
from pathlib import Path

D = Path(__file__).resolve().parent
W = Path('/home/trevor/USV')
N = W / '.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_5_20261013_v11'
P = D.parent / 'scheme_A_C3_4_20261013_09'
sys.path.insert(0, str(N))
import acceptance_core_v1 as C

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def write_new(path, value):
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')

def main():
    reader = C.Reader(seconds=300, max_bytes=1024 * 1024 * 1024, max_files=6000)
    contract_path = D / 'preregister/acceptance_contract_v3.json'
    contract_raw = reader.raw(contract_path)
    C.require(sha(contract_raw) == '927e9f0776b8deee4c1b77e730409549eba0916df1061e8cd11b1583e73281af', 'final_contract_identity')
    contract = C.strict_json(contract_raw)
    result = reader.json(D / 'acceptance/full_attempt03/result.json')
    pins = contract['identity_pins'] + contract['record_pins'] + [contract['preregister']]
    for pin in pins:
        reader.verify(pin)
        C.require(result['input_SHA_before'][pin['path']] == pin['sha256'], 'final_original_hash_link')
    C.require(len(pins) == 409 and len({p['path'] for p in pins}) == 409, 'fixed_pin_population')
    C.require(result['input_SHA_before'][str(contract_path)] == sha(contract_raw), 'contract_result_link')
    C.require(result['passed'] is True and result['fixed_inputs_unchanged'] is True, 'formal_result')
    C.require(len(result['jobs']) == 14 and all(j['returncode'] == 0 and j['status'] == 'passed' for j in result['jobs']), 'jobs')
    for job in result['jobs']:
        report = D / 'acceptance/full_attempt03' / (job['id'] + '.json')
        C.require(sha(reader.raw(report)) == result['input_SHA_before'][str(report)], 'generated_report_identity')
    C.require(len(result['input_SHA_before']) == 424, 'input_reads_fixed_plus_generated')
    C.require(all(v is False for v in result['qualifications'].values()), 'qualification_not_promoted')
    C.require(all(s['status'] == 'unknown' and s['qualified'] is False for s in result['assessment']['stages'].values()), 'stage_gaps_retained')

    parent_manifest_path = P / 'final_frozen_snapshot/manifest.json'
    parent_raw = reader.raw(parent_manifest_path)
    C.require(sha(parent_raw) == '8e30346fd19e88636f9d15b68fe0a55d27c6d78fc3fed8300570b85cba9da7a2', 'parent_manifest_identity')
    parent_manifest = C.strict_json(parent_raw)
    supplement_path = P / 'final_frozen_snapshot/source_supplement.json'
    supplement = reader.json(supplement_path)
    pairs = parent_manifest['files'] + parent_manifest['owned_raw'] + supplement['files']
    C.require(len(pairs) == 355, 'parent_pairs')
    for pin in pairs:
        for side in ('original', 'copy'):
            reader.verify({'path': pin[side], 'sha256': pin['sha256'], 'bytes': pin['bytes']})

    baseline_path = P / 'postrun/preserved_assets.json'
    baseline_raw = reader.raw(baseline_path)
    C.require(sha(baseline_raw) == '1097df3fa1bf9937aa0862f84a8bfd3de0a1cec9503534f53334af73a11c39e1', 'support_baseline_identity')
    baseline = C.strict_json(baseline_raw)
    # These declared support paths may intentionally be symlinks; preserve their
    # declared content and separately verify the explicit support link manifest.
    support_content = {}
    for path, expected in baseline['pins'].items():
        raw = Path(path).read_bytes()
        C.require(sha(raw) == expected, 'declared_parent_content_changed:' + path)
        support_content[path] = expected
    support_path = W / '.sgh-research/repairs/remaining_drift_20261010_01/SIM_SHARED_SUPPORT_20261010_01.json'
    support = json.loads(support_path.read_text())
    for entry in support['assets']:
        path = Path(entry['path'])
        C.require(str(path.resolve()) == entry['resolved_path'], 'support_resolved_path')
        C.require((os.readlink(path) if path.is_symlink() else None) == entry['link_target'], 'support_link_target')
        if entry['sha256'] is None:
            C.require(path.is_dir(), 'support_directory')
        else:
            C.require(sha(path.read_bytes()) == entry['sha256'], 'support_content')
    diff = subprocess.check_output(['git', 'diff', '--binary', '--', ':(exclude).gitignore'], cwd=W)
    C.require(len(diff) == 151961 and sha(diff) == 'd901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5', 'business_diff_changed')
    initial = reader.json(D / 'preflight/workspace_initial.json')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=W, text=True).strip()
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=W, text=True).strip()
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    C.require((head, branch, boot) == (initial['HEAD'], initial['branch'], initial['boot_id']), 'workspace_identity_changed')

    neg = reader.json(D / 'negatives/contract_copies_v1/result.json')
    readiness = reader.json(D / 'readiness/coherent_negatives_v1/summary.json')
    review = reader.json(D / 'postrun/current_independent_review_v3.json')
    log = reader.raw(D / 'postrun/unit_final48.log').decode()
    C.require(neg['passed'] is True and neg['count'] == 18, 'contract_negative_suite')
    C.require(readiness['all_expectations_met'] is True and readiness['case_count'] == 14, 'readiness_negative_suite')
    C.require(review['remaining_P1_P2_findings'] == [], 'independent_review')
    C.require(re.search(r'Ran 48 tests in [0-9.]+s\s+OK\s*$', log), 'final_unit_suite')
    C.require(reader.unchanged(), 'final_reader_original_changed')

    frozen = D / 'final_frozen_snapshot'
    frozen.mkdir(exist_ok=False)
    (frozen / 'source').mkdir()
    (frozen / 'contract').mkdir()
    sources = sorted(N.glob('*.py')) + [Path(__file__).resolve()]
    contracts = [contract_path, D / 'preregister/acceptance_contract_pin_v3.json',
                 D / 'preregister/execution_scope_v1.json', D / 'preregister/external_input_registry_v1.json',
                 D / 'readiness/readiness_c35_contract_v1.json', D / 'budget_scope/preregister_v2.json']
    frozen_entries = []
    for kind, paths in [('source', sources), ('contract', contracts)]:
        for number, path in enumerate(paths, 1):
            raw = reader.raw(path)
            copy = frozen / kind / (f'{number:02d}_' + path.name)
            with copy.open('xb') as f:
                f.write(raw)
            C.require(reader.raw(copy) == raw, 'frozen_copy_readback')
            frozen_entries.append({'kind': kind, 'original': str(path), 'copy': str(copy), 'sha256': sha(raw), 'bytes': len(raw)})
    C.require(reader.unchanged(), 'final_freeze_input_changed')
    manifest = {'schema': 'scheme-A-C3.5-new-source-contract-freeze/v1', 'files': frozen_entries,
                'new_N11_python_sources': len(sources) - 1, 'finalization_source': 1, 'contract_count': len(contracts),
                'all_pairs_verified': True, 'parent_N10_manifest': {'path': str(parent_manifest_path), 'sha256': sha(parent_raw)},
                'parent_N10_pairs_reverified': len(pairs), 'execute': False, 'stage_qualified': False, 'research_conclusion': False}
    write_new(frozen / 'manifest.json', manifest)
    qa = {'schema': 'scheme-A-C3.5-final-closure-QA/v1', 'passed': True,
          'HEAD': head, 'branch': branch, 'boot_id': boot,
          'original_business_diff_bytes': len(diff), 'original_business_diff_sha256': sha(diff),
          'N10_pairs': len(pairs), 'N10_pair_reads': len(pairs) * 2,
          'declared_parent_content_pins': len(support_content), 'support_declarations': len(support['assets']),
          'scope': 'declared current support, frozen N10, fixed formal inputs; not a full-machine or historical 3864-guard qualification',
          'formal_contract': {'path': str(contract_path), 'sha256': sha(contract_raw)},
          'identity_pins': len(contract['identity_pins']), 'record_pins': len(contract['record_pins']),
          'fixed_inputs_including_preregister_and_contract': 410, 'new_generated_reports': 14, 'reader_result_inputs': 424,
          'formal_jobs_passed': 14, 'final_unit_tests_passed': 48,
          'readiness_coherent_negatives_passed': 14, 'contract_copy_negatives_passed': 18,
          'new_source_contract_frozen_pairs': len(frozen_entries), 'qualifications': result['qualifications'],
          'stages': result['assessment']['stages'], 'new_ROS_nodes_launched': False,
          'old_expected_updated': False, 'old_failed_evidence_deleted': False,
          'older3864_guard_requalified': False, 'fixed_before_after_hashes': reader.hashes}
    write_new(D / 'postrun/final_closure_QA.json', qa)
    with (D / 'postrun/git_status_final.txt').open('x') as f:
        subprocess.run(['git', 'status', '--short'], cwd=W, stdout=f, check=True)
    print(json.dumps({k: v for k, v in qa.items() if k not in ('fixed_before_after_hashes', 'stages')}, ensure_ascii=False))

if __name__ == '__main__':
    main()
