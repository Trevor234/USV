#!/usr/bin/env python3
"""Validate inventory integrity; do not turn evidence counts into qualification."""
from pathlib import Path
import copy
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT.parent / 'scheme_A_formal_execute_profile_20261020_47/freeze/M4_fault_matrix_v1.json'


def validate(catalog):
    matrix = json.loads(MATRIX.read_text())
    assert catalog['matrix']['sha256'] == hashlib.sha256(MATRIX.read_bytes()).hexdigest(), 'parent matrix pin'
    assert len(catalog['groups']) == len(matrix['groups']) == 9, 'group population'
    assert len(catalog['original_clauses']) == 18, 'original clause population'
    assert catalog['new_ROS_or_owned_runs'] == 0, 'owned execution scope'
    assert all(catalog[key] is False for key in ('M4_stage_qualified', 'F6_qualified',
        'P1_qualified', 'plant_acceptance', 'hard_realtime', 'research_conclusion')), 'qualification promotion'
    ids = [row['id'] for row in catalog['cases']]
    assert len(ids) == len(set(ids)) == catalog['atom_count'], 'atom population/duplicates'
    assert catalog['N1_inventory_complete'] is True
    all_groups = {group['id']: group for group in matrix['groups']}
    for key, ref in catalog['evidence'].items():
        path = Path(ref['path'])
        assert path.is_file(), 'evidence missing: ' + key
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == ref['sha256'] and len(data) == ref['bytes'], 'evidence pin: ' + key
    for row in catalog['cases']:
        assert row['group'] in all_groups, 'foreign group'
        assert row['status'] in catalog['status_labels'], 'unknown disposition'
        assert row['evidence_keys'] and all(key in catalog['evidence'] for key in row['evidence_keys']), 'empty/unknown evidence'
        assert row['case'] and row['proven_scope'] and row['whole_stage_qualification_implied'] is False, 'missing layer boundary'
        if row['status'] in ('needs_wiring_validation', 'uncovered_current_path'):
            assert row['remaining_current_path_obligation'], 'gap without concrete next obligation'
    expected_clauses = {(g['id'], i): text for g in matrix['groups'] for i, text in enumerate(g['required_cases'])}
    seen = set()
    for row in catalog['original_clauses']:
        key = (row['group'], row['clause_index'])
        assert key not in seen and key in expected_clauses, 'clause identity'
        assert row['original_verbatim'] == expected_clauses[key], 'original wording changed'
        seen.add(key)
        expected_ids = {x['id'] for x in catalog['cases'] if x['group'] == row['group']
                        and x['original_clause_index'] == row['clause_index']}
        assert expected_ids and set(row['atom_ids']) == expected_ids, 'clause binding incomplete'
    assert seen == set(expected_clauses), 'missing original obligation'


def main():
    original = json.loads((ROOT / 'postrun/case_applicability_v1.json').read_text())
    validate(original)
    mutations = {
        'remove_original_clause': lambda value: value['original_clauses'].pop(),
        'rewrite_original_requirement': lambda value: value['original_clauses'][0].update(original_verbatim='weaker replacement'),
        'duplicate_atom': lambda value: value['cases'].append(copy.deepcopy(value['cases'][0])),
        'erase_evidence': lambda value: value['cases'][0].update(evidence_keys=[]),
        'forge_evidence_pin': lambda value: value['evidence']['current_core58'].update(sha256='0'*64),
        'promote_stage': lambda value: value.update(M4_stage_qualified=True),
        'remove_scope': lambda value: value['cases'][0].update(proven_scope=''),
        'erase_next_gap': lambda value: next(row for row in value['cases']
            if row['status'] == 'needs_wiring_validation').update(remaining_current_path_obligation=''),
    }
    rejected = {}
    for name, mutate in mutations.items():
        changed = copy.deepcopy(original)
        mutate(changed)
        assert changed != original, 'mutation did not prepare: ' + name
        try:
            validate(changed)
        except AssertionError as error:
            rejected[name] = str(error)
        else:
            raise AssertionError('mutation survived: ' + name)
    report = {'schema': 'M4-case-catalog-structural-audit-v67', 'baseline_passed': True,
              'mutations_assertion_rejected': rejected, 'complete': len(rejected) == len(mutations),
              'scope': 'Population, pins, clause binding and evidence-layer integrity; semantic sufficiency remains a review decision',
              'ROS_initialized': False, 'owned_runs': 0}
    with (ROOT / 'evidence/catalog_verification_v1.json').open('x') as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'baseline': True, 'assertion_mutations': len(rejected), 'complete': True}))


if __name__ == '__main__':
    main()
