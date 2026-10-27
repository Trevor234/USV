"""Read-only source/actual MCAP proof of live process loss and finite receipt lease."""
from collections import Counter
import argparse,json
from pathlib import Path
from owned_process_supervisor import sha256_file
from check_regulator_fault_matrix import scan
from check_p1_execution import JOB_ALIASES,CANDIDATE_ALIASES,CANDIDATE_FIELDS,DECISION_ALIASES,DECISION_V2_FIELDS
from p1_payload_digest import canonical_payload_digest

def mechanism(context,summary,reg,fixture,decisions,jobs,caps):
    issues=[]
    def require(ok,why):
        if not ok:issues.append(why)
    fault=summary.get('fault')
    if not fault:return {'issues':['fault missing'],'mechanism_complete':False,'gap_reproduced':False}
    at=fault['ns'];samples=[e for e in fixture if e['type']=='stopped_live_sample']
    end=next((e['ns'] for e in fixture if e['type']=='stopped_observation_end'),0)
    resume=next((e['ns'] for e in fixture if e['type']=='declared_owned_continue'),0)
    resume_end=next((e['ns'] for e in fixture if e['type']=='resume_observation_end'),0)
    require(end-at>=1_800_000_000 and resume_end-resume>=800_000_000,'finite observation windows absent')
    require(len(samples)>=12 and all(e['identity']['state'] in ('T','t') and e['identity']['pid']==fault['pid'] and e['identity']['start_ticks']==fault['process_identity']['start_ticks'] for e in samples),'live stopped identity not proven')
    require(context['scenario']=='active_stop' and fault['active_job']>0 or context['scenario']!='active_stop' and fault['active_job']==0 and fault['pending_count']==0,'declared active/idle state absent')
    require(any(d['accepted'] and d['activation_commit_ns']<at for d in decisions) if context['scenario']!='active_stop' else bool(jobs),'actual normal prefix absent')
    post=[d for d in decisions if at<=d['activation_commit_ns']<end]
    transitions=[e for e in reg if e['type']=='worker_unusable_transition' and at<=e['processed_ns']<end]
    require(len(post)>=8,'insufficient stopped control ticks')
    if context['policy_mode']=='observe_old':
        require(context['scenario']=='idle_stop','old observation scope is idle only')
        gap=not transitions and any(j['submit_commit_ns']>=at+1_200_000_000 and j['submit_commit_ns']<end for j in jobs)
        require(gap,'prospective idle loss gap not reproduced')
        return {'issues':issues,'mechanism_complete':False,'gap_reproduced':gap and not issues,
                'observation_evidence_complete':not issues,'new_commits_after_1_2s':sum(at+1_200_000_000<=j['submit_commit_ns']<end for j in jobs),'stopped_decisions':len(post)}
    admissions=[e for e in reg if e['type']=='capability_admission']
    require(bool(admissions),'validated capability receipt source absent')
    require(len(transitions)==1,'single terminal lease transition absent')
    if len(transitions)!=1:return {'issues':issues,'mechanism_complete':False,'gap_reproduced':False}
    t=transitions[0];terminal=t['check_ns'];last=t['capability_last_valid_commit_ns'];lease=t['capability_timeout_ns']
    require(t['reason']=='worker_capability_expired' and lease==600_000_000,'terminal receipt lease cause/identity differs')
    require(lease<terminal-last<=lease+220_000_000,'lease observed outside declared expiration/tick bound')
    require(t['candidate_after'] is False and t['pending_after'] is False,'terminal invalidation absent')
    valid=[e for e in admissions if e['renewed']]
    require(len(valid)>=2 and valid[-1]['validation_commit_ns']==last,'last actual valid renewal differs')
    require(all(e['valid'] and not e['terminal_run'] for e in valid),'invalid or terminal capability renewed lease')
    require(not any(e['renewed'] and e['validation_commit_ns']>=terminal for e in admissions),'lease revived after terminal')
    require(not any(j['submit_commit_ns']>terminal for j in jobs),'new job commit after terminal observation')
    require(not any(d['accepted'] and d['activation_commit_ns']>=terminal for d in decisions),'candidate activated after terminal')
    stable=[d for d in post if d['activation_commit_ns']>=t['processed_ns']]
    require(len(stable)>=5 and all(d['reason']=='worker_unusable' and not d['accepted'] for d in stable),'post-terminal stopped decisions absent')
    resumed=[d for d in decisions if resume<=d['activation_commit_ns']<resume_end]
    require(len(resumed)>=3 and all(d['reason']=='worker_unusable' and not d['accepted'] for d in resumed),'same-run response recovery reactivated worker')
    later=[e for e in admissions if e['validation_commit_ns']>=resume and e['valid']]
    require(bool(later) and all(e['terminal_run'] and not e['renewed'] for e in later),'actual renewed messages after SIGCONT not quarantined')
    injections=[e for e in fixture if e['type']=='invalid_capability_injection']
    if context['scenario']=='invalid_capability_stop':
        require(len(injections)>=12,'declared invalid capability stream missing')
        base=next((e['payload_sha256'] for e in fixture if e['type']=='invalid_capability_base'),None)
        originals=[m for m in caps if canonical_payload_digest(m)==base]
        require(bool(originals),'actual original capability used for injection absent')
        hashes=Counter(e['payload_sha256'] for e in injections)
        actual_bad=[m for m in caps if m['backend']=='invalid']
        require(hashes==Counter(canonical_payload_digest(m) for m in actual_bad),'invalid capability declaration/actual multiset differs')
        if originals:
            expected=dict(originals[0]);expected['backend']='invalid'
            require(all(m==expected for m in actual_bad),'undeclared invalid capability field changed')
        ignored=[e for e in admissions if at<=e['validation_commit_ns']<end and e['capability']['backend']=='invalid']
        require(len(ignored)==len(injections) and all(not e['valid'] and not e['renewed'] and e['lease_last_before_ns']==e['lease_last_after_ns'] for e in ignored),'invalid packets renewed or not accounted')
    else:require(not injections,'unexpected declared capability injection')
    return {'issues':issues,'mechanism_complete':not issues,'gap_reproduced':False,'terminal_source_invalidation_proven':True,
            'last_valid_commit_ns':last,'terminal_check_ns':terminal,'lease_age_ms':(terminal-last)/1e6,'fault_to_terminal_ms':(t['processed_ns']-at)/1e6,
            'post_terminal_stopped_decisions':len(stable),'post_resume_decisions':len(resumed),'post_resume_valid_capabilities_quarantined':len(later),
            'invalid_capability_injections':len(injections),'capability_source_freshness_available':False}

