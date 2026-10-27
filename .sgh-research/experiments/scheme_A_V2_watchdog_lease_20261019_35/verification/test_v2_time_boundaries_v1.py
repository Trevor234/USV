from pathlib import Path
import json
import sys
sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(D / 'implementation'))
from audit_v2_core_v1 import timing_accepts
origin = 10_000_000_000
cases = [
 ('lease_equal_not_expired', 'lease', origin, origin+600_000_000, origin, 'worker_capability_expired', False),
 ('lease_strictly_expired', 'lease', origin, origin+600_000_001, origin, 'worker_capability_expired', True),
 ('lease_wrong_cause', 'lease', origin, origin+900_000_000, origin, 'active_watchdog', False),
 ('active_equal_not_expired', 'active', origin, origin+1_000_000_000, origin+800_000_000, 'active_watchdog', False),
 ('active_strictly_expired', 'active', origin, origin+1_000_000_001, origin+800_000_000, 'active_watchdog', True),
 ('active_lease_equal_still_valid', 'active', origin, origin+1_100_000_000, origin+500_000_000, 'active_watchdog', True),
 ('active_lease_expired_reject', 'active', origin, origin+1_100_000_000, origin+499_999_999, 'active_watchdog', False),
 ('active_wrong_cause', 'active', origin, origin+1_100_000_000, origin+900_000_000, 'worker_capability_expired', False),
 ('future_receipt', 'lease', origin, origin-1, origin, 'worker_capability_expired', False),
 ('boolean_is_not_timestamp', 'active', True, origin+1_100_000_000, origin, 'active_watchdog', False),
 ('unknown_profile', 'normal', origin, origin+1_100_000_000, origin, 'active_watchdog', False),
 ('lease_origin_not_last_valid', 'lease', origin, origin+900_000_000, origin+1, 'worker_capability_expired', False),
]
out=[]
for name, case, start, end, last, reason, expected in cases:
 actual=timing_accepts(case,start,end,last,reason)
 assert actual is expected, name
 out.append({'case':name,'passed':True,'admitted':actual})
with (D/'verification/V2_time_boundaries_v1.json').open('x') as f:json.dump({'passed':True,'cases':out,'actual_control_runs':0},f,indent=2)
print(json.dumps({'passed':True,'cases':len(out)}))
