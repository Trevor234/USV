// SPDX-License-Identifier: MIT
#pragma once
#define P1_SHADOW_ENTRY_TEST
#define P1_LEGACY_READY_TEST
#define P1_C34_LEASE_COMPONENT
#define main p1_c34_original_program_main
#include P1_REGULATOR_SOURCE
#undef main

class C34LeaseAccess {
 public:
  static std::unique_ptr<Regulator> make(const std::string &path){
    stop_requested=false;
    p1::shadow::LegacyIdentity legacy{"p0-minimal-v1","component-legacy","component-producer","B",std::string(64,'f'),"sim"};
    auto r=std::unique_ptr<Regulator>(new Regulator(Regulator::LegacyReadyTestTag{},path,legacy));
    // Explicit seeded source-linked component: no startup readiness, tick,
    // native solver, actuator publisher or normal owned graph qualification.
    r->legacy_readiness_enabled_=false;return r;
  }
  static p1::Capability valid(Regulator &r){p1::Capability m;
    m.schema_version="p1-worker-capability-v1";m.run_id=r.run_;m.boot_id=r.boot_;m.contract_hash=r.hash_;
    m.nominal_hash=r.nominal_;m.worker_instance=std::string(64,'e');m.clock_name="CLOCK_MONOTONIC";
    m.backend="acados";m.matrix_layout="column_major";m.horizon_steps=20;m.prediction_dt=.2;
    m.pid=getpid();m.startup_ns=p1::monotonic_ns()-1000;m.fault_injection_enabled=true;return m;
  }
  static void callback(Regulator &r,const p1::Capability &m,const p1::Json *raw=nullptr){r.capability(m,raw);}
  static p1::Json state(Regulator &r){std::lock_guard<std::mutex> lock(r.mutex_);return {
    {"last_valid_ns",r.capability_lease_->last_valid_ns()},{"worker_valid",r.worker_valid_.load()},
    {"worker_unusable",r.worker_unusable_.load()},{"worker_instance",r.worker_instance_},
    {"input_commit_ordinal",r.input_commit_ordinal_},{"last_capability",r.last_capability_}};}
  static void check(Regulator &r,int64_t ns){std::lock_guard<std::mutex> lock(r.mutex_);r.check_worker_locked(ns);}
  static void subscribe(Regulator &r,const std::string &topic,std::atomic<unsigned> &count){
    r.capabilities_=r.create_subscription<p1::Capability>(topic,rclcpp::QoS(32).reliable().transient_local(),
      [&r,topic,&count](p1::Capability::SharedPtr m,const rclcpp::MessageInfo &info){
        auto raw=p1_observation_v4::raw_input(*m,info,topic,"usv_research_interfaces/msg/WorkerCapability",++r.raw_callback_sequences_[topic]);
        r.capability(*m,&raw);++count;});
  }
  static p1::Json endpoint(Regulator &r){return p1_owned::subscription_endpoint(*r.capabilities_,"usv_research_interfaces/msg/WorkerCapability");}
  static void close(Regulator &r){r.sink_->close();}
};