def check(directory):
    output=directory/'verification_live_loss_v1'
    if output.exists():raise FileExistsError('create-only verification')
    tracked={str(p):sha256_file(p) for p in directory.rglob('*') if p.is_file()}
    def j(name):return json.loads((directory/name).read_text())
    def lines(name):
        b=(directory/name).read_bytes()
        if not b.endswith(b'\n'):raise ValueError('unclosed source '+name)
        return [json.loads(v) for v in b.decode().splitlines()]
    context=j('run_context.json');summary=j('runner_summary.json');fixture=lines('fixture_source.jsonl');reg=lines('regulator_source.jsonl');ledger=lines('owned_process_ledger.jsonl')
    c=json.loads(Path(context['contract_file']).read_text());data=scan(directory/'raw_bag',context['topics'])
    msgs=lambda topic:[e['message'] for e in data[topic]]
    b=(directory/'worker_source.jsonl').read_bytes();partial=not b.endswith(b'\n');worker=[json.loads(v) for v in b[:b.rfind(b'\n')+1].decode().splitlines()]
    issues=[]
    def require(ok,why):
        if not ok:issues.append(why)
    require(summary['failure'] is None and summary['cleanup_complete'] and summary['supervision_evidence_complete'],'runner/cleanup/source failure')
    require(summary['zero_physical_endpoints'] and summary['graph_samples']>0 and context['production_regulator_present'],'real production/zero physical graph absent')
    require(context['asset_precheck']['drift']==summary['asset_postcheck']['drift']==[],'asset drift')
    for name in ('regulator','worker','recorder'):
        require(summary['cleanup'].get(name,{}).get('remaining_members')==[],'owned residual '+name)
        sp=[e for e in ledger if e['type']=='spawn' and e['name']==name]
        require(len(sp)==1 and sp[0]['executable_verified'],'actual executable binding absent '+name)
        if name!='recorder' and sp:require(sp[0]['expected_sha256']==context['binaries'][name]['sha256'],'actual binary differs '+name)
    require(any(e['type']=='signal' and e['name']=='worker' and e['signal']==19 for e in ledger) and any(e['type']=='signal' and e['name']=='worker' and e['signal']==18 for e in ledger),'owned STOP/CONT not proven')
    for topic in ('/p1/solve_job','/p1/solve_candidate','/p1/execution_decision','/p1/worker_capability'):
        observed=Counter(e['payload_sha256'] for e in fixture if e['type']=='observed' and e['topic']==topic)
        require(observed==Counter(e['payload_sha256'] for e in data[topic]),'observer/actual full content differs '+topic)
    for kind in ('clock','odom','imu','path','profile'):
        topic='/clock' if kind=='clock' else c['input_topics'][kind]
        pubs=Counter(e['payload_sha256'] for e in fixture if e['type'] in ('input_publish','reference_publish') and e['kind']==kind)
        require(pubs==Counter(e['payload_sha256'] for e in data[topic]),'input/actual content differs '+kind)
    sj=[e for e in reg if e['type']=='job'];sd=[e for e in reg if e['type']=='decision'];sc=[e for e in worker if e['type']=='candidate']
    jobs=msgs('/p1/solve_job');decisions=msgs('/p1/execution_decision');candidates=msgs('/p1/solve_candidate');caps=msgs('/p1/worker_capability')
    require((len(sj),len(sd))==(len(jobs),len(decisions)),'job/decision source count differs')
    for e,m in zip(sj,jobs):require(e['job']=={JOB_ALIASES.get(k,k):v for k,v in m.items()},'full job differs')
    for e,m in zip(sd,decisions):require(all(e.get(DECISION_ALIASES.get(k,k))==m[k] for k in DECISION_V2_FIELDS),'full decision differs')
    for e,m in zip(sc,candidates):
        require(e['job']=={JOB_ALIASES.get(k,k):v for k,v in m['job'].items()} and all(e[CANDIDATE_ALIASES.get(k,k)]==m[k] for k in CANDIDATE_FIELDS),'full native candidate prefix differs')
    active=context['scenario']=='active_stop'
    unknown=[]
    if active:
        require(summary['cleanup']['worker']['returncode']==-9,'controlled busy worker KILL cleanup absent')
        unknown=['worker_terminal_summary_missing','worker_source_completeness_unknown','worker_flush_success_unproven']
        if partial:unknown.append('worker_source_partial_last_line_preserved')
    else:
        require(len(sc)==len(candidates) and not partial,'normal resumed worker source count/closure differs')
        ends=[e for e in worker if e['type']=='worker_summary']
        require(len(ends)==1 and ends[0]['normal_source_complete'] and 'WORKER_CLOSE_FLUSH_SUCCESS=true' in (directory/'worker.console.log').read_text(),'normal worker close/flush unproven')
    ends=[e for e in reg if e['type']=='source_summary']
    require(len(ends)==1 and ends[0]['normal_source_complete'] and ends[0]['dropped']==0 and 'REGULATOR_CLOSE_FLUSH_SUCCESS=true' in (directory/'regulator.console.log').read_text(),'regulator source/flush incomplete')
    require(all(m['pid']==summary['worker_pid'] and m['worker_instance']==summary['worker_instance'] and m['boot_id']==context['boot_id'] and m['contract_hash']==context['contract_hash'] for m in caps),'foreign actual capability')
    if context['policy_mode']=='enforce_lease':
        admissions=[e for e in reg if e['type']=='capability_admission']
        actual_caps=Counter(e['payload_sha256'] for e in data['/p1/worker_capability'])
        admitted_caps=Counter(canonical_payload_digest(e['capability']) for e in admissions)
        # Recording starts before regulator subscription; v1 lacks packet seq.
        # Match every processed callback payload, without claiming raw prefix
        # packets were processed or proving source freshness/replay resistance.
        require(not (admitted_caps-actual_caps),'processed capability content absent from actual bag')
    result=mechanism(context,summary,reg,fixture,sd,sj,caps);result['issues']=issues+result['issues']
    gate=result['gap_reproduced'] if context['policy_mode']=='observe_old' else result['mechanism_complete']
    result.update(schema='p1-live-worker-loss-check-v1',run_id=context['run_id'],scenario=context['scenario'],policy_mode=context['policy_mode'],
                  evidence_accounting_complete=not issues,selected_gate_passed=gate and not result['issues'],
                  actual_topic_counts={k:len(v) for k,v in data.items()},source_typed_counts={'job':len(sj),'candidate':len(sc),'decision':len(sd)},
                  unknown=unknown,evidence_sha256=tracked,normal_contract_complete=False,execute_qualified=False)
    if context['policy_mode']=='enforce_lease':result['raw_capability_packets_without_processed_counterpart']=sum((actual_caps-admitted_caps).values())
    if any(sha256_file(Path(p))!=v for p,v in tracked.items()):raise RuntimeError('evidence changed during scan')
    output.mkdir()
    with (output/'live_worker_loss_check.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='evidence_sha256'}))
    return 0 if result['selected_gate_passed'] else 2

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    raise SystemExit(check(p.parse_args().directory))
