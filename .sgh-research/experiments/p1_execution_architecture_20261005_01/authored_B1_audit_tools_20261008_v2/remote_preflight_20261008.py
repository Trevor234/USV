from pathlib import Path
import hashlib,json,sys,os
E=Path('/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01')
R=E/'authored_runtime_v30_contract_20261007';G=E/'contract_B0_closed_assets_20261007.json'
sys.path.insert(0,str(R))
from run_worker_fault_matrix import verify_assets
from run_formal_no_output_validation import host_preflight
from owned_process_supervisor import proc_table
assert hashlib.sha256(G.read_bytes()).hexdigest()=='bc0e932313852ff046b748f9cfa4292d27b5320aea5177a5ef6a20bbff8b1de8'
h=host_preflight();extra=[]
for item in proc_table():
    if item['pid']==os.getpid() or item['state']=='Z':continue
    try:args=(Path('/proc')/str(item['pid'])/'cmdline').read_bytes().split(b'\0')
    except FileNotFoundError:continue
    names={Path(v.decode(errors='replace')).name for v in args[:3] if v}
    if 'p1_regulator_r5_diag' in names or ('run_r5_diag_validation.py' in names and b'--fixture-child' in args):extra.append(item)
assert not extra,extra
print(json.dumps({'schema':'p1-B1-preflight-v1','date':'2026-10-08','host':h,'additional_diag_processes':extra,'guard':verify_assets(G),'new_ROS_run':False,'physical_release':False}))
