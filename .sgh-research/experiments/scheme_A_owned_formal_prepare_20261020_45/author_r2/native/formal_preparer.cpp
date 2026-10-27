// SPDX-License-Identifier: MIT
#include "formal_owned_runtime.hpp"
#include <thread>
namespace fo=formal_owned;namespace fp=p1::formal_prepare;
namespace {std::atomic<bool> stopped{false};void on_signal(int){stopped=true;}}
class FormalPreparer final:public rclcpp::Node {
 public:
  FormalPreparer():Node("p1_regulator",fo::node_options()){
    fo::entry_arguments(*this);
    run_=declare_parameter<std::string>("run_id","");hash_=declare_parameter<std::string>("contract_hash","");
    const auto file=declare_parameter<std::string>("contract_file","");const auto mode=declare_parameter<std::string>("mode","");
    c_=fo::load_contract(file,hash_,mode);out_=declare_parameter<std::string>("output_dir","");
    const auto pins_file=declare_parameter<std::string>("peer_pins_file","");
    const auto pins_hash=declare_parameter<std::string>("peer_pins_sha256","");
    fo::overrides(*this,{"run_id","contract_hash","contract_file","mode","output_dir","peer_pins_file","peer_pins_sha256","use_sim_time"});
    fo::require(fp::text(run_,128),"Preparer run domain");
    pins_=fo::read_pinned(pins_file,pins_hash);
    driver_=fo::driver_peer(pins_.at("driver"),run_,hash_);
    worker_=std::make_unique<fo::Peer>(pins_.at("worker"),"worker",run_,hash_);
    fixture_=std::make_unique<fo::Peer>(pins_.at("fixture"),"synthetic_source",run_,hash_);
    recorder_=std::make_unique<fo::Peer>(pins_.at("recorder"),"recorder",run_,hash_);
    fo::require(worker_->manifest().at("contract_configuration")==c_&&fixture_->manifest().at("contract_configuration")==c_,"actual peer contract configurations");
    const auto &wm=worker_->manifest();
    fo::require(wm.at("runtime_hook_values").at("test_delay_ms")==0&&wm.at("runtime_hook_values").at("test_native_block_ms")==0&&
      wm.at("diagnostic_v2").at("policy")=="none"&&wm.at("diagnostic_v2").at("milliseconds")==0&&
      wm.at("fault_injection_permission")==false,"actual Worker fault permission disabled");
    fo::require(fixture_->manifest().at("source_state")=="stationary_zero_equilibrium"&&fixture_->manifest().at("Applied_subscribers")==0,
      "no legacy Fixture semantics");
    fo::require(recorder_->manifest().at("true_recorder_storage")==true&&recorder_->manifest().at("discovery_stopped")==true&&
      recorder_->manifest().at("topic_declaration_sha256")==pins_.at("topics_sha256"),"actual Recorder configuration binding");
    source_=std::make_unique<fo::Source>(out_+"/source.jsonl");const auto t=fo::inputs(c_);
    clock_=create_subscription<rosgraph_msgs::msg::Clock>(t[0].first,rclcpp::ClockQoS(),
      [this](rosgraph_msgs::msg::Clock::ConstSharedPtr m,const rclcpp::MessageInfo &info){
        const auto stamp=ns(m->clock);const bool valid=stamp>0&&stamp>stamps_[0];
        receipt(0,*m,info,valid,stamp);});
    odom_=create_subscription<nav_msgs::msg::Odometry>(t[1].first,rclcpp::SensorDataQoS(),
      [this](nav_msgs::msg::Odometry::ConstSharedPtr m,const rclcpp::MessageInfo &info){
        const auto &p=m->pose.pose;const auto &v=m->twist.twist;
        const bool valid=m->header.frame_id==c_.at("expected_pose_frame")&&m->child_frame_id==c_.at("expected_child_frame")&&
          zero(p.position)&&unit(p.orientation)&&zero(v.linear)&&zero(v.angular);
        receipt(1,*m,info,valid,ns(m->header.stamp));});
    imu_=create_subscription<sensor_msgs::msg::Imu>(t[2].first,rclcpp::SensorDataQoS(),
      [this](sensor_msgs::msg::Imu::ConstSharedPtr m,const rclcpp::MessageInfo &info){
        receipt(2,*m,info,m->header.frame_id==c_.at("expected_imu_frame")&&unit(m->orientation)&&zero(m->angular_velocity)&&zero(m->linear_acceleration),ns(m->header.stamp));});
    path_=create_subscription<nav_msgs::msg::Path>(t[3].first,rclcpp::QoS(1).reliable(),
      [this](nav_msgs::msg::Path::ConstSharedPtr m,const rclcpp::MessageInfo &info){
        bool valid=m->header.frame_id==c_.at("expected_pose_frame")&&m->poses.size()==21;
        if(valid)for(const auto &p:m->poses)valid=valid&&p.header==m->header&&zero(p.pose.position)&&unit(p.pose.orientation);
        receipt(3,*m,info,valid,ns(m->header.stamp));});
    profile_=create_subscription<std_msgs::msg::Float64MultiArray>(t[4].first,rclcpp::QoS(1).reliable(),
      [this](std_msgs::msg::Float64MultiArray::ConstSharedPtr m,const rclcpp::MessageInfo &info){
        if(!fo::bounded_domain(*m,c_)){receipt(4,*m,info,false,0);return;}
        bool valid=m->layout.dim.size()==2&&m->layout.data_offset==0&&m->data.size()==84;int64_t stamp=0;
        if(valid){const auto &d=m->layout.dim;
          valid=d[0].size==21&&d[0].stride==84&&d[1].size==4&&d[1].stride==4;
          try{const std::string a="stamp_sec:",b="stamp_nanosec:";
            valid=valid&&d[0].label.rfind(a,0)==0&&d[1].label.rfind(b,0)==0;
            size_t ac=0,bc=0;const auto sec=std::stoll(d[0].label.substr(a.size()),&ac),nano=std::stoll(d[1].label.substr(b.size()),&bc);
            valid=valid&&ac==d[0].label.size()-a.size()&&bc==d[1].label.size()-b.size();
            valid=valid&&sec>=0&&sec<=INT32_MAX&&nano>=0&&nano<1000000000;stamp=sec*1000000000LL+nano;
          }catch(...){valid=false;}
          for(int k=0;k<=20;++k)valid=valid&&m->data[4*k]==0.&&m->data[4*k+1]==0.&&m->data[4*k+2]==0.&&m->data[4*k+3]==.2*k;
        }receipt(4,*m,info,valid,stamp);});
    cap_=create_subscription<fo::Capability>(fo::cap_topic,rclcpp::QoS(1).reliable().transient_local(),
      [this](fo::Capability::ConstSharedPtr m,const rclcpp::MessageInfo &info){capability(*m,info);});
    candidate_=create_subscription<fo::Candidate>(fo::candidate_topic,rclcpp::QoS(1).reliable(),
      [this](fo::Candidate::ConstSharedPtr,const rclcpp::MessageInfo &info){
        source_->add({{"type","unexpected_candidate"},{"publisher_gid",p1_owned::gid_json(info.get_rmw_message_info().publisher_gid)}});
        throw std::runtime_error("prepare-only must receive no candidate");});
    auto endpoints=fo::Json::array({p1_owned::subscription_endpoint(*clock_,t[0].second),p1_owned::subscription_endpoint(*odom_,t[1].second),
      p1_owned::subscription_endpoint(*imu_,t[2].second),p1_owned::subscription_endpoint(*path_,t[3].second),
      p1_owned::subscription_endpoint(*profile_,t[4].second),p1_owned::subscription_endpoint(*cap_,"usv_research_interfaces/msg/WorkerCapability"),
      p1_owned::subscription_endpoint(*candidate_,"usv_research_interfaces/msg/SolveCandidate")});
    frozen_=p1_owned::freeze_parameters(*this);
    p1_owned::write_create_only(out_+"/manifest.json",p1_owned::role_manifest(*this,"formal_preparer",run_,hash_,P1_OWNED_SOURCE_BUNDLE_SHA256,endpoints,
      {{"mode",mode},{"contract_configuration",c_},{"spec_sha256",p1::full_contract_spec_sha256},
       {"source_fd",p1_owned::source_fd_identity(out_+"/source.jsonl")},{"physical_publishers",0},{"business_publishers",0},
       {"preparation_scope",fp::scope},{"command_anchor_authority","none"},{"peer_pins_sha256",pins_hash}}));
    own_sha_=p1_owned::file_sha256(out_+"/manifest.json");const auto &dm=driver_->manifest();
    gate_=std::make_unique<fp::Gate>(c_,mode,fp::Identity{run_,p1_owned::boot_id(),hash_,own_sha_,
      dm.at("pid"),dm.at("process_start_ticks"),dm.at("binary_sha256"),p1_owned::sha256_bytes(dm.at("argv").dump()),
      dm.at("tool_sha256"),pins_.at("worker").at("manifest_sha256"),pins_.at("fixture").at("manifest_sha256"),
      pins_.at("recorder").at("manifest_sha256")},p1_owned::steady_ns());
    source_->add({{"type","preparer_waiting"},{"gate",gate_->evidence()},{"manifest_sha256",own_sha_}});
  }
  bool done()const{return failed_;}
  void poll(){
    const auto now=p1_owned::steady_ns();const auto graph=graph_ready();
    if(graph&&!readers_ready_){
      readers_ready_=true;p1_owned::write_create_only(out_+"/reader_ready.json",{{"schema","formal-owned-readers-ready-v1"},
        {"run_id",run_},{"boot_id",p1_owned::boot_id()},{"contract_sha256",hash_},{"manifest_sha256",own_sha_},
        {"checked_ns",now},{"exact_Reader_and_Writer_GIDs",true},{"forbidden_Writers",0},{"stage_qualified",false}});
      source_->add({{"type","readers_ready"},{"checked_ns",now},{"forbidden_Writers",0}});
    }
    auto c=context(now,graph);
    if(ready_sha_.empty()&&prerequisites(c)){
      p1_owned::write_create_only(out_+"/ready.json",{{"schema","formal-owned-prepare-ready-v1"},{"run_id",run_},
        {"boot_id",p1_owned::boot_id()},{"contract_sha256",hash_},{"spec_sha256",p1::full_contract_spec_sha256},
        {"manifest_sha256",own_sha_},{"created_ns",now},{"ready_generation",1},{"version",version()},
        {"validated_receipts",receipts_json()},{"capability_receipt_ns",cap_receipt_},
        {"paired_reference_stamp_ns",paired_reference_stamp_},{"paired_reference_commit_ns",paired_reference_commit_},
        {"peer_manifest_pins",pins_},{"source_policy","stationary_inputs_no_command_anchor_prepare_only"},
        {"recording_ready",c.recording_ready},{"forbidden_Writers",0},{"stage_qualified",false},{"execute_qualified",false}});
      ready_sha_=p1_owned::file_sha256(out_+"/ready.json");c=context(p1_owned::steady_ns(),graph_ready());
      source_->add({{"type","ready_snapshot_committed"},{"ready_snapshot_sha256",ready_sha_},{"context",context_json(c)}});
    }
    if(gate_->state()==fp::State::waiting&&std::filesystem::exists(out_+"/grant.json")){
      const auto raw=c36_owned::detail::read_manifest(out_+"/grant.json");
      c=context(p1_owned::steady_ns(),graph_ready());const auto commit=p1_owned::steady_ns();
      try{gate_->open(raw,commit,c);was_prepared_=true;
        source_->add({{"type","prepare_grant_accepted"},{"request",c36_owned::detail::strict_json(raw)},
          {"request_sha256",p1_owned::sha256_bytes(raw)},{"context",context_json(c)},{"gate",gate_->evidence()}});
        p1_owned::write_create_only(out_+"/prepared.json",{{"schema","formal-owned-prepared-v1"},{"run_id",run_},
          {"contract_sha256",hash_},{"grant_sha256",p1_owned::sha256_bytes(raw)},{"ready_snapshot_sha256",ready_sha_},
          {"prepared_ns",commit},{"gate",gate_->evidence()}});
        bool rejected=false;std::string reason;
        try{gate_->open(raw,p1_owned::steady_ns(),context(p1_owned::steady_ns(),graph_ready()));}
        catch(const std::exception&e){rejected=true;reason=e.what();}
        fo::require(rejected&&gate_->state()==fp::State::prepared,"actual same-grant replay must reject");
        source_->add({{"type","actual_grant_replay_rejected"},{"reason",reason},{"gate",gate_->evidence()}});
      }catch(const std::exception&e){source_->add({{"type","prepare_grant_rejected"},{"reason",e.what()},{"context",context_json(c)},{"gate",gate_->evidence()}});failed_=true;}
    }
    gate_->poll(p1_owned::steady_ns(),context(p1_owned::steady_ns(),graph_ready()));
    if(gate_->state()==fp::State::rejected||gate_->state()==fp::State::expired){
      source_->add({{"type","prepare_terminal_failure"},{"gate",gate_->evidence()},{"context",context_json(context(p1_owned::steady_ns(),graph_ready()))}});failed_=true;
    }
    if(graph_checks_%20==0)source_->add({{"type","actual_graph_check"},{"checked_ns",p1_owned::steady_ns()},
      {"graph_ready",graph},{"forbidden_Writers_absent",fo::forbidden_writers_absent(*this,c_)},
      {"gate",gate_->evidence()}});
    ++graph_checks_;
  }
  bool close(){
    gate_->close(p1_owned::steady_ns());source_->add({{"type","preparer_closed"},{"gate",gate_->evidence()},
      {"was_prepared",was_prepared_},{"failed",failed_},{"validated_input_counts",accepted_},{"rejected_input_counts",rejected_},
      {"capability_receipts",cap_count_},{"graph_checks",graph_checks_},{"solve_jobs",0},{"Decisions",0},{"Applied",0},{"physical_calls",0}});source_->finish();
    p1_owned::write_create_only(out_+"/terminal.json",{{"schema","formal-preparer-terminal-v1"},{"run_id",run_},
      {"contract_sha256",hash_},{"manifest_sha256",own_sha_},{"was_prepared",was_prepared_},{"failed",failed_},
      {"normal_source_complete",source_->good()},{"gate",gate_->evidence()},{"graph_checks",graph_checks_},
      {"validated_input_counts",accepted_},{"rejected_input_counts",rejected_},{"capability_receipts",cap_count_},
      {"solve_jobs",0},{"Decisions",0},{"Applied",0},{"physical_calls",0},{"stage_qualified",false},{"execute_qualified",false}});
    return was_prepared_&&!failed_;
  }
 private:
  static int64_t ns(const builtin_interfaces::msg::Time &s){return int64_t(s.sec)*1000000000LL+s.nanosec;}
  template<class V>static bool zero(const V &v){return v.x==0.&&v.y==0.&&v.z==0.;}
  template<class Q>static bool unit(const Q &q){return zero(q)&&q.w==1.;}
  template<class M>void receipt(size_t index,const M &m,const rclcpp::MessageInfo &info,bool value_valid,int64_t stamp){
    const auto enter=p1_owned::steady_ns();const auto t=fo::inputs(c_)[index];
    if(!fo::bounded_domain(m,c_)){source_->add({{"type","typed_resource_rejected"},{"topic",t.first},{"receive_ns",enter}});++rejected_[index];input_invalid_=true;return;}
    const bool admitted=fixture_->receipt(info,t.first,t.second)&&value_valid&&stamp>0&&stamp>=stamps_[index];
    source_->add({{"type","input_receipt"},{"topic",t.first},{"receive_ns",enter},{"sim_stamp_ns",stamp},
      {"publisher_gid",p1_owned::gid_json(info.get_rmw_message_info().publisher_gid)},{"cdr",fo::cdr(m)},
      {"value_valid",value_valid},{"owned_admitted",admitted}});
    if(admitted){
      receipts_[index]=enter;stamps_[index]=stamp;++accepted_[index];
      if((index==3||index==4)&&stamps_[3]>0&&stamps_[3]==stamps_[4]){
        paired_reference_stamp_=stamp;paired_reference_commit_=enter;
      }
    }else{++rejected_[index];input_invalid_=true;}
  }
  void capability(const fo::Capability &m,const rclcpp::MessageInfo &info){
    const auto now=p1_owned::steady_ns();const auto &wm=worker_->manifest();
    if(!fo::bounded(m)){source_->add({{"type","typed_resource_rejected"},{"topic",fo::cap_topic},{"receive_ns",now}});input_invalid_=true;return;}
    const bool valid=worker_->receipt(info,fo::cap_topic,"usv_research_interfaces/msg/WorkerCapability")&&
      m.schema_version=="p1-worker-capability-v1"&&m.run_id==run_&&m.boot_id==p1_owned::boot_id()&&m.contract_hash==hash_&&
      m.worker_instance==wm.at("worker_instance")&&m.nominal_hash==c_.at("nominal_hash")&&m.pid==wm.at("pid")&&
      m.clock_name=="CLOCK_MONOTONIC"&&m.backend=="acados"&&m.matrix_layout=="column_major"&&m.horizon_steps==20&&m.prediction_dt==.2&&
      m.startup_ns>0&&m.startup_ns<=now&&!m.fault_injection_enabled&&!m.fatal&&m.completed_jobs==0&&m.active_job==0&&m.pending_count==0&&m.reason.empty();
    source_->add({{"type","capability_receipt"},{"receive_ns",now},{"owned_admitted",valid},
      {"publisher_gid",p1_owned::gid_json(info.get_rmw_message_info().publisher_gid)},{"payload",fo::capability_json(m)},{"cdr",fo::cdr(m)}});
    if(valid){cap_receipt_=p1_owned::steady_ns();cap_valid_=true;++cap_count_;}else{cap_valid_=false;input_invalid_=true;}
  }
  bool reader(const fo::Peer &peer,const std::string &topic,const std::string &type){
    const auto expected=peer.endpoint("subscription",topic,type);
    for(const auto &e:get_subscriptions_info_by_topic(topic)){
      fo::Json gid=fo::Json::array();for(auto b:e.endpoint_gid())gid.push_back(unsigned(b));
      if(gid==expected.at("gid")&&e.topic_type()==type)return peer.alive();
    }return false;
  }
  bool graph_ready(){
    if(!fo::forbidden_writers_absent(*this,c_)||!worker_->alive()||!fixture_->alive()||!recorder_->alive())return false;
    for(const auto &t:fo::inputs(c_))if(!fixture_->graph(*this,t.first,t.second)||!reader(*recorder_,t.first,t.second)||get_subscriptions_info_by_topic(t.first).size()!=2)return false;
    return worker_->graph(*this,fo::cap_topic,"usv_research_interfaces/msg/WorkerCapability")&&
      worker_->graph(*this,fo::candidate_topic,"usv_research_interfaces/msg/SolveCandidate")&&
      reader(*recorder_,fo::cap_topic,"usv_research_interfaces/msg/WorkerCapability")&&
      reader(*fixture_,fo::cap_topic,"usv_research_interfaces/msg/WorkerCapability")&&
      reader(*recorder_,fo::candidate_topic,"usv_research_interfaces/msg/SolveCandidate")&&
      get_subscriptions_info_by_topic(fo::cap_topic).size()==3&&get_subscriptions_info_by_topic(fo::candidate_topic).size()==2;
  }
  static fo::Json version(){return {{"task",1},{"model",1},{"config",1},{"schedule",1},{"epoch",1}};}
  fp::Context context(int64_t now,bool graph){
    fp::Context c;c.driver_live=driver_->alive();c.worker_live=worker_->alive();c.fixture_live=fixture_->alive();c.recorder_live=recorder_->alive();
    c.worker_capability_valid=cap_valid_&&!input_invalid_;c.capability_receipt_ns=cap_receipt_;
    c.source_inputs_valid=!input_invalid_&&graph;
    for(size_t k=0;k<receipts_.size();++k)c.source_inputs_valid=c.source_inputs_valid&&receipts_[k]>0&&now>=receipts_[k]&&now-receipts_[k]<=100000000;
    if(c.source_inputs_valid){const auto current=stamps_[0]+now-receipts_[0];
      for(size_t k=1;k<=2;++k)c.source_inputs_valid=c.source_inputs_valid&&current-stamps_[k]<=100000000&&stamps_[k]-current<=20000000;}
    // The latest independently arriving halves may temporarily disagree. Keep
    // the last complete authenticated pair within the same 100ms input bound.
    c.reference_pair_ready=paired_reference_stamp_>0&&paired_reference_commit_>0&&now>=paired_reference_commit_&&now-paired_reference_commit_<=100000000;
    c.recording_ready=graph&&recorder_->stable_manifest()&&worker_->stable_manifest()&&fixture_->stable_manifest()&&driver_->stable_manifest();
    c.sink_ready=source_->good();c.stopping=stopped;c.ready_generation=ready_sha_.empty()?0:1;
    c.ready_snapshot_sha256=ready_sha_;c.version=version();
    const bool forbidden=fo::forbidden_writers_absent(*this,c_);c.physical_publishers=forbidden?0:1;
    return c;
  }
  static bool prerequisites(const fp::Context &c){return c.driver_live&&c.worker_live&&c.fixture_live&&c.recorder_live&&
    c.worker_capability_valid&&c.capability_receipt_ns>0&&p1_owned::steady_ns()-c.capability_receipt_ns<=600000000&&
    c.source_inputs_valid&&c.reference_pair_ready&&c.recording_ready&&c.sink_ready&&!c.stopping&&c.physical_publishers==0;}
  fo::Json receipts_json()const{return {{"receive_ns",receipts_},{"sim_stamp_ns",stamps_},{"accepted",accepted_},{"rejected",rejected_}};}
  static fo::Json context_json(const fp::Context &c){return {{"driver_live",c.driver_live},{"worker_live",c.worker_live},{"fixture_live",c.fixture_live},
    {"recorder_live",c.recorder_live},{"worker_capability_valid",c.worker_capability_valid},{"source_inputs_valid",c.source_inputs_valid},
    {"reference_pair_ready",c.reference_pair_ready},{"recording_ready",c.recording_ready},{"sink_ready",c.sink_ready},{"stopping",c.stopping},
    {"capability_receipt_ns",c.capability_receipt_ns},{"ready_generation",c.ready_generation},{"ready_snapshot_sha256",c.ready_snapshot_sha256},
    {"physical_publishers",c.physical_publishers},{"solve_job_publishers",c.solve_job_publishers},
    {"decision_publishers",c.decision_publishers},{"applied_publishers",c.applied_publishers},{"version",c.version}};}
  std::string run_,hash_,out_,own_sha_,ready_sha_;fo::Json c_,pins_;bool readers_ready_=false,was_prepared_=false,failed_=false,input_invalid_=false,cap_valid_=false;
  std::unique_ptr<fo::Peer> driver_,worker_,fixture_,recorder_;std::unique_ptr<fo::Source> source_;std::unique_ptr<fp::Gate> gate_;
  std::array<int64_t,5> receipts_{},stamps_{};std::array<uint64_t,5> accepted_{},rejected_{};
  int64_t cap_receipt_=0,paired_reference_stamp_=0,paired_reference_commit_=0;
  uint64_t cap_count_=0,graph_checks_=0;
  rclcpp::Subscription<rosgraph_msgs::msg::Clock>::SharedPtr clock_;rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_;
  rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_;rclcpp::Subscription<nav_msgs::msg::Path>::SharedPtr path_;
  rclcpp::Subscription<std_msgs::msg::Float64MultiArray>::SharedPtr profile_;rclcpp::Subscription<fo::Capability>::SharedPtr cap_;
  rclcpp::Subscription<fo::Candidate>::SharedPtr candidate_;rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr frozen_;
};
int main(int argc,char **argv){try{
  rclcpp::init(argc,argv,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);std::signal(SIGINT,on_signal);std::signal(SIGTERM,on_signal);
  auto node=std::make_shared<FormalPreparer>();rclcpp::executors::SingleThreadedExecutor executor;executor.add_node(node);
  while(rclcpp::ok()&&!stopped&&!node->done()){
    executor.spin_some(std::chrono::milliseconds(5));node->poll();std::this_thread::sleep_for(std::chrono::milliseconds(5));}
  executor.remove_node(node);const bool good=node->close();node.reset();rclcpp::shutdown();return good?0:3;
}catch(const std::exception&e){fprintf(stderr,"formal Preparer: %s\n",e.what());if(rclcpp::ok())rclcpp::shutdown();return 2;}}
