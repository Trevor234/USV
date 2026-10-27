#!/usr/bin/env python3
"""Verify historical inputs and review evidence; create a bounded closeout."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return {'bytes': path.stat().st_size, 'sha256': h.hexdigest()}


before = read(ROOT / 'evidence/inputs_before_v1.json')
missing = [p for p in before['files'] if not Path(p).is_file()]
changed = [p for p, value in before['files'].items() if Path(p).is_file() and pin(p) != value]
workspace_changed = [p for p, value in before['workspace_files'].items() if not Path(p).is_file() or pin(p) != value]
selected_after = set()
for name in ['scheme_A_M4_t1_semantic_supp_20261024_70',
             'scheme_A_M4_t2_action_freeze_20261024_71',
             'scheme_A_M4_t2a_clock_freeze_owned_20261024_72',
             'scheme_A_M4_t2b_feasibility_20261024_73']:
    for parent, dirs, filenames in os.walk(ROOT.parent / name):
        dirs[:] = [d for d in dirs if d not in ('build', 'cmake_build', 'CMakeFiles', '__pycache__') and not d.startswith('build_')]
        selected_after.update(str(Path(parent) / f) for f in filenames if (Path(parent) / f).is_file())
added = sorted(selected_after - set(before['files']))
status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=REPO, text=True)
report_path = ROOT / 'documents/方案A_第74批_70至73批独立代码审查与后续实施计划_2026-10-24.md'
report = report_path.read_text()
measurements = read(ROOT / 'evidence/independent_replay01/boundary/measurements.json')
for row in measurements['job_windows']:
    line = f"| {row['job_id']} | {row['receive_to_candidate_event_ns'] / 1e6:.6f} | {row['submit_commit_to_ready_commit_ns'] / 1e6:.6f} |"
    assert line in report, line
review = read(ROOT / 'postrun/review_findings_v1.json')
plan = read(ROOT / 'postrun/next_plan_v6.json')
assert review['review_reproductions_complete'] is True
assert review['production_fixes_implemented'] is False
assert review['owned_runs_this_batch'] == 0
assert plan['qualification'] == dict.fromkeys(['M4', 'F6', 'P1', 'plant', 'hard_realtime'], False)
assert not missing and not changed and not workspace_changed and not added
assert status == before['status_porcelain']
verdict = {
    'schema': 'M4-T2-independent-review-final-v74',
    'recorded_at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
    'review_reproductions_complete': True,
    'protected_input_files': before['count'],
    'protected_input_bytes': sum(x['bytes'] for x in before['files'].values()),
    'historical_files_missing': missing, 'historical_files_changed': changed,
    'historical_selected_population_added': added,
    'workspace_ordinary_files_preserved': len(before['workspace_files']),
    'workspace_files_changed': workspace_changed,
    'git_porcelain_matches_before': True,
    'population_scope': before['scope'],
    'independent_replays': {p: read(ROOT / 'evidence/independent_replay01' / p / 'replay_result.json')
                            for p in ['contract', 'clock', 'boundary']},
    'report_measurements_match_raw': True,
    'findings_count': len(review['findings']),
    'production_fixes_implemented': False, 'owned_runs_this_batch': 0, 'ROS_graph_started': False,
    'T2A_14_full_family_accepted': False,
    'qualification': plan['qualification'], 'production_B_mode': 'MANUAL+RC override',
    'note': 'Review completion includes correctly reproduced negative findings; it is not component requalification or a T2/M4/F6/P1 pass.'}
with (ROOT / 'evidence/final_verification_v1.json').open('x') as stream:
    stream.write(json.dumps(verdict, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'review_finished': True, 'protected_files': before['count'],
                  'workspace_files_preserved': len(before['workspace_files']),
                  'historical_changes': 0, 'owned_runs_this_batch': 0}, ensure_ascii=False))
