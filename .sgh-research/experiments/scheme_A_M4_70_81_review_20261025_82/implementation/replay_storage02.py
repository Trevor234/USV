#!/usr/bin/env python3
"""Full workspace schema: align Python and native type support; no ROS init."""
from pathlib import Path
import hashlib
import json
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/replay02/storage'
OUT.mkdir(parents=True)
source = ROOT / 'evidence/replay01/protocol/validate_t2b_p01.py'
raw = source.read_text()
old = "sys.path.insert(0,str(ROOT/'p1_execution_architecture_20261005_01/v4_interfaces_snapshot/lib/python3.12/site-packages'))\n"
assert raw.count(old) == 1
derived = raw.replace(old, '').replace(str(ROOT / 'evidence/replay01/protocol'), str(OUT))
target = OUT / source.name
with target.open('x') as stream:
    stream.write(derived)
sys.dont_write_bytecode = True
runpy.run_path(str(target), run_name='__main__')
result = json.loads((OUT / 'validate_t2b_p01_result.json').read_bytes())
assert result['Stored']['CDR_decoded'] is True
assert result['protected_run_files_unchanged'] is True
for name in ['API_full_stream', 'typed_Source_Stored', 'capability_Source_Stored',
             'wire_GID_Stored', 'recorder_fixture_counts', 'observed_four_role_rc0_group_empty_no_errors']:
    assert result['common_checks'][name]['passed'] is True, name
from usv_research_interfaces.msg import ExecutionDecision
assert hasattr(ExecutionDecision(), 'activation_odom_stamp_ns')
paths = set()
for row in Path('/proc/self/maps').read_text().splitlines():
    name = row.split()[-1]
    if name.startswith('/') and 'usv_research_interfaces' in name and '.so' in name:
        paths.add(name)
assert paths and all('/home/trevor/USV/usv_mpc_ws/' in p for p in paths)
provenance = {'schema': 'M4-review-workspace-CDR-provenance-v82',
              'ExecutionDecision_has_activation_odom_stamp_ns': True,
              'Python_modules': {k: getattr(v, '__file__', None) for k, v in sys.modules.items()
                                 if k.startswith('usv_research_interfaces')},
              'native_type_support': {p: {'sha256': hashlib.sha256(Path(p).read_bytes()).hexdigest(),
                                        'bytes': Path(p).stat().st_size} for p in sorted(paths)},
              'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'derived_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
              'changes': 'remove old snapshot Python insertion; relocate output only',
              'previous_failure_preserved': 'evidence/replay01/protocol/validate_t2b_p01_result.json',
              'no_ROS_init': True, 'owned_runs': 0,
              'full_workspace_decode_and_selected_checks_passed': True}
with (OUT / 'environment_provenance.json').open('x') as stream:
    stream.write(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n')
