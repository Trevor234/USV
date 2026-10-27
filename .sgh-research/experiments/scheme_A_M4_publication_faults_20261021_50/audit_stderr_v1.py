#!/usr/bin/env python3
"""Classify every stderr line without suppressing, editing, or rerunning a test."""
import hashlib
import json
from pathlib import Path
import re

D = Path(__file__).resolve().parent
path = D / 'verification/component_run01/stderr.log'
raw = path.read_bytes()
text = raw.decode()
blocks = re.findall(r'>>> \[rcutils\|error_handling\.c:108\] rcutils_set_error_state\(\).*?<<<', text, re.S)
old = "Handle's typesupport identifier (rosidl_typesupport_cpp) is not supported by this library, at ./src/type_support_dispatch.hpp:114"
site = str(D / 'author_v2/test_m4_publication_faults.cpp') + ':54'
for block in blocks:
    assert old in block
    assert 'test50 declared private publisher return-seam failure, at ' + site in block
    assert block.count('This error state is being overwritten:') == 1
remaining = text
for block in blocks:
    remaining = remaining.replace(block, '', 1)
warnings = [line for line in remaining.splitlines() if line.strip()]
assert len(warnings) == 2
assert all(re.match(r'^\[WARN\] \[[0-9.]+\] \[rcl\]: ', line) for line in warnings)
assert 'ROS_LOCALHOST_ONLY is deprecated but still honored' in warnings[0]
assert "'localhost_only' is enabled" in warnings[1]
audit = json.loads((D / 'postrun/publication_fault_audit_v1.json').read_bytes())
assert audit['passed'] and audit['totals']['injected_return_errors'] == 14
assert len(blocks) == 8 <= audit['totals']['injected_return_errors']
result = {'schema': 'M4-private-test-native-stderr-complete-classification/v1', 'passed': True,
          'source': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
          'SDK_localhost_compatibility_warnings': warnings,
          'old_typesupport_error_state_overwrite_diagnostics': len(blocks),
          'all_overwrite_emitters_at_declared_test_return_seam': True,
          'old_error_state_text': old,
          'attribution': 'Existing SDK error state was overwritten by this test ELF error setter; this is the observed diagnostic cause. Generic type-support fallback as the original stale-state source is an inference, not a proven full provenance trace.',
          'new_failure_text_and_emitter_proven': True, 'original_stale_state_full_provenance_proven': False,
          'all_delegated_calls_succeeded_and_wire_matched': True,
          'unclassified_nonempty_stderr_lines': 0,
          'original_stderr_modified_or_filtered': False, 'new_ROS_test_run': False,
          'these_diagnostics_called_real_DDS_failures': False, 'M4_stage_qualified': False, 'P1_qualified': False}
with (D / 'postrun/native_stderr_diagnostics_v1.json').open('x') as f:
    json.dump(result, f, ensure_ascii=False, indent=2, sort_keys=True)
    f.write('\n')
assert path.read_bytes() == raw
print(json.dumps({'passed': True, 'overwrite_diagnostics': len(blocks), 'compatibility_warnings': len(warnings), 'unclassified_lines': 0}))
