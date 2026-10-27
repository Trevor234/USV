// SPDX-License-Identifier: MIT
// Exact49 production publish/record/Applied/finish code with explicitly seeded
// test-constructor authority. Private topics only; no live owned-entry claim.
#include <gtest/gtest.h>
#include <rcl/publisher.h>
#include <rcl/error_handling.h>
#include <rclcpp/serialization.hpp>
#include <dlfcn.h>
#include <atomic>
#include <filesystem>
#include <fstream>
#include <vector>
#define P1_SHADOW_ENTRY_TEST
#define P1_C33_MATRIX_TEST
#define main unused_original49_regulator_main
#include P1_REGULATOR_SOURCE
#undef main

namespace seam {
struct Call {
  int side=0;
  bool injected=false, delegated=false;
  int rc=0;
  int64_t begin=0,end=0;
  double command=0;
};
struct Context {
  std::array<const rcl_publisher_t *,3> handles{};
  std::array<bool,3> fail{};
  std::vector<Call> calls;
};
std::atomic<Context *> active{nullptr};
using Native = rcl_ret_t (*)(const rcl_publisher_t *,const void *,rmw_publisher_allocation_t *);
Native real_publish(){
  static auto function=reinterpret_cast<Native>(dlsym(RTLD_NEXT,"rcl_publish"));
  return function;
}
}

// Present only in this test ELF, keyed by the three exact private handles.
// An injected error is a return-seam fact, never a claimed DDS failure.
extern "C" rcl_ret_t rcl_publish(const rcl_publisher_t *publisher,const void *message,
                                 rmw_publisher_allocation_t *allocation){
  auto native=seam::real_publish();
  if(!native){RCL_SET_ERROR_MSG("test50 actual rcl_publish unavailable");return RCL_RET_ERROR;}
  auto context=seam::active.load();
  int side=-1;
  if(context)for(int i=0;i<3;++i)if(publisher==context->handles[i])side=i;
  if(side<0)return native(publisher,message,allocation);
  seam::Call call;
  call.side=side;call.begin=p1::monotonic_ns();call.injected=context->fail[side];
  if(side<2)call.command=static_cast<const std_msgs::msg::Float64 *>(message)->data;
  if(call.injected){
    RCL_SET_ERROR_MSG("test50 declared private publisher return-seam failure");
    call.rc=RCL_RET_ERROR;
  }else{
    call.delegated=true;call.rc=native(publisher,message,allocation);
  }
  call.end=p1::monotonic_ns();context->calls.push_back(call);
  return call.rc;
}

