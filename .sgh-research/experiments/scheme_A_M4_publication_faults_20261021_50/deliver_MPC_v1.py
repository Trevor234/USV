#!/usr/bin/env python3
"""Create-only sealed50 delivery using the pinned two-readback archive copier."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent
helper = D.parent / 'scheme_A_B4_applicability_20261019_31/sync_MPC_v1.py'
assert hashlib.sha256(helper.read_bytes()).hexdigest() == 'a1d01de6003d040209a385124524d4fdcb25895d6b95575ea6d4b8ddff7ffbe3'
qa = json.loads((D / 'postrun/final_QA_v1.json').read_bytes())
assert qa['passed'] and qa['source_linked_publication_exit_component_qualified'] and not qa['M4_stage_qualified']
spec = importlib.util.spec_from_file_location('pinned_create_only_MPC_delivery50', helper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
result = module.deliver(D.name)
result.update(schema='SchemeA-batch50-MPC-delivery/v1', final_regular_files_per_root=result['files'] + 1,
              source_linked_publication_exit_component_qualified=True,
              actual_component_cases=16, actuator_topic_publishers=0, new_full_M4_fault_runs=0,
              stage_qualified=False, M4_stage_qualified=False, F6_qualified=False, P1_qualified=False,
              ordinary_production_release_enabled=False, research_conclusion=False)
data = (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
dest = Path(result['destination'])
for root in [D, dest]:
    with (root / 'delivery_verification.json').open('xb') as f:
        f.write(data)
assert (D / 'delivery_verification.json').read_bytes() == (dest / 'delivery_verification.json').read_bytes() == data
assert module.population(D) == module.population(dest)
print(json.dumps({'passed': True, 'final_regular_files_per_root': result['final_regular_files_per_root'],
                  'full_second_SHA_readback': True, 'destination': str(dest),
                  'delivery_verification_sha256': hashlib.sha256(data).hexdigest()}))
