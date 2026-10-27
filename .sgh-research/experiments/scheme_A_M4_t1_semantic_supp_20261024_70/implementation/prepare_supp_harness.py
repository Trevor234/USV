#!/usr/bin/env python3
"""Derive the batch-70 S1 harness from the 69 reviewed harness.

The 25 original tests stay byte-identical: the S1 helpers are inserted at one
precise anchor inside C33MatrixAccess and the S1 tests are appended at EOF.
"""
from pathlib import Path
import datetime
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
B69 = ROOT.parent / 'scheme_A_M4_t1_review_20261024_69'
SOURCE = B69 / 'implementation/reviewed_harness/tests/test_current_candidate_reference_clock.cpp'
HARNESS = ROOT / 'implementation/supp_harness'
TARGET = HARNESS / 'tests/test_current_candidate_reference_clock.cpp'
NOW = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()


def pin(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


text = SOURCE.read_text()
helpers = (HARNESS / 's1_helpers_insert.cpp').read_text()
tests = (HARNESS / 's1_tests_append.cpp').read_text()
anchor = '   return {d.candidate_accepted,d.reason,d.control_source};\n }\n'
assert text.count(anchor) == 1, 'helper anchor is not unique in the 69 harness'
insert_at = text.index(anchor)
derived = text.replace(anchor, anchor + helpers, 1) + tests
assert derived[:insert_at] == text[:insert_at]
assert derived[insert_at:insert_at + len(anchor) + len(helpers)] == anchor + helpers
assert derived[insert_at + len(anchor) + len(helpers):] == text[insert_at + len(anchor):] + tests
with TARGET.open('x') as stream:
    stream.write(derived)
record = {'schema': 'M4-T1-S1-harness-derivation-v70', 'recorded_at': NOW,
          'source': {'path': str(SOURCE), **pin(SOURCE)},
          'helpers_insert': {'path': str(HARNESS / 's1_helpers_insert.cpp'), 'anchor': repr(anchor), **pin(HARNESS / 's1_helpers_insert.cpp')},
          'tests_append': {'path': str(HARNESS / 's1_tests_append.cpp'), **pin(HARNESS / 's1_tests_append.cpp')},
          'target': {'path': str(TARGET), **pin(TARGET)},
          'claim': 'target equals the 69 reviewed harness with the helper block inserted at the single anchor inside C33MatrixAccess and the S1 test block appended at end of file; the 25 original tests are byte-identical to batch 69'}
with (ROOT / 'evidence/supp_harness_derivation_v1.json').open('x') as stream:
    stream.write(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'target': str(TARGET), 'bytes': len(derived)}))