class C33MatrixAccess {
 public:
  static std::unique_ptr<Regulator> make(const std::string &source,const std::string &base){
    stop_requested=false;
    p1::shadow::LegacyIdentity id{"p0-contract-v1","test50","test50-unit",controlled_phase::baseline,std::string(64,'a'),p1::boot_id()+":steady_clock"};
    auto r=std::unique_ptr<Regulator>(new Regulator(Regulator::ShadowTestTag{},source,id));
    std::ifstream in("/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/freeze/p1_execution_contract_v1.json");
    in>>r->c_;
    r->hash_=m4_owned::frozen_contract_sha;r->nominal_=r->c_.at("nominal_hash");r->mode_="execute";
    r->resources_=p1::resource_limits_from_contract(r->c_);
    r->limits_.low=-25;r->limits_.high=25;r->limits_.rho=80;r->limits_.hold_ns=600000000;
    r->limits_.tolerance=r->c_.at("activation_tolerance").get<p1::State>();
    r->left_=r->create_publisher<std_msgs::msg::Float64>(base+"/left",rclcpp::QoS(32).reliable());
    r->right_=r->create_publisher<std_msgs::msg::Float64>(base+"/right",rclcpp::QoS(32).reliable());
    r->own_applied_pub_=r->create_publisher<usv_research_interfaces::msg::AppliedControl>(base+"/applied",rclcpp::QoS(32).reliable());
    r->own_manifest_={{"producer_instance_id","component50_"+std::to_string(getpid())}};
    r->worker_liveness_=std::make_unique<p1::WorkerLiveness>(getpid());r->expected_worker_pid_=getpid();r->worker_valid_=true;
    r->capability_lease_->renew(p1::monotonic_ns());
    return r;
  }
  static void authority(Regulator &r){
    if(r.own_authority_)return;
    auto hex=[](const auto &pub){auto gid=pub->get_gid();return p1_owned::hex(gid.data,RMW_GID_STORAGE_SIZE);};
    p1::Json context={{"run_id","component50_"+std::to_string(getpid())},{"boot_id",p1::boot_id()},
      {"contract_sha256",m4_owned::frozen_contract_sha},{"freeze_evidence_sha256",m4_owned::frozen_index_sha},
      {"policy_sha256",p1::target_policy_sha256},{"regulator_manifest_sha256",p1_owned::sha256_bytes(r.own_manifest_.dump())},
      {"producer_id",r.own_manifest_.at("producer_instance_id")},{"role","p1_owned_execute_regulator"},
      {"pid",getpid()},{"start_ticks",p1_owned::process_start_ticks()},
      {"output_gids",p1::Json::array({hex(r.left_),hex(r.right_)})},
      {"old_outputs_absent",true},{"worker_output_count",0},{"fixture_output_count",0},{"recorder_output_count",0},
      {"worker_capability_live",true},{"recorder_ready",true},{"inputs_ready",true},{"source_graph_verified",true}};
    r.own_origin_ns_=p1::monotonic_ns()-1000000;
    r.own_authority_=std::make_unique<p1::owned_execution::OutputAuthority>(r.c_,context,context,r.own_origin_ns_);
  }
  static std::array<const rcl_publisher_t *,3> handles(Regulator &r){return {r.left_->get_publisher_handle().get(),r.right_->get_publisher_handle().get(),r.own_applied_pub_->get_publisher_handle().get()};}
  static bool matched(Regulator &r){return r.left_->get_subscription_count()==1&&r.right_->get_subscription_count()==1&&r.own_applied_pub_->get_subscription_count()==1;}
  static p1::Anchor anchor(Regulator &r){return r.anchor_;}
  static p1::Json state(Regulator &r){
    auto a=r.anchor_;
    return {{"known",a.known},{"n",a.n},{"start_ns",a.time},{"sequence",a.seq},
      {"authority_known",r.own_authority_->anchor().known},{"authority_n",r.own_authority_->anchor().n},
      {"authority_start_ns",r.own_authority_->anchor().time},{"authority_sequence",r.own_authority_->anchor().seq},
      {"authority_terminal",r.own_authority_->terminal()},{"authority_initialized",r.own_authority_->initialized()},
      {"business_permitted",r.own_authority_->business_permitted(p1::monotonic_ns())},
      {"normal_complete",r.normal_complete_.load()},{"worker_unusable",r.worker_unusable_.load()},
      {"stop_requested",stop_requested.load()},{"candidate_present",bool(r.candidate_)},{"pending_present",bool(r.pending_)},
      {"held_history_size",r.history_.size()},{"publication_history_size",r.publication_history_.size()}};
  }
  static void seed_slots(Regulator &r){r.candidate_=std::make_shared<p1::Candidate>();r.pending_=Regulator::Preparation{};}
  static void stopping(Regulator &r){r.stopping_=true;}
  static void publish(Regulator &r,p1::Decision &d){
    authority(r);auto now=p1::monotonic_ns();r.clock_receive_=now;r.sim_=100000000000LL+now-r.own_origin_ns_;
    d.activation_clock_sim_ns=r.sim_;d.activation_clock_receive_ns=now;
    d.tick_start_ns=d.tick_planned_ns=now;d.activation_commit_ns=now;
    if(d.candidate_accepted)r.last_accepted_=now;
    r.publish(d);
  }
  static bool finish(Regulator &r,const p1::Decision &d,int64_t now,int64_t &stop){
    r.capability_lease_->renew(p1::monotonic_ns());return r.finish_tick(d,now,now,d.tick,stop);
  }
  static std::optional<uint64_t> clear(Regulator &r){return r.invalidate_locked();}
  static void close(Regulator &r){r.sink_->close();}
};

