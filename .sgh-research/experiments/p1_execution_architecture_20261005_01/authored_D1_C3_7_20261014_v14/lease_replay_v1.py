"""Independent finite replay of the original Capability callback and receipt lease.

No ROS imports. Source order and original commit times are evidence coordinates;
they do not create a total order between unrelated diagnostic writers. A callback
receipt is not a packet identifier, freshness claim, or native solve progress.
"""
from __future__ import annotations
import copy
import math

FIELDS=set(('schema_version run_id boot_id contract_hash nominal_hash worker_instance clock_name backend '
            'matrix_layout horizon_steps prediction_dt pid startup_ns completed_jobs active_job pending_count '
            'fault_injection_enabled fatal reason').split())
STRING_LIMITS=dict(schema_version=64,run_id=128,boot_id=64,contract_hash=64,nominal_hash=64,
    worker_instance=64,clock_name=32,backend=16,matrix_layout=32,reason=256)
INTEGER_DOMAINS=dict(horizon_steps=(0,2**32-1),pid=(-2**63,2**63-1),startup_ns=(-2**63,2**63-1),
    completed_jobs=(0,2**64-1),active_job=(0,2**64-1),pending_count=(0,2**32-1))
LEASE_TERMINALS={'worker_capability_expired','worker_capability_clock_invalid'}


def exact_payload(cap):
    return (type(cap) is dict and set(cap)==FIELDS and
        all(type(cap[k]) is str for k in STRING_LIMITS) and
        all(type(cap[k]) is int and lo<=cap[k]<=hi for k,(lo,hi) in INTEGER_DOMAINS.items()) and
        type(cap['prediction_dt']) is float and math.isfinite(cap['prediction_dt']) and
        all(type(cap[k]) is bool for k in ('fault_injection_enabled','fatal')))


def resource_violation(cap):
    for name,limit in STRING_LIMITS.items():
        observed=len(cap[name].encode('utf-8'))
        if observed>limit:
            return {'reason':'resource_string_oversize','field':'capability.'+name,'observed':observed,'limit':limit}
    return None


class LeaseReplay:
    def __init__(self,expected,timeout_ns):
        if type(timeout_ns) is not int or not 200_000_000<=timeout_ns<=5_000_000_000:
            raise ValueError('lease timeout outside original finite bounds')
        self.expected=copy.deepcopy(expected);self.timeout=timeout_ns
        self.last=0;self.instance='';self.worker_valid=False;self.terminal=False
        self.reason='';self.lease_reason='';self.last_capability=None;self.last_commit=0

    def state(self):
        return dict(last_valid_ns=self.last,worker_instance=self.instance,worker_valid=self.worker_valid,
            worker_unusable=self.terminal,last_capability=copy.deepcopy(self.last_capability),
            last_capability_commit_ns=self.last_commit,terminal_reason=self.reason)

    def terminate(self,reason):
        if not self.terminal:
            self.terminal=True;self.worker_valid=False;self.reason=reason

    def lease_check(self,now):
        if not self.lease_reason:
            if type(now) is not int or now<=0 or (self.last and now<self.last):
                self.lease_reason='worker_capability_clock_invalid'
            elif self.last and now-self.last>self.timeout:
                self.lease_reason='worker_capability_expired'
        return self.lease_reason

    def check(self,now):
        if not self.terminal:
            reason=self.lease_check(now)
            if reason:self.terminate(reason)
        return self.state()

    def callback(self,cap,now):
        if not exact_payload(cap):raise ValueError('Capability exact full19 payload required')
        resource=resource_violation(cap)
        before=self.state()
        if resource:
            return dict(resource=resource,before=before,after=self.state(),renewed=False,
                        identity_valid=None,valid=None,terminal_run=self.terminal)
        # Original resource failure returns before this check; valid or invalid
        # resource-admitted callbacks both check the old lease before renewal.
        self.check(now)
        identity=all(cap[k]==self.expected[k] for k in ('run_id','boot_id','contract_hash','nominal_hash','pid'))
        valid=(identity and cap['schema_version']=='p1-worker-capability-v1' and
            cap['clock_name']=='CLOCK_MONOTONIC' and cap['backend']=='acados' and
            cap['matrix_layout']=='column_major' and cap['horizon_steps']==20 and
            cap['prediction_dt']==.2 and not cap['fatal'] and bool(cap['worker_instance']) and
            cap['startup_ns']>0 and cap['fault_injection_enabled']==self.expected['fault_injection_enabled'])
        renewed=False
        if identity:
            if self.instance and self.instance!=cap['worker_instance']:self.terminate('worker_instance_changed')
            if cap['fatal']:self.terminate('fatal_capability')
            if valid and not self.terminal:
                if not self.lease_check(now):
                    self.last=now;self.instance=cap['worker_instance'];self.worker_valid=True
                    self.last_capability=copy.deepcopy(cap);self.last_commit=now;renewed=True
                else:self.terminate(self.lease_reason)
        return dict(resource=None,before=before,after=self.state(),identity_valid=identity,
            valid=valid,renewed=renewed,terminal_run=self.terminal)


