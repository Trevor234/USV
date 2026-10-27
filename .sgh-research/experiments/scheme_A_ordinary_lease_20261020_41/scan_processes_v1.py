"""Read-only /proc identity population; never signal an unowned process."""
from pathlib import Path
import argparse,json,time
D=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);a=ap.parse_args()
roles={r['binary'] for r in json.loads((D/'author/build_manifest_current.json').read_bytes())}
found=[];denied=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:
        exe=str((p/'exe').resolve(strict=True))
        if exe in roles or Path(exe).name.startswith(('p1_controlled_phase_','p1_regulator_shadow_','p1_solver_worker_','p1_owned_recorder')):
            found.append(dict(pid=int(p.name),exe=exe,stat=(p/'stat').read_text(),status=(p/'status').read_text()))
    except (ProcessLookupError,FileNotFoundError):pass
    except PermissionError:denied.append(int(p.name))
report=dict(selected_research_processes=found,unreadable_process_ids=denied,read_only=True,checked_ns=time.monotonic_ns(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
with Path(a.output).open('x') as f:json.dump(report,f,indent=2)
print(json.dumps(dict(selected_research_processes=len(found),unreadable_processes=len(denied),no_signal_sent=True)))