class PublicationFault:public ::testing::Test {
 protected:
  static void SetUpTestSuite(){int argc=0;rclcpp::init(argc,nullptr,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);}
  static void TearDownTestSuite(){rclcpp::shutdown();}
  void SetUp()override{
    ASSERT_NE(std::getenv("P1_M4_COMPONENT_OUTPUT"),nullptr);
    const auto name=::testing::UnitTest::GetInstance()->current_test_info()->name();
    folder=std::filesystem::path(std::getenv("P1_M4_COMPONENT_OUTPUT"))/name;
    ASSERT_FALSE(std::filesystem::exists(folder));std::filesystem::create_directories(folder);
    base="/p1_m4_component_"+std::to_string(getpid())+"/"+name;
    r=C33MatrixAccess::make((folder/"source.jsonl").string(),base);
    receiver=std::make_shared<rclcpp::Node>("p1_m4_component_receiver",formal_owned::node_options());
    for(int i=0;i<3;++i){
      const std::string topic=base+(i==0?"/left":i==1?"/right":"/applied");
      const std::string type=i<2?"std_msgs/msg/Float64":"usv_research_interfaces/msg/AppliedControl";
      subscriptions.push_back(receiver->create_generic_subscription(topic,type,rclcpp::QoS(64).reliable(),
        [this,i,topic,type](std::shared_ptr<rclcpp::SerializedMessage> message){
          const auto &m=message->get_rcl_serialized_message();
          wire.push_back({{"side",i},{"topic",topic},{"type",type},{"received_ns",p1::monotonic_ns()},
            {"cdr_hex",p1_owned::hex(m.buffer,m.buffer_length)},{"bytes",m.buffer_length}});
        }));
    }
    executor.add_node(r->get_node_base_interface());executor.add_node(receiver);
    const auto until=p1::monotonic_ns()+3000000000LL;
    while(!C33MatrixAccess::matched(*r)&&p1::monotonic_ns()<until){executor.spin_some();std::this_thread::sleep_for(std::chrono::milliseconds(5));}
    ASSERT_TRUE(C33MatrixAccess::matched(*r));ASSERT_NE(seam::real_publish(),nullptr);
  }
  void TearDown()override{
    seam::active=nullptr;
    if(r){
      executor.spin_some();C33MatrixAccess::close(*r);
      std::ofstream out(folder/"case.json");
      out<<p1::Json{{"schema","M4-source-linked-private-publication-fault-case/v1"},
        {"case",::testing::UnitTest::GetInstance()->current_test_info()->name()},
        {"case_failed",HasFailure()},{"exact_production_source",P1_REGULATOR_SOURCE},
        {"exact_production_source_sha256",file_sha(P1_REGULATOR_SOURCE)},
        {"test_only_return_seam",true},{"seeded_owned_readiness_context",true},
        {"production_owned_gate_exercised",false},{"actuator_topic_publishers",0},
        {"observed_DDS_fault_claimed",false},{"plant_guarantee",false},{"M4_stage_qualified",false},
        {"steps",steps},{"wire",wire},{"extra",extra}}.dump(2)<<'\n';
      executor.remove_node(r->get_node_base_interface());executor.remove_node(receiver);subscriptions.clear();receiver.reset();r.reset();
    }
  }
  p1::Decision send(std::array<bool,3> fail={false,false,false},bool accepted=false,p1::Command command={0,0}){
    p1::Decision d;d.sequence=steps.size()+1;d.tick=steps.size();d.candidate_accepted=accepted;
    d.final_n=d.requested_n=command;d.control_source=accepted?"candidate":"ramp_zero";
    C33MatrixAccess::authority(*r);auto before=C33MatrixAccess::state(*r);
    seam::Context context;context.handles=C33MatrixAccess::handles(*r);context.fail=fail;
    seam::active=&context;C33MatrixAccess::publish(*r,d);seam::active=nullptr;
    p1::Json calls=p1::Json::array();size_t successful=0;
    for(const auto &c:context.calls){
      successful+=c.delegated&&c.rc==RCL_RET_OK;
      calls.push_back({{"side",c.side},{"injected",c.injected},{"delegated_to_actual_RCL",c.delegated},
        {"rc",c.rc},{"begin_ns",c.begin},{"end_ns",c.end},{"command",c.command}});
    }
    EXPECT_EQ(context.calls.size(),3u); // both control calls, then Applied attempt
    if(context.calls.size()==3){EXPECT_EQ(context.calls[0].side,0);EXPECT_EQ(context.calls[1].side,1);EXPECT_EQ(context.calls[2].side,2);}
    expected_wire+=successful;
    const auto until=p1::monotonic_ns()+1000000000LL;
    while(wire.size()<expected_wire&&p1::monotonic_ns()<until){executor.spin_some();std::this_thread::sleep_for(std::chrono::milliseconds(1));}
    executor.spin_some();EXPECT_EQ(wire.size(),expected_wire);
    auto after=C33MatrixAccess::state(*r);
    EXPECT_EQ(after["known"],after["authority_known"]);EXPECT_EQ(after["n"],after["authority_n"]);
    EXPECT_EQ(after["start_ns"],after["authority_start_ns"]);EXPECT_EQ(after["sequence"],after["authority_sequence"]);
    for(int i=0;i<2;++i){
      EXPECT_EQ(d.publish_success[i],!fail[i]);EXPECT_LE(d.publish_start_ns[i],d.publish_end_ns[i]);
      EXPECT_EQ(after["known"][i],!fail[i]);
      if(!fail[i]){EXPECT_EQ(after["n"][i],command[i]);EXPECT_EQ(after["start_ns"][i],d.publish_start_ns[i]);EXPECT_EQ(after["sequence"][i].get<uint64_t>(),before["sequence"][i].get<uint64_t>()+1);}
      else{EXPECT_EQ(after["n"][i],before["n"][i]);EXPECT_EQ(after["start_ns"][i],before["start_ns"][i]);EXPECT_EQ(after["sequence"][i],before["sequence"][i]);}
    }
    EXPECT_LE(d.publish_end_ns[0],d.publish_start_ns[1]);
    steps.push_back({{"decision",RegulatorDecision(d)},{"injected_sides",fail},{"calls",calls},{"before",before},{"after",after}});
    return d;
  }
  static p1::Json RegulatorDecision(const p1::Decision &d){return {{"sequence",d.sequence},{"accepted",d.candidate_accepted},{"command",d.final_n},
    {"starts",d.publish_start_ns},{"ends",d.publish_end_ns},{"returned",d.publish_success},{"rho_available",d.rho_available}};}
  void bootstrap(){auto d=send();EXPECT_FALSE(d.rho_available);EXPECT_FALSE(C33MatrixAccess::state(*r)["authority_terminal"].get<bool>());std::this_thread::sleep_for(std::chrono::milliseconds(15));}
  void terminal(){auto s=C33MatrixAccess::state(*r);EXPECT_TRUE(s["authority_terminal"].get<bool>());EXPECT_FALSE(s["normal_complete"].get<bool>());EXPECT_TRUE(s["worker_unusable"].get<bool>());EXPECT_TRUE(s["stop_requested"].get<bool>());EXPECT_FALSE(s["business_permitted"].get<bool>());}
  void shutdown_case(const std::array<bool,3> &fail){
    bootstrap();C33MatrixAccess::stopping(*r);auto d=send(fail);int64_t now=p1::monotonic_ns(),stop=now;
    bool exited=C33MatrixAccess::finish(*r,d,now,stop);EXPECT_TRUE(exited);extra={{"finish_exit_tick",exited},{"stop_start_ns",stop},{"finish_now_ns",now}};
    if(fail[0]||fail[1])terminal();
  }
  std::unique_ptr<Regulator> r;
  std::shared_ptr<rclcpp::Node> receiver;
  std::vector<std::shared_ptr<rclcpp::GenericSubscription>> subscriptions;
  rclcpp::executors::SingleThreadedExecutor executor;
  std::filesystem::path folder;
  std::string base;
  p1::Json wire=p1::Json::array(),steps=p1::Json::array(),extra=p1::Json::object();
  size_t expected_wire=0;
};

