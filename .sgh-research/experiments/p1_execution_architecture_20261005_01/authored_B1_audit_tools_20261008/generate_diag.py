from pathlib import Path
import hashlib,difflib
B=Path(__file__).resolve().parent;D=B/'diag'
src=(D/'regulator_baseline.cpp').read_text(encoding='utf-8')
assert hashlib.sha256((D/'regulator_baseline.cpp').read_bytes()).hexdigest()=='1163a651580bde314e8b450d39213c1691187fbe977debe63a0366c6e027eb8c'
s=src
def replace(a,b):
    global s
    assert s.count(a)==1,(a[:100],s.count(a))
    s=s.replace(a,b)
replace('namespace {std::atomic<bool>', '#include "p1_diag_sink.hpp"\n#include <openssl/evp.h>\nnamespace {std::atomic<bool>')
a=s.index('// One bounded logging queue.');b=s.index('class Regulator final:')
s=s[:a]+'''// Dedicated B1 diagnostic entry; production B0 is byte-for-byte preserved.
using Sink=p1::DiagSink<p1::Decision,rclcpp::Publisher<p1::Decision>::SharedPtr>;
static std::string file_sha(const std::string &path){
  std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("identity file unavailable");
  EVP_MD_CTX *ctx=EVP_MD_CTX_new();if(!ctx)throw std::runtime_error("digest allocation");
  unsigned char hash[EVP_MAX_MD_SIZE];unsigned length=0;char buffer[16384];
  bool ok=EVP_DigestInit_ex(ctx,EVP_sha256(),nullptr)==1;
  while(f&&ok){f.read(buffer,sizeof(buffer));if(f.gcount())ok=EVP_DigestUpdate(ctx,buffer,f.gcount())==1;}
  ok=ok&&f.eof()&&EVP_DigestFinal_ex(ctx,hash,&length)==1;EVP_MD_CTX_free(ctx);
  if(!ok||length!=32)throw std::runtime_error("identity digest failed");
  static const char hex[]="0123456789abcdef";std::string result(64,'0');
  for(unsigned i=0;i<32;++i){result[2*i]=hex[hash[i]>>4];result[2*i+1]=hex[hash[i]&15];}return result;
}
''' +s[b:]
replace('Regulator():Node("p1_regulator")','Regulator():Node("p1_regulator")') # same node preserves matched-endpoint identity
replace('resources_=p1::resource_limits_from_contract(c_);boot_', '''resources_=p1::resource_limits_from_contract(c_);
    if(mode_!="no_output"||c_.at("schema")!="p1-execution-contract-v2"||c_.at("diagnostic_contract_revision")!=5)
      throw std::runtime_error("B1 diagnostic entry requires no_output diag5");
    boot_''')
replace('worker_liveness_=std::make_unique<p1::WorkerLiveness>(expected_worker_pid_);', '''const bool audit=declare_parameter<bool>("witness_enabled",false);
    witness_file_=declare_parameter<std::string>("witness_file","");
    p1::DiagPausePolicy pause{declare_parameter<int64_t>("test_sink_pause_ms",0)};
    pause.validate(mode_,true,c_.at("fault_injection_enabled").get<bool>(),audit);
    if(!audit&&!witness_file_.empty())throw std::runtime_error("disabled witness cannot have output path");
    p1::WitnessHeader h{};
    if(audit){
      if(witness_file_.empty())throw std::runtime_error("witness output path required");
      const auto source_path=declare_parameter<std::string>("diagnostic_source_file","");
      const auto expected_source=declare_parameter<std::string>("diagnostic_source_sha256","");
      const auto expected_binary=declare_parameter<std::string>("diagnostic_binary_sha256","");
      const auto expected_worker=declare_parameter<std::string>("worker_binary_sha256","");
      const auto instance=declare_parameter<std::string>("witness_worker_instance","");
      const auto source=file_sha(source_path),binary=file_sha("/proc/self/exe");
      if(expected_worker_pid_<=0)throw std::runtime_error("worker identity PID required");
      const auto worker=file_sha("/proc/"+std::to_string(expected_worker_pid_)+"/exe");
      if(source!=expected_source||binary!=expected_binary||worker!=expected_worker)throw std::runtime_error("witness identity digest mismatch");
      if(!(p1::witness_text(h.run_id,run_)&&p1::witness_text(h.boot_id,boot_)&&p1::witness_text(h.contract_sha256,hash_)&&
           p1::witness_text(h.source_sha256,source)&&p1::witness_text(h.binary_sha256,binary)&&p1::witness_text(h.worker_binary_sha256,worker)&&p1::witness_text(h.worker_instance,instance)))
        throw std::runtime_error("bounded witness identity invalid");
    }
    witness_=std::make_unique<p1::Witness>(audit,h);
    if(audit&&witness_->summary().incomplete)throw std::runtime_error("witness header invalid");
    pause_policy_=pause;
    worker_liveness_=std::make_unique<p1::WorkerLiveness>(expected_worker_pid_);''')
