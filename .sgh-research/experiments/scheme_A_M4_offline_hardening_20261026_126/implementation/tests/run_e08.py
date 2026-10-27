import json,sys
from pathlib import Path
from offline_support import Evidence,ROOT,pin,save
sys.path.insert(0,str(ROOT/'implementation/audit'))
from t3_bounded_rejudge_v2 import rejudge,rows
e=Evidence('E08',sys.argv[1]);shadow=ROOT/'implementation/author/observer/src/shadow'
test=ROOT/'implementation/tests/test_sink_sticky_v2.cpp';binary=e.out/'sticky'
save(e.out/'registration.json',{'cases':['T3V-STICKY-01','T3V-STICKY-02','T3V-SURVIVOR-DOC','T3V-C12-REJUDGE','T3V-A101-PROVENANCE'],'sink':pin(shadow/'p1_diag_sink.hpp'),'signals_sent':0,'owned_runs':0})
r=e.command('build_sticky',['g++','-std=c++17','-O2','-I',shadow,test,'-pthread','-o',binary]);e.check('build.sticky',r.returncode==0)
if r.returncode==0:
 r=e.command('sticky',[binary,e.out/'sticky_run'],timeout=10)
 p=e.out/'sticky_run/result.json';d=json.loads(p.read_text())if p.is_file()else{}
 e.check('T3V-STICKY-01',r.returncode==0 and d.get('post_drain_add')is True and d.get('failed_sticky')is True)
 data=rows(e.out/'sticky_run/source.jsonl');summary=data[-1]
 e.check('T3V-STICKY-02',summary['normal_source_complete']is False and summary['generated']==4 and summary['emitted']==3 and summary['dropped']==1 and len(data)==4,summary)
d=rejudge();save(e.out/'historical_rejudge.json',d)
e.check('T3V-C12-REJUDGE',all(d[tag]['all_expected_facts']for tag in ['C12','C3']))
e.check('T3V-SURVIVOR-DOC',all(d['survivor_source'][key]is True for key in ['signal_handler_only_sets_stop','fork_reached_from_main','fd_range_3_to_255','fork_failure_not_handled']))
e.check('T3V-A101-PROVENANCE',bool(d['audit101_provenance']['independently_recomputed'])and bool(d['audit101_provenance']['referenced_harness_or_runner'])and d['audit101_provenance']['current_host_pid_probe_used']is False)
result=e.finish(sink_business_implementation_modified=False,all_fd_cleanup=False,generic_restart_proof=False,source_summary_scope='qualification remains failed after later enqueue succeeds')
sys.exit(0 if result['status']=='PASS'else 2)
