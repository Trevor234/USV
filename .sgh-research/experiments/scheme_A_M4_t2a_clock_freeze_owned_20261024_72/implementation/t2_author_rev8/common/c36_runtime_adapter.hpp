// Source-linked shadow bridge. Authentication is performed before observe().
#pragma once
#include "command_anchor_v2.hpp"
#include "protocol.hpp"
#include "usv_research_interfaces/msg/applied_control.hpp"
namespace c36_runtime {
class Adapter {
 public:
  Adapter(c36::Owner owner,std::string job_run,std::string contract,std::string nominal)
    :owner_(owner),book_(owner),job_run_(std::move(job_run)),contract_(std::move(contract)),nominal_(std::move(nominal)) {}
  c36::Result observe(const usv_research_interfaces::msg::AppliedControl& m,int64_t now) {
    if(m.event_semantics!="publisher_command"||m.run_id!=owner_.run||m.producer_instance_id!=owner_.producer||m.config_hash!=owner_.config||m.clock_epoch!=owner_.epoch)return {"payload_owner_mismatch"};
    c36::PairFeedback f{owner_,m.sequence,m.final_n,
      {m.left_publish_success?c36::Call::succeeded:c36::Call::failed,m.right_publish_success?c36::Call::succeeded:c36::Call::failed},
      {m.left_publish_start_steady_ns,m.right_publish_start_steady_ns},{m.left_publish_end_steady_ns,m.right_publish_end_steady_ns},now};
    auto result=book_.observe(f);if(result&&book_.facts().life==c36::Life::preparing)result=book_.open(now);return result;
  }
  c36::Result submit(const p1::Job& j,int64_t now) {
    if(closing_)return {"driver_close_requested"};
    if(j.run_id!=job_run_||j.boot_id!=owner_.boot||j.contract_hash!=contract_||j.nominal_hash!=nominal_||j.anchor_source!="legacy_publisher"||j.anchor_run_id!=owner_.run||j.anchor_producer!=owner_.producer)return {"job_identity"};
    p1::Version v{j.task_generation,j.model_generation,j.config_generation,j.schedule_generation,j.clock_epoch};
    if(!(v==version_)){auto r=book_.change_version(v,now);if(!r)return r;version_=v;job_.reset();}
    c36::FrozenJob frozen;frozen.owner=owner_;frozen.freeze=j.freeze_steady_ns;
    auto& t=frozen.ticket;t.id=j.job_id;t.target=j.target_tick;t.origin=j.tick_origin_steady_ns;t.deadline=j.deadline_steady_ns;t.target_ns=j.target_steady_ns;t.version=v;
    t.anchor={j.anchor_n,j.anchor_sequence,j.anchor_publish_ns,j.anchor_known};t.prediction=j.target_state;
    auto result=book_.import_frozen(frozen,now);if(result){job_=j;frozen_=frozen;}return result;
  }
  c36::Result ready(const p1::Job& echo,const p1::Command& command,int64_t now) {
    if(closing_)return {"driver_close_requested"};
    if(!job_||p1::job_json(*job_)!=p1::job_json(echo))return {"full_job_echo_mismatch"};
    return book_.ready(frozen_,command,now);
  }
  c36::Result cutoff(int64_t now){if(closing_)return {"driver_close_requested"};return book_.cutoff(now);}
  c36::Result finalize_ready_completion(uint64_t id,int64_t now){
    if(closing_)return {"driver_close_requested"};
    if(!job_||job_->job_id!=id)return {"adapter_job_missing"};
    auto r=book_.finalize_ready_completion(id,now);if(r.reason=="late_ready_completion")job_.reset();return r;
  }
  c36::Result inspect(uint64_t job,uint64_t tick,int64_t now) {
    if(closing_){cancel(tick,now);return {"driver_close_requested"};}
    if(!job_||job_->job_id!=job)return {"adapter_job_missing"};
    auto result=book_.inspect_consume(frozen_,tick,now);job_.reset();return result;
  }
  c36::Result cancel(uint64_t tick,int64_t now){auto r=book_.cancel_pending(tick,now);if(r&&job_&&(!tick||job_->target_tick<=tick))job_.reset();return r;}
  c36::Result request_close(int64_t now){closing_=true;return cancel(0,now);}
  c36::Result close_after_join(int64_t now){closing_=true;auto r=book_.close(now);if(r)job_.reset();return r;}
  bool closing()const{return closing_;}
  c36::Facts facts()const{return book_.facts();}
  p1::Json evidence()const{auto a=book_.facts();return {{"profile","C3.6-shadow-adapter"},{"closing_requested",closing_},{"command_n",a.anchor.n},{"command_known",a.anchor.known},{"command_sequence",a.anchor.seq},{"command_publish_ns",a.anchor.time},{"component_lifecycle",int(a.life)},{"active_publish_transaction",a.active_transaction},{"job_pending",bool(job_)},{"actual_regulator_publish",false},{"plant_acceptance_observed",false}};}
 private:
  c36::Owner owner_;c36::CommandAnchor book_;p1::Version version_;
  std::string job_run_,contract_,nominal_;std::optional<p1::Job> job_;c36::FrozenJob frozen_;bool closing_=false;
};
} // namespace c36_runtime