replace('c_.at("log_capacity"),decision_pub_);','c_.at("log_capacity"),decision_pub_,witness_.get(),pause_policy_);')
replace('if(mode_=="shadow")applied_=', '''pause_arm_=create_subscription<std_msgs::msg::Bool>("/p1/diag/arm_sink_pause",rclcpp::QoS(1).reliable(),[this](std_msgs::msg::Bool::SharedPtr m){if(m->data)sink_->arm_pause();});
    if(mode_=="shadow")applied_=''')
replace('sink_->close();fprintf(stdout,"REGULATOR_CLOSE_FLUSH_SUCCESS=%s\\n",sink_->failed()?"false":"true");return !sink_->failed();', '''sink_->close();
    {std::lock_guard<std::mutex> l(mutex_);phase_locked(p1::WitnessPhaseKind::Close,p1::WitnessObservation::Close,p1::monotonic_ns());}
    if(witness_->enabled()&&!audit_identity_ok_)witness_->mark_header_invalid();
    witness_->close_after_join();const bool audit_written=!witness_->enabled()||witness_->write_terminal(witness_file_.c_str());
    audit_closed_=audit_written&&(!witness_->enabled()||witness_->summary().audit_complete);
    fprintf(stdout,"REGULATOR_CLOSE_FLUSH_SUCCESS=%s\\n",sink_->failed()?"false":"true");
    fprintf(stdout,"DIAGNOSTIC_WITNESS_COMPLETE=%s\\n",audit_closed_&&witness_->summary().audit_complete?"true":"false");return !sink_->failed();''')
replace('bool finished()const{return finished_;}', 'bool finished()const{return finished_;}\n  bool audit_closed()const{return audit_closed_;}')
replace('static int64_t stamp(', '''static p1::WitnessState ws(bool value){return value?p1::WitnessState::True:p1::WitnessState::False;}
  void phase_locked(p1::WitnessPhaseKind event,p1::WitnessObservation observation,int64_t ns,uint64_t job=0){
    if(!witness_->enabled())return;
    p1::WitnessPhase r{};r.event_code=event;r.observation_code=observation;r.ns=ns;r.tick=current_tick_;r.job_id=job;
    r.admission_slots=int32_t(admission_.slots());r.candidate_present=ws(bool(candidate_));
    {std::lock_guard<std::mutex> q(prep_mutex_);r.pending_present=ws(bool(pending_));}
    r.failed=ws(sink_->failed());r.stopping=ws(stopping_);r.pause_active=ws(sink_->pause_active());witness_->record_phase(r);
  }
  template<class Row>void identity(Row &r,const p1::Decision &d){r.job_id=d.job_id;r.tick=d.tick;r.target_tick=d.job_id?d.tick:0;r.task_generation=d.task_generation;r.model_generation=d.model_generation;r.config_generation=d.config_generation;r.schedule_generation=d.schedule_generation;r.clock_epoch=d.clock_epoch;}
  void audit_tick(const p1::Decision &d,bool present,bool failed_start,bool stopping_start){
    if(!witness_->enabled())return;
    p1::WitnessTick r{};identity(r,d);r.planned_ns=d.tick_planned_ns;r.start_ns=d.tick_start_ns;r.end_ns=p1::monotonic_ns();r.skipped_ticks=d.skipped_ticks;
    r.candidate_present=present;r.failed_start=failed_start;r.stopping_start=stopping_start;r.failed_end=sink_->failed();r.stopping_end=stopping_;witness_->record_tick(r);
  }
  static int64_t stamp(''')
replace('if(identity){\n', '''if(witness_->enabled()&&valid&&identity&&m.worker_instance!=witness_->header().worker_instance)audit_identity_ok_=false;
    if(identity){
''')
replace('while(jobs_.size()>8)jobs_.pop_front();}', '''while(jobs_.size()>8)jobs_.pop_front();
      p1::WitnessSubmit row{};row.job_id=j.job_id;row.tick=p.tick;row.target_tick=j.target_tick;row.task_generation=j.task_generation;row.model_generation=j.model_generation;row.config_generation=j.config_generation;row.schedule_generation=j.schedule_generation;row.clock_epoch=j.clock_epoch;row.commit_ns=p1::monotonic_ns();row.failed=sink_->failed();row.stopping=stopping_;witness_->record_submit(row);
    }''')
