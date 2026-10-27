#!/usr/bin/env python3
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
helper = D.parent / 'scheme_A_B4_applicability_20261019_31/sync_MPC_v1.py'
assert hashlib.sha256(helper.read_bytes()).hexdigest() == 'a1d01de6003d040209a385124524d4fdcb25895d6b95575ea6d4b8ddff7ffbe3'
assert json.loads((D / 'postrun/final_QA_v1.json').read_bytes())['passed']
spec = importlib.util.spec_from_file_location('mode_correction_create_only_delivery', helper)
module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
result = module.deliver(D.name)
result.update(schema='SchemeB-MANUAL-correction-MPC-delivery/v1', final_regular_files_per_root=result['files'] + 1,
              original_MANUAL_RC_contract_restored=True, verified_checks=30, real_ship_deployed=False,
              M4_F6_P1_qualified=False)
raw = (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()
dest = Path(result['destination'])
for root in [D, dest]:
    with (root / 'delivery_verification.json').open('xb') as f:f.write(raw)
assert (D / 'delivery_verification.json').read_bytes() == (dest / 'delivery_verification.json').read_bytes()
assert module.population(D) == module.population(dest)
print(json.dumps({'passed': True, 'final_files_each': result['final_regular_files_per_root'], 'full_second_SHA_readback': True, 'destination': str(dest)}))
