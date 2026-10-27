#!/usr/bin/env python3
"""Generate current Python/C++ profile values from one bounded, pinned spec.

Semantic validators are preserved, reviewable templates; emitted field sets,
baseline, profile ID, and spec SHA all come from the same exact spec bytes.
Output is create-only so earlier attempts and their evidence stay intact.
"""
import hashlib
import json
from pathlib import Path
import re

D = Path(__file__).resolve().parent


def emit(path, data):
    with path.open('xb') as stream:
        stream.write(data)


def main():
    spec_path = D / 'current_contract_spec_v1.json'
    raw = spec_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    spec = json.loads(raw)
    assert len(spec['legacy_baseline']) == 81
    assert len(spec['legacy_baseline']['hydro']) == 19
    assert spec['physical_execute_release_enabled'] is False
    assert spec['legacy_diagnostic_revision'] == 10
    assert spec['formal_schema'] == 'p1-execution-contract-v3'
    values = {
        'SPEC_SHA256': sha,
        'PROFILE_ID': spec['profile_id'],
        'BASELINE_JSON': json.dumps(spec['legacy_baseline'], separators=(',', ':'),
                                    sort_keys=True, ensure_ascii=True, allow_nan=False),
    }
    for key in ('integer_keys', 'resource_keys', 'special_keys'):
        assert len(spec[key]) == len(set(spec[key]))
        values[key.upper()] = ','.join(json.dumps(k) for k in sorted(spec[key]))
    outputs = {}
    for template, target in [
        ('p1_full_contract.hpp.in', 'native/p1_full_contract.hpp'),
        ('p1_resources.hpp.in', 'native/p1_resources.hpp'),
        ('p1_full_contract.py.in', 'python/p1_full_contract.py'),
        ('p1_resource_contract.py.in', 'python/p1_resource_contract.py'),
    ]:
        text = (D / 'templates' / template).read_text()
        for key, value in values.items():
            text = text.replace('@' + key + '@', value)
        assert re.search(r'@[A-Z_]+@', text) is None
        outputs[D / target] = text.encode()
    outputs[D / 'python/p1_contract_spec_v1.json'] = raw
    for path, data in outputs.items():
        emit(path, data)
    record = {'schema': 'B5-generated-contract-artifacts/v1',
              'spec_sha256': sha, 'profile_id': spec['profile_id'],
              'diag_fields': 81, 'formal_fields': 84,
              'source_of_values': str(spec_path),
              'generated': {str(p): {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}
                            for p, b in outputs.items()},
              'fixed_current_parameters_changed': False,
              'physical_execute_release_enabled': False}
    emit(D.parent / 'evidence/generated_contract_artifacts_v1.json',
         (json.dumps(record, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps({k: record[k] for k in ('spec_sha256', 'diag_fields', 'formal_fields')}))


if __name__ == '__main__':
    main()
