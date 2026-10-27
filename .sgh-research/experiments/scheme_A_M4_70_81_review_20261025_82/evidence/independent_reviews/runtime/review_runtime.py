import json,hashlib
from pathlib import Path
root=Path('/home/trevor/USV/.sgh-research/experiments')
b76=root/'scheme_A_M4_t2_r1_runtime_20261024_76'
a76=b76/'implementation/t2_author_r1'
a81=root/'scheme_A_M4_t2_r2_driver_20261025_78/implementation/t2_author_r3'
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r=a81/'observer/src/shadow/regulator_owned_execute.cpp'
test=b76/'implementation/r1_harness/tests/test_current_candidate_reference_clock.cpp'
f=a81/'fixture/synthetic_source_m4.cpp'
t=test.read_text();reg=r.read_text();fix=f.read_text()
nom=json.loads((b76/'evidence/harness_gtest.json').read_text())
rows=nom['testsuites'][0]['testsuite'];failures=[x['name'] for x in rows if x.get('failures')]
assert nom['tests']==34 and not failures
assert h(r)==h(a76/'observer/src/shadow/regulator_owned_execute.cpp')
assert 'auto applied=C33MatrixAccess::read_event_once(sink_file,"owned_applied_publication")' in t
assert '{"applied_emitted",true}' in reg
assert '++clock_attempts_;' in fix
record={'schema':'independent-runtime-review-76-to-81-v1','no_ROS_or_owned_started':True,'regulator_76_and_current_identical':True,'regulator_sha256':h(r),'component_record':{'tests':nom['tests'],'failures_field':nom['failures'],'individual_failures':failures,'note':'read and verified preserved GTest JSON; did not re-run ROS linked harness'},'positive':[
'pause schedule bump, origin/tick/last_schedule updated under same mutex; witness rules not loosened',
'API/Applied precede anchor consistency comparison; actual divergence remains explicit fail-closed',
'current actual Witness header replay rejects old T2A_14 with precise consistency reason and no first_failure code; counterfactual tick-only repair permits witness structural check (not new run)'
],'findings':[
{'id':'R76-review-1','priority':2,'file':str(r),'lines':[1235,1246,1272],'title':'applied_emitted fact is hardcoded despite caught Applied publish failure','evidence':'emit_owned_applied returns void and catches publication failure; consistency_failed later always says applied_emitted=true','reproducer':'probe_pair.py copies actual owned_pair_record body with stubbed dependencies and failed emit; pair_controlflow_probe.json simultaneously records publication_failed and applied_emitted=true','limit':'offline controlflow probe, not ROS publish failure injection','fix':'return actual attempt/result from emit_owned_applied and record only that; preserve failure terminal path'},
{'id':'R76-review-2','priority':2,'file':str(test),'lines':[837,875],'title':'named seq12 regression does not bind assertions to deliberately diverged target pair','evidence':'calls owned_pair_record directly, bypasses publish-side anchor update; first pair already differs. reads first Applied and first divergence, not target sequence2; second d.publish timestamps are unchanged while actual.calls advance','fix':'drive publish via injectable actual-send seam; require exact sequence2 API/Applied and divergence; prove seq1 agreed; target-emit-deletion mutation must fail'},
{'id':'R76-review-3','priority':3,'file':str(f),'lines':[242,243],'title':'clock_publish_attempts counts silent skipped steps','evidence':'counter increments before silent branch; misleading as real API attempt and disagrees with document silent counters not incremented','fix':'increment at actual call attempt or rename model-clock slots; retain clock_publish_returned and skipped count separately'}
],'limits':['No live pause/resume witness continuity proof was added by this review; original report accurately defers it to T2A re-evidence','OutputAuthority record_pair still precedes API fact ledger and has timing contract preconditions; production monotonic serial wrapper normally satisfies those; no demonstrated current runtime failure from that ordering','history mapping regression source remains; current fix preserves facts and controlled stop, not healthy resume/new-epoch service recovery']}
Path('/tmp/review76_runtime/review_summary.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(record,ensure_ascii=False,indent=2))
