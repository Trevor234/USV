#!/usr/bin/env python3
"""Create-only current delivery; all prior MPC archives stay untouched."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
helper = D.parent / 'scheme_A_B4_applicability_20261019_31/sync_MPC_v1.py'
assert hashlib.sha256(helper.read_bytes()).hexdigest() == 'a1d01de6003d040209a385124524d4fdcb25895d6b95575ea6d4b8ddff7ffbe3'
spec = importlib.util.spec_from_file_location('pinned_create_only_MPC_delivery', helper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
submission = json.loads((D / 'freeze/freeze_submission_v1.json').read_bytes())
qa = json.loads((D / 'postrun/final_QA_v1.json').read_bytes())
assert qa['passed'] and qa['B5_contract_freeze_qualified'] and qa['M0b_selected_engineering_freeze_qualified']
result = module.deliver(D.name)
result.update(schema='SchemeA-batch47-MPC-delivery/v1', final_regular_files_per_root=result['files'] + 1,
              B5_contract_freeze_qualified=True, M0b_selected_engineering_freeze_qualified=True,
              M4_qualified=False, F6_qualified=False, P1_qualified=False,
              stage_qualified=False, stage_qualified_scope='overall P1',
              physical_execute_release_enabled=False, true_plant_qualified=False, research_conclusion=False,
              freeze_index_sha256=submission['freeze_index_sha256'], frozen_contract_sha256=submission['contract_sha256'])
data = (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
target = Path(result['destination'])
for root in [D, target]:
    with (root / 'delivery_verification.json').open('xb') as stream:stream.write(data)
assert (D / 'delivery_verification.json').read_bytes() == (target / 'delivery_verification.json').read_bytes() == data
assert module.population(D) == module.population(target)
print(json.dumps({'passed': True, 'files': result['files'], 'final_regular_files_per_root': result['final_regular_files_per_root'],
                  'full_second_SHA_readback': True, 'destination': str(target),
                  'delivery_verification_sha256': hashlib.sha256(data).hexdigest()}))