TEST_F(PublicationFault,BootstrapBothSuccess){auto d=send();EXPECT_FALSE(d.rho_available);EXPECT_TRUE(C33MatrixAccess::state(*r)["authority_initialized"].get<bool>());}
TEST_F(PublicationFault,BootstrapLeftFailure){send({true,false,false});terminal();}
TEST_F(PublicationFault,BootstrapRightFailure){send({false,true,false});terminal();}
TEST_F(PublicationFault,BootstrapBothFailure){send({true,true,false});terminal();}
TEST_F(PublicationFault,AcceptedLeftFailureClearsCandidateAndPending){bootstrap();C33MatrixAccess::seed_slots(*r);send({true,false,false},true,{.5,-.5});terminal();auto s=C33MatrixAccess::state(*r);EXPECT_FALSE(s["candidate_present"].get<bool>());EXPECT_FALSE(s["pending_present"].get<bool>());}
TEST_F(PublicationFault,AcceptedRightFailureRetainsLeft){bootstrap();send({false,true,false},true,{.5,-.5});terminal();}
TEST_F(PublicationFault,AcceptedBothFailure){bootstrap();send({true,true,false},true,{.5,-.5});terminal();}
TEST_F(PublicationFault,ShutdownBothSuccess){shutdown_case({false,false,false});}
TEST_F(PublicationFault,ShutdownLeftFailure){shutdown_case({true,false,false});}
TEST_F(PublicationFault,ShutdownRightFailure){shutdown_case({false,true,false});}
TEST_F(PublicationFault,ShutdownBothFailure){shutdown_case({true,true,false});}
TEST_F(PublicationFault,PartialThenZeroCannotResurrectBusiness){bootstrap();send({true,false,false},true,{.5,-.5});terminal();C33MatrixAccess::stopping(*r);std::this_thread::sleep_for(std::chrono::milliseconds(15));send();terminal();}
TEST_F(PublicationFault,AppliedFailureCannotRollBackSuccessfulControl){bootstrap();send({false,false,true},true,{.5,-.5});auto s=C33MatrixAccess::state(*r);EXPECT_TRUE(s["normal_complete"]==false);EXPECT_TRUE(s["worker_unusable"].get<bool>());EXPECT_TRUE(s["stop_requested"].get<bool>());EXPECT_TRUE(s["known"][0].get<bool>());EXPECT_TRUE(s["known"][1].get<bool>());}
TEST_F(PublicationFault,ShutdownGraceBeforeNonzeroDoesNotExit){bootstrap();auto d=send({},true,{.5,-.5});C33MatrixAccess::stopping(*r);int64_t now=p1::monotonic_ns(),stop=now-2500000000LL+1;const auto before=stop;bool exit=C33MatrixAccess::finish(*r,d,now,stop);EXPECT_FALSE(exit);extra={{"finish_exit_tick",exit},{"finish_now_ns",now},{"stop_start_ns",before},{"seeded_grace_time_boundary",true}};}
TEST_F(PublicationFault,ShutdownGraceEqualityNonzeroExitsWithoutZeroClaim){bootstrap();auto d=send({},true,{.5,-.5});C33MatrixAccess::stopping(*r);int64_t now=p1::monotonic_ns(),stop=now-2500000000LL;const auto before=stop;bool exit=C33MatrixAccess::finish(*r,d,now,stop);EXPECT_TRUE(exit);extra={{"finish_exit_tick",exit},{"finish_now_ns",now},{"stop_start_ns",before},{"seeded_grace_time_boundary",true}};}
TEST_F(PublicationFault,ClearInvalidatesCandidatePendingWithoutRewritingAnchors){bootstrap();auto old=C33MatrixAccess::anchor(*r);C33MatrixAccess::seed_slots(*r);auto cleared=C33MatrixAccess::clear(*r);ASSERT_TRUE(cleared);EXPECT_EQ(*cleared,1u);auto s=C33MatrixAccess::state(*r);EXPECT_FALSE(s["candidate_present"].get<bool>());EXPECT_FALSE(s["pending_present"].get<bool>());auto now=C33MatrixAccess::anchor(*r);EXPECT_EQ(now.n,old.n);EXPECT_EQ(now.time,old.time);EXPECT_EQ(now.seq,old.seq);EXPECT_EQ(now.known,old.known);extra={{"cleared_pending_target",*cleared},{"real_clear_called",true}};}