def replay(rows,expected,timeout_ns,need,*,decode_raw=None,require_observation=False):
    """Replay source callbacks and externally observed terminal checks.

    Capability-induced terminal rows occur before their admission row under the
    same original mutex; their matching check_ns is replayed from the payload,
    rather than trusted as an external event. All other terminal observations
    are independently checked where the reason has lease semantics. Other
    liveness/source terminals retain their explicit limited evidence scope.
    """
    machine=LeaseReplay(expected,timeout_ns);timeline=[];proof=[]
    admissions=[r for r in rows if r.get('type')=='capability_admission']
    commits={r.get('validation_commit_ns') for r in admissions}
    deferred={};callback_seq=0;last_now=0
    for index,row in enumerate(rows):
        typ=row.get('type')
        if typ=='worker_unusable_transition':
            now=row.get('check_ns');reason=row.get('reason')
            need(type(now) is int and now>0,'lease_transition_exact_time',source_index=index)
            if now in commits and reason in LEASE_TERMINALS|{'worker_instance_changed','fatal_capability'}:
                deferred.setdefault(now,[]).append(row);continue
            before=machine.state()
            if reason in LEASE_TERMINALS:
                machine.check(now);need(machine.terminal and machine.reason==reason,
                    'lease_external_terminal_independent_reason',source_index=index)
            else:machine.terminate(reason)
            need(row.get('capability_last_valid_commit_ns')==before['last_valid_ns'] and
                row.get('capability_timeout_ns')==timeout_ns,'lease_terminal_last_valid_binding',source_index=index)
            timeline.append((now,machine.state()));continue
        resource_row=typ=='resource_rejected' and row.get('interface')=='capability'
        if typ!='capability_admission' and not resource_row:continue
        raw=row.get('raw_input');cap=row.get('capability')
        if raw is not None:
            callback_seq+=1
            need(type(raw.get('callback_sequence')) is int and raw['callback_sequence']==callback_seq,
                'capability_raw_callback_sequence',source_index=index)
            if decode_raw is not None:
                decoded=decode_raw(raw,index)
                if cap is not None:need(decoded==cap,'capability_callback_raw_full19_binding',source_index=index)
                cap=decoded
        elif require_observation:need(False,'capability_raw_callback_missing',source_index=index)
        if cap is None:
            # Historical resource rows omitted payload/raw. They cannot become
            # general-replay coverage; normal-only compatibility is separate.
            need(False,'capability_resource_payload_unavailable',source_index=index);continue
        need(exact_payload(cap),'capability_replay_exact_full19_types',source_index=index)
        if not exact_payload(cap):continue
        now=row.get('validation_commit_ns',row.get('receive_ns'))
        if resource_row:
            result=machine.callback(cap,now)
            need(result['resource'] is not None and row.get('renewed') is False,
                 'capability_resource_original_early_return',source_index=index)
            if result['resource']:
                for key in ('reason','field','observed','limit'):
                    need(row.get(key)==result['resource'][key],'capability_resource_independent_bound',field=key,source_index=index)
            proof.append(dict(source_index=index,resource_rejected=True,state=machine.state()));continue
        need(type(now) is int and now>0 and now>=last_now and type(row.get('receive_ns')) is int and
             0<row['receive_ns']<=now,'capability_replay_callback_time',source_index=index)
        last_now=now;result=machine.callback(cap,now)
        need(result['resource'] is None,'capability_admitted_resource_violation',source_index=index)
        for field in ('identity_valid','valid','renewed','terminal_run'):
            need(type(row.get(field)) is bool and row[field] is result[field],
                 'capability_independent_'+field,source_index=index)
        need(type(row.get('lease_last_before_ns')) is int and row['lease_last_before_ns']==result['before']['last_valid_ns'] and
            type(row.get('lease_last_after_ns')) is int and row['lease_last_after_ns']==result['after']['last_valid_ns'] and
            type(row.get('lease_timeout_ns')) is int and row['lease_timeout_ns']==timeout_ns,
            'capability_independent_before_after',source_index=index)
        need(row.get('source_freshness_available') is False,'capability_no_packet_freshness_claim',source_index=index)
        observation=row.get('lease_observation')
        if observation is not None:
            for phase in ('before','after'):
                want={k:result[phase][k] for k in ('worker_instance','worker_valid','worker_unusable')}
                need(type(observation.get(phase)) is dict and observation[phase]==want and
                    all(type(observation[phase].get(k)) is bool for k in ('worker_valid','worker_unusable')),
                    'capability_independent_'+phase+'_flags_instance',source_index=index)
        elif require_observation:need(False,'capability_same_lock_observation_missing',source_index=index)
        transitions=deferred.pop(now,[])
        if not result['before']['worker_unusable'] and result['after']['worker_unusable']:
            need(len(transitions)==1 and transitions[0]['reason']==result['after']['terminal_reason'],
                 'capability_internal_terminal_independent_reason',source_index=index)
        else:need(not transitions,'capability_unexpected_terminal_transition',source_index=index)
        for t in transitions:
            need(t.get('capability_last_valid_commit_ns')==result['after']['last_valid_ns'] and
                 t.get('capability_timeout_ns')==timeout_ns,'capability_internal_terminal_last_valid',source_index=index)
        timeline.append((now,machine.state()));proof.append(dict(source_index=index,commit_ns=now,
            resource_rejected=False,identity_valid=result['identity_valid'],valid=result['valid'],
            renewed=result['renewed'],before=result['before'],after=result['after']))
    need(not deferred,'capability_unmatched_deferred_terminal')
    return dict(timeline=timeline,proof=proof,final=machine.state(),callbacks=len(proof),
        last_receipt_used_as_last_valid=False,source_packet_freshness_available=False)


def state_at(result,now):
    out=dict(last_valid_ns=0,worker_instance='',worker_valid=False,worker_unusable=False,
             last_capability=None,last_capability_commit_ns=0,terminal_reason='')
    for ns,state in result['timeline']:
        if ns<=now:out=copy.deepcopy(state)
    return out
