"""Pinned current source snippets and closed-raw finite metrics; never launch ROS."""
from pathlib import Path
import hashlib,json,math,re
D=Path(__file__).resolve().parent.parent;W=D.parent;P=W/'scheme_A_post_lease_fresh_recovery_20261020_42'
PINS={}
def need(v,w):
 if not v:raise ValueError(w)
def raw(p):
 p=Path(p);b=p.read_bytes();f=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest());need(str(p) not in PINS or PINS[str(p)]==f,'changed:'+str(p));PINS[str(p)]=f;return b
def load(p):return json.loads(raw(p))
def pin(p):b=raw(p);return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def lines(p):return [json.loads(x) for x in raw(p).splitlines()]
def dump(p,v):
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def main():
 freeze=load(P/'postrun/selected_profile_evidence_freeze_v1.json');register=load(P/'implementation/current_B4_applicability_v1.json')
 need(freeze['evidence_freeze_completed'] and register['contract_sha256']==freeze['contract']['sha256'],'current evidence freeze')
 registry={r['role']:r for r in load(P/'author/build_manifest_current.json')};author=W/'scheme_A_owned_business_start_20261020_39/author';O=author/'observer/src/shadow'
 authority={}
 for role,row in registry.items():
  bundle=load(row['source_bundle']['path']);need(pin(row['binary'])['sha256']==row['binary_sha256'],'current binary')
  need(pin(row['source_bundle']['path'])['sha256']==row['source_bundle']['sha256'],'current source bundle')
  for f in bundle['files'].values():authority[f['path']]=dict(kind='registered_source_bundle',role=role,expected=dict(bytes=f['bytes'],sha256=f['sha256']))
 deps_path=W/'scheme_A_owned_business_start_20261020_39/build/business_observer_attempt01/compiler_dependency_pins.json'
 deps=load(deps_path)
 for p,f in deps['files'].items():authority.setdefault(p,dict(kind='registered_Observer_compiler_dependency',role='observer',expected=dict(bytes=f['bytes'],sha256=f['sha256'])))
 def snippet(name,path,start,end=None,count=1):
  path=Path(path);need(str(path) in authority,'not current compilation authority:'+str(path));info=authority[str(path)]
  need(pin(path)==info['expected'],'compiled source changed:'+str(path));s=raw(path).decode().splitlines();matches=[i for i,t in enumerate(s) if start in t]
  need(len(matches)>=count,'missing or ambiguous source anchor:'+name);a=matches[count-1]
  b=next(i for i in range(a,len(s)) if end in s[i]) if end else a
  need(b-a<100,'bounded source excerpt')
  return dict(id=name,path=str(path),start_line=a+1,end_line=b+1,source_pin=pin(path),authority=info,
   lines=[dict(line=i+1,text=s[i],sha256=hashlib.sha256(s[i].encode()).hexdigest()) for i in range(a,b+1)])
 pub=next(Path(f) for f,v in authority.items() if v['role']=='publisher' and Path(f).name=='mpc_node.cpp')
 S={}
 def add(name,path,start,end=None):S[name]=snippet(name,path,start,end)
 add('output_publisher_creation',pub,'  vrx_left_pub_ = this->create_publisher','this->get_parameter("vrx_right_thrust_topic").as_string(), 10);')
 add('output_API_calls',pub,'  event.left_publish_start_steady_ns = research_steady_ns();','    event.right_publish_end_steady_ns = research_steady_ns();')
 add('shadow_entry_mode',O/'p1_shadow_entry.hpp','inline void require_shadow_mode')
 add('shadow_publish_early_return',O/'regulator_shadow_observer.cpp','  void publish(p1::Decision & d){','    const p1::publication::Policy policy')
 add('propagation_call',O/'regulator_shadow_observer.cpp','  bool predict(Snapshot & s,int64_t target_sim)','if(mode_!="no_output"&&(!found[0]||!found[1]))return false;return usv_mpc::propagate_publisher_nominal')
 core=Path('/home/trevor/USV/usv_mpc_ws/src/usv_mpc_cpp/include/usv_mpc_cpp/p1_input_core.hpp')
 add('nominal_RK4_history',core,'inline bool propagate_publisher_nominal(','  advance(target);s[2] = normalize_angle(s[2]);return s.allFinite();')
 add('mixed_callbacks',O/'regulator_shadow_observer.cpp','  void odom(const nav_msgs','  void path(const nav_msgs')
 add('source_age_comparison',O/'p1_admission.hpp','inline std::string source_time_check(','struct Limits {')
 add('source_eligibility',O/'regulator_shadow_observer.cpp','  std::string eligible(const Snapshot','    return "";')
 add('capability_latch',O/'p1_capability_lease.hpp','class CapabilityLease {','  int64_t timeout_,last_=0;bool armed_=false;std::string reason_;')
 add('worker_callback_authentication',O/'regulator_shadow_observer.cpp','      const auto authentication=worker_peer_?','    // Resource shape and actual interface GID/pidfd precede bounded full CDR.')
 add('capability_validation_and_renewal',O/'regulator_shadow_observer.cpp','  void capability(const p1::Capability','    sink_->add(admission);if(renewed)')
 add('terminal_transition',O/'regulator_shadow_observer.cpp','  void unusable_locked(','  void check_worker_locked(')
 msg=next(Path(p) for p in authority if Path(p).name=='worker_capability__struct.hpp')
 add('capability_wire_fields',msg,'  using _schema_version_type =','  _reason_type reason;')
 add('rho_hold_state_gate',O/'p1_admission.hpp','inline std::string state_check(','inline uint64_t due_tick')
 add('clock_window',O/'p1_clock_window.hpp','class ClockWindow {','  int64_t last_receive_=0,last_sim_=0;')
 add('clock_epoch_invalidation',O/'regulator_shadow_observer.cpp','  void clock(const rosgraph','  p1::Json worker_callback_snapshot_locked() const')
 add('pause_and_watchdog',O/'regulator_shadow_observer.cpp','        if(clock_receive_&&last_clock_advance_','        s=snapshot_locked(')
 add('activation_history_selection',O/'activation_sensor_history_v1.hpp','inline constexpr const char *policy=', 'struct Selection {')
 add('causal_selection',O/'activation_sensor_history_v1.hpp','Selection select(const Snapshot','template<class Snapshot>void apply(')
 add('publication_per_side_results',O/'publication_result_v1.hpp','inline void apply_channel_result(','struct ShutdownResult')
 add('shutdown_result',O/'publication_result_v1.hpp','inline ShutdownResult shutdown_result(','  return r;')
 add('formal_modes_and_release',O/'p1_full_contract.hpp','inline void validate_contract_mode(','inline nlohmann::json parse_unique_contract')
 add('formal_flags',O/'p1_full_contract.hpp','  contract_require(c.at("fault_injection_enabled")==false','  return ContractProfile::Frozen;')
 add('business_gate_scope',author/'common/business_start_gate_v1.hpp','inline void validate_policy(','  const std::filesystem::path p(path);')
 add('owned_entry_intersection',O/'regulator_shadow_observer.cpp','    p1::shadow::require_shadow_mode(mode_);','    p1::shadow::validate_task_time_entry(c_,mode_);')
 native=raw(W/'scheme_A_owned_business_start_20261020_39/build/business_observer_attempt01/native.log').decode();tests=re.findall(r'^\[       OK \] (.*?) \(',native,re.M);need(len(tests)==38,'current selected Native roster')
 observations=[]
 for profile in freeze['diagnostic_profile_register']:
  R=Path(profile['root']);source=lines(R/'observer/source.jsonl');pubrows=lines(R/'publisher/controlled_source.jsonl');result=load(R/'result.json');a=load(profile['audit']['path']);need(a['passed'],'parent actual audit')
  accepted=[r for r in source if r.get('type')=='decision' and r.get('accepted')];jobs=[r for r in source if r.get('type')=='job'];decisions=[r for r in source if r.get('type')=='decision'];start=min(d['planned_ns'] for d in decisions);finish=max(d['activation_commit_ns'] for d in decisions)
  states=[r['state'] for r in source if r.get('type')=='odom_admission' and r.get('valid') and start<=r['receive_ns']<=finish]
  points=[r['target_state'] for r in accepted]+[r['activation_state'] for r in accepted]
  metrics=dict(batch=profile['batch'],run_id=profile['run_id'],scope=profile['scope'],audit_pin=pin(profile['audit']['path']),result_passed=result['passed'],
   observation_span_ns=finish-start,accepted=len(accepted),jobs=len(jobs),decisions=len(decisions),mixed_jobs=sum(r['job']['r_from_imu'] for r in jobs),mixed_accepted=sum(r['activation_r_from_imu'] for r in accepted),
   max_observed_planar_speed_m_s=max([math.hypot(s[3],s[4]) for s in states+points],default=0.),
   max_abs_state_error=[max([abs(r['state_error'][i]) for r in accepted],default=0.) for i in range(6)],
   max_accepted_odom_receipt_age_ns=max([r['odom_age_ns'] for r in accepted],default=0),max_accepted_clock_receipt_age_ns=max([r['clock_age_ns'] for r in accepted],default=0),
   accepted_RTF_min=min([r['activation_rtf'] for r in accepted],default=None),accepted_RTF_max=max([r['activation_rtf'] for r in accepted],default=None),
   max_tick_start_gap_ns=max([b['start_ns']-a['start_ns'] for a,b in zip(decisions,decisions[1:])],default=0),
   max_start_or_activation_jitter_ns=max([max(d['start_ns']-d['planned_ns'],d['activation_commit_ns']-d['planned_ns']) for d in decisions],default=0),
   current_Observer_physical_publishers=profile['roles']['observer']['physical_publisher_endpoints'],all_role_cleanup_complete=result['cleanup_complete'],
   normal_business_qualified=False,raw_inputs_are_original_closed_runs=True)
  need(metrics['mixed_accepted']==0,'selected review domain must be reconsidered if mixed present');observations.append(metrics)
 topics=freeze['contract']['fields']['output_topics'];current=freeze['diagnostic_profile_register'][-1]['roles']
 output_binding={}
 for side,topic in topics.items():
  endpoint=[e for e in current['publisher']['endpoints'] if e['kind']=='publisher' and e['topic']==topic];need(len(endpoint)==1,'one selected owner output endpoint')
  param=current['publisher']['effective_parameters']['vrx_'+side+'_thrust_topic']['value'];need(param==topic,'declared and actual topic binding')
  output_binding[side]=dict(contract_topic=topic,effective_parameter=param,actual_closed_run_endpoint=endpoint[0],Observer_physical_outlets=0,M4_new_regulator_proven=False)
 probe=load(D/'evidence/formal_compatibility_probe_v1.json');need(probe['probe_passed'],'formal probe')
 before=dict(PINS)
 for p in before:raw(p)
 need(PINS==before,'review facts input stability')
 report=dict(schema='B4-current-source-and-finite-evidence-facts/v1',passed=True,snippets=S,finite_observations=observations,
  selected_current_Native_test_names=tests,output_binding=output_binding,contract_fields=freeze['contract']['fields'],original_pending_groups=register['pending_original_groups'],
  compatibility_probe=probe,source_authority_is_registered_bundle_or_compiler_pin=True,
  current_same_ELF_profiles=[39,40,41,42],new_ROS_runs=0,new_CXX_builds=0,new_Native_runs=0,
  input_sha256_before=before,input_sha256_after=PINS,stage_qualified=False,execute_qualified=False,research_conclusion=False)
 dump(D/'evidence/current_source_facts_v1.json',report)
 print(json.dumps(dict(passed=True,pinned_source_snippets=len(S),closed_run_profiles=len(observations),current_Native_tests_reused=len(tests),read_inputs=len(PINS),new_ROS_runs=0)))
if __name__=='__main__':main()