replace('current_tick_=tick;check_worker_locked(now);if(stop_requested||sink_->failed()){stopping_=true;if(!stop_start)stop_start=now;invalidate_locked();}', '''current_tick_=tick;check_worker_locked(now);if(stop_requested||sink_->failed()){
          stopping_=true;if(!stop_phase_recorded_){phase_locked(p1::WitnessPhaseKind::StoppingObserved,p1::WitnessObservation::TickStart,p1::monotonic_ns());stop_phase_recorded_=true;}
          if(!stop_start)stop_start=now;invalidate_locked();
          if(!invalidate_phase_recorded_){phase_locked(p1::WitnessPhaseKind::InvalidationObserved,p1::WitnessObservation::TickStart,p1::monotonic_ns());invalidate_phase_recorded_=true;}
        }''')
replace('auto reason=eligible(s,now);', 'const bool audit_failed_start=sink_->failed(),audit_stopping_start=stopping_;\n      auto reason=eligible(s,now);')
replace('d.candidate_accepted=reason.empty();d.reason=reason;d.activation_commit_ns=commit_now;', '''d.candidate_accepted=reason.empty();d.reason=reason;d.activation_commit_ns=commit_now;
        if(t&&cand){p1::WitnessActivation row{};identity(row,d);row.commit_ns=commit_now;row.ready_commit_ns=d.candidate_ready_commit_ns;row.accepted=d.candidate_accepted;row.failed=sink_->failed();row.stopping=stopping_;
          row.reason_code=row.accepted?p1::WitnessActivationReason::Accepted:reason=="shutdown"?p1::WitnessActivationReason::Shutdown:reason=="run_unusable_at_commit"?p1::WitnessActivationReason::RunUnusable:p1::WitnessActivationReason::OtherRejected;
          witness_->record_activation(row);
          if(row.accepted&&!business_ready_recorded_){phase_locked(p1::WitnessPhaseKind::BusinessReady,p1::WitnessObservation::FinalActivation,commit_now,d.job_id);business_ready_recorded_=true;}
          if(row.failed&&!activation_failed_recorded_){phase_locked(p1::WitnessPhaseKind::SourceFailure,p1::WitnessObservation::FinalActivation,p1::monotonic_ns(),d.job_id);activation_failed_recorded_=true;}
        }
        ''')
replace('if(!sink_->add(decision_json(d),d)){normal_complete_=false;stopping_=true;if(!stop_start)stop_start=now;}', '''if(!sink_->add(decision_json(d),d)){normal_complete_=false;stopping_=true;if(!stop_start)stop_start=now;
        std::lock_guard<std::mutex> l(mutex_);if(!enqueue_failed_recorded_){phase_locked(p1::WitnessPhaseKind::StoppingObserved,p1::WitnessObservation::DecisionEnqueue,p1::monotonic_ns(),d.job_id);enqueue_failed_recorded_=true;}
      }''')
replace('}});break;}}\n      p1::sleep_until_monotonic', '}});audit_tick(d,bool(t&&cand),audit_failed_start,audit_stopping_start);break;}}\n      p1::sleep_until_monotonic')
replace('      ++tick;','      audit_tick(d,bool(t&&cand),audit_failed_start,audit_stopping_start);\n      ++tick;')
replace('  p1::Json c_;', '''  std::unique_ptr<p1::Witness> witness_;p1::DiagPausePolicy pause_policy_;std::string witness_file_;
  std::atomic<bool> audit_identity_ok_{true};bool audit_closed_=false,business_ready_recorded_=false,stop_phase_recorded_=false,invalidate_phase_recorded_=false,activation_failed_recorded_=false,enqueue_failed_recorded_=false;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr pause_arm_;
  p1::Json c_;''')
replace('bool closed=node->close_source();node.reset();rclcpp::shutdown();return closed?0:2;', 'bool closed=node->close_source();bool audit=node->audit_closed();node.reset();rclcpp::shutdown();return closed?(audit?0:3):2;')
(D/'regulator_r5_diag.cpp').write_text(s,encoding='utf-8',newline='\n')
(B/'baseline_to_diag.diff').write_text(''.join(difflib.unified_diff(src.splitlines(True),s.splitlines(True),fromfile='B0/regulator.cpp',tofile='B1/regulator_r5_diag.cpp')),encoding='utf-8',newline='\n')
print('generated',hashlib.sha256(s.encode()).hexdigest())
