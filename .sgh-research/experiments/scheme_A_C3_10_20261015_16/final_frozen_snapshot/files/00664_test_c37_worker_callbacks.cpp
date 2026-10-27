// SPDX-License-Identifier: MIT
// Source-including tests of actual Regulator Worker receive/guard paths.
// The owned Worker identity and callback GIDs come from actual DataWriters.
// Jobs and over-bound typed objects are explicitly seeded finite fixtures;
// they are not a solver, owned-runtime closure, or middleware budget proof.
#include <gtest/gtest.h>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <spawn.h>
#include <sys/wait.h>
#include "owned_worker_peer_c37_v1.hpp"
#define P1_SHADOW_ENTRY_TEST
#define P1_LEGACY_READY_TEST
#define P1_C37_WORKER_CALLBACK_TEST
#define main p1_c37_worker_callbacks_program_main
#include P1_REGULATOR_SOURCE
#undef main
extern char **environ;

// As in the source-linked atomic fixture, identity compares full decoded typed
// fields with exact IEEE float64 bits. Each retained CDR is decoded separately;
// unrelated alignment padding is not semantic payload identity.
static p1::Json c37_ieee_payload(const p1::Json &value) {
  if(value.is_number_float())return {{"float64_ieee754",p1_owned::double_canonical(value.get<double>())}};
  auto out=value;if(out.is_array()||out.is_object())for(auto &element:out)element=c37_ieee_payload(element);
  return out;
}
static p1::Json c37_typed_payload(const p1::Candidate &m) {
  return c37_ieee_payload({{"job",p1::job_json(m.job)},
    {"worker_instance",m.worker_instance},{"worker_receive_ns",m.worker_receive_ns},
    {"solve_start_ns",m.solve_start_ns},{"solve_end_ns",m.solve_end_ns},
    {"solver_invoked",m.solver_invoked},{"success",m.success},
    {"prediction_available",m.prediction_available},{"reason",m.reason},
    {"backend",m.backend},{"backend_ms",m.backend_ms},{"first_control",m.first_control},
    {"x_prediction",m.x_prediction},{"u_prediction",m.u_prediction}});
}
static p1::Json c37_typed_payload(const p1::Capability &m) {
  return c37_ieee_payload({{"schema_version",m.schema_version},{"run_id",m.run_id},{"boot_id",m.boot_id},
    {"contract_hash",m.contract_hash},{"nominal_hash",m.nominal_hash},{"worker_instance",m.worker_instance},
    {"clock_name",m.clock_name},{"backend",m.backend},{"matrix_layout",m.matrix_layout},
    {"horizon_steps",m.horizon_steps},{"prediction_dt",m.prediction_dt},{"pid",m.pid},
    {"startup_ns",m.startup_ns},{"completed_jobs",m.completed_jobs},{"active_job",m.active_job},
    {"pending_count",m.pending_count},{"fault_injection_enabled",m.fault_injection_enabled},
    {"fatal",m.fatal},{"reason",m.reason}});
}
template<class Message>static Message c37_decoded_payload(const std::string &raw) {
  p1_owned::require(raw.size()>=4&&raw.size()<=16384,"test retained CDR bound");
  rclcpp::SerializedMessage serialized(raw.size());auto &buffer=serialized.get_rcl_serialized_message();
  p1_owned::require(buffer.buffer_capacity>=raw.size(),"test CDR capacity");
  std::memcpy(buffer.buffer,raw.data(),raw.size());buffer.buffer_length=raw.size();
  Message decoded;rclcpp::Serialization<Message> serializer;serializer.deserialize_message(&serialized,&decoded);
  return decoded;
}

// Only this object owns this spawned PID. No shell or existing process is used.
class C37ControlledChild {
 public:
  C37ControlledChild(const std::string &binary,const std::filesystem::path &folder,
      const std::filesystem::path &output) {
    posix_spawn_file_actions_t actions{};posix_spawnattr_t attributes{};
    p1_owned::require(::posix_spawn_file_actions_init(&actions)==0,"child file actions init");
    const auto initialized=::posix_spawnattr_init(&attributes);
    if(initialized!=0){::posix_spawn_file_actions_destroy(&actions);throw std::runtime_error("child attributes init");}
    const auto cleanup=[&]{::posix_spawn_file_actions_destroy(&actions);::posix_spawnattr_destroy(&attributes);};
    const auto stdout_path=(output/"controlled_child_stdout.log").string();
    const auto stderr_path=(output/"controlled_child_stderr.log").string();
    if(::posix_spawn_file_actions_addopen(&actions,STDOUT_FILENO,stdout_path.c_str(),O_WRONLY|O_CREAT|O_EXCL,0600)!=0||
       ::posix_spawn_file_actions_addopen(&actions,STDERR_FILENO,stderr_path.c_str(),O_WRONLY|O_CREAT|O_EXCL,0600)!=0||
       ::posix_spawnattr_setflags(&attributes,POSIX_SPAWN_SETPGROUP)!=0||
       ::posix_spawnattr_setpgroup(&attributes,0)!=0){cleanup();throw std::runtime_error("child spawn registration");}
    auto executable=binary;auto argument=folder.string();
    char flag[]="--fixture-dir";char *argv[]={executable.data(),flag,argument.data(),nullptr};
    const auto result=::posix_spawn(&pid_,executable.c_str(),&actions,&attributes,argv,environ);cleanup();
    p1_owned::require(result==0&&pid_>0,"registered exec-child spawn failed");
  }
  ~C37ControlledChild(){
    if(pid_<=0||reaped_)return;
    int status=0;pid_t observed;
    do{observed=::waitpid(pid_,&status,WNOHANG);}while(observed<0&&errno==EINTR);
    if(observed==pid_){reaped_=true;return;}
    // An unreaped direct child cannot have its PID reused. Failure cleanup
    // terminates only our registered child and waits for its terminal status.
    if(observed==0){::kill(pid_,SIGKILL);do{observed=::waitpid(pid_,&status,0);}while(observed<0&&errno==EINTR);}
  }
  pid_t pid()const{return pid_;}
  bool wait_normal(double seconds,int &status){
    const auto deadline=std::chrono::steady_clock::now()+std::chrono::duration<double>(seconds);
    while(std::chrono::steady_clock::now()<deadline){const auto observed=::waitpid(pid_,&status,WNOHANG);
      if(observed==pid_){reaped_=true;return true;}
      if(observed<0&&errno!=EINTR)throw std::runtime_error("registered child waitpid failed");
      std::this_thread::sleep_for(std::chrono::milliseconds(2));}return false;
  }
 private:pid_t pid_=-1;bool reaped_=false;
};

class C37WorkerCallbackAccess {
 public:
  static std::unique_ptr<Regulator> make(const std::string& file) {
    stop_requested=false;
    p1::shadow::LegacyIdentity legacy{"p0-contract-v1","worker-callback-publisher",
      "worker-callback-producer","F5_20261005_atomic_freeze_01",std::string(64,'a'),
      p1::boot_id()+":steady_clock"};
    return std::unique_ptr<Regulator>(new Regulator(Regulator::LegacyReadyTestTag{},file,legacy));
  }
  static p1::Json identity(Regulator &r) {
    return {{"run_id",r.run_},{"boot_id",r.boot_},{"contract_sha256",r.hash_},{"nominal_hash",r.nominal_}};
  }
  static void install(Regulator &r,const c37_owned::WorkerPins &pins) {
    r.worker_peer_=std::make_unique<c37_owned::OwnedWorkerPeer>(pins);
  }
  static void install_child(Regulator &r,const c37_owned::WorkerPins &pins) {
    r.worker_peer_=std::make_unique<c37_owned::OwnedWorkerPeer>(pins);
    r.expected_worker_pid_=pins.pid;
    r.worker_liveness_=std::make_unique<p1::WorkerLiveness>(pins.pid);
  }
  static bool worker_peer_alive(Regulator &r){return r.worker_peer_->alive();}
  static std::string worker_authentication(Regulator &r,const rclcpp::MessageInfo &info){
    return r.worker_peer_->callback_reason(info,c37_owned::Interface::Capability);
  }
  template<class T> static void receive(Regulator &r,const T &m,const rclcpp::MessageInfo &info,
    c37_owned::Interface interface) { r.receive_worker(m,info,interface); }
  static p1::Json state(Regulator &r) {
    std::lock_guard<std::mutex> lock(r.mutex_);
    auto state=r.worker_callback_snapshot_locked();
    state["capability_received"]=r.worker_capability_received_;
    state["candidate_received"]=r.worker_candidate_received_;
    state["input_commit_ordinal"]=r.input_commit_ordinal_;
    return state;
  }
  static p1::Candidate seed_candidate(Regulator &r) {
    std::lock_guard<std::mutex> lock(r.mutex_);
    const auto now=p1::monotonic_ns();
    r.version_={1,1,1,1,0};r.current_tick_=0;
    p1::Candidate m;auto& j=m.job;
    j.schema_version="p1-solve-job-v1";j.run_id=r.run_;j.boot_id=r.boot_;
    j.contract_hash=r.hash_;j.nominal_hash=r.nominal_;j.worker_instance=r.worker_instance_;
    j.job_id=1;j.target_tick=1;j.task_generation=1;j.model_generation=1;
    j.config_generation=1;j.schedule_generation=1;j.clock_epoch=0;
    j.tick_origin_steady_ns=now-10000000;j.freeze_steady_ns=now-5000000;
    j.deadline_steady_ns=j.tick_origin_steady_ns+p1::DEADLINE;
    j.target_steady_ns=j.tick_origin_steady_ns+p1::T;
    j.odom_stamp_ns=1000000000;j.target_sim_ns=1200000000;
    j.odom_receive_ns=j.freeze_steady_ns-1000;j.odom_sequence=1;
    j.horizon_steps=20;j.prediction_dt=.2;
    j.target_state={1,2,.1,.2,.3,.4};j.frozen_state=j.target_state;
    j.anchor_n={0,0};j.anchor_sequence={1,1};j.anchor_known={true,true};
    j.anchor_publish_ns={j.tick_origin_steady_ns-1000,j.tick_origin_steady_ns-500};
    j.frozen_clock_sim_ns=1000000000;
    j.frozen_clock_receive_ns=j.freeze_steady_ns-1000;j.assumed_rtf=1;
    j.anchor_source="legacy_publisher";j.anchor_producer="worker-callback-producer";
    j.anchor_run_id="worker-callback-publisher";
    j.history_sim_ns={1000000000,1000000000};j.history_channel={0,1};j.history_n={0,0};
    m.worker_instance=r.worker_instance_;m.worker_receive_ns=j.freeze_steady_ns;
    m.solve_start_ns=j.freeze_steady_ns;m.solve_end_ns=j.freeze_steady_ns;
    m.backend="acados";m.backend_ms=0;
    m.success=true;m.prediction_available=true;m.solver_invoked=true;
    m.first_control={1,2};m.u_prediction[0]=1;m.u_prediction[1]=2;
    std::copy(j.target_state.begin(),j.target_state.end(),m.x_prediction.begin());
    r.jobs_.push_back(j);
    return m;
  }
  static std::vector<p1::Json> rows(Regulator &r,const std::filesystem::path& file) {
    r.sink_->close();std::ifstream input(file);std::string line;std::vector<p1::Json> out;
    while(std::getline(input,line))out.push_back(p1::Json::parse(line));
    return out;
  }
};

class C37WorkerCallbacks:public ::testing::Test {
 protected:
  using Interface=c37_owned::Interface;
  static void SetUpTestSuite(){int argc=0;rclcpp::init(argc,nullptr,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);}
  static void TearDownTestSuite(){rclcpp::shutdown();}
  static rclcpp::NodeOptions options(){return rclcpp::NodeOptions().enable_rosout(false)
    .start_parameter_services(false).start_parameter_event_publisher(false).use_intra_process_comms(false);}
  void SetUp()override{
    const auto* base=std::getenv("P1_BRANCH_TEST_OUTPUT");ASSERT_NE(base,nullptr);
    folder=std::filesystem::path(base)/(std::string("C37WorkerCallbacks_")+::testing::UnitTest::GetInstance()->current_test_info()->name());
    ASSERT_FALSE(std::filesystem::exists(folder));std::filesystem::create_directories(folder);
    source=folder/"source.jsonl";r=C37WorkerCallbackAccess::make(source.string());
    owner=std::make_shared<rclcpp::Node>("c37_callback_worker",options());
    foreign=std::make_shared<rclcpp::Node>("c37_callback_worker",options());
    reader=std::make_shared<rclcpp::Node>("c37_callback_reader",options());
    capability_pub=owner->create_publisher<p1::Capability>("/p1/worker_capability",rclcpp::QoS(10).reliable());
    candidate_pub=owner->create_publisher<p1::Candidate>("/p1/solve_candidate",rclcpp::QoS(10).reliable());
    foreign_capability_pub=foreign->create_publisher<p1::Capability>("/p1/worker_capability",rclcpp::QoS(10).reliable());
    foreign_candidate_pub=foreign->create_publisher<p1::Candidate>("/p1/solve_candidate",rclcpp::QoS(10).reliable());
    capability_sub=reader->create_subscription<p1::Capability>("/p1/worker_capability",rclcpp::QoS(10).reliable(),
      [this](p1::Capability::SharedPtr m,const rclcpp::MessageInfo &info){
        capability_metadata.push_back(info);capability_cdr.push_back(serialized(*m));capability_messages.push_back(*m);
        if(dispatch_capability)C37WorkerCallbackAccess::receive(*r,*m,info,Interface::Capability);
      });
    candidate_sub=reader->create_subscription<p1::Candidate>("/p1/solve_candidate",rclcpp::QoS(10).reliable(),
      [this](p1::Candidate::SharedPtr m,const rclcpp::MessageInfo &info){
        candidate_metadata.push_back(info);candidate_cdr.push_back(serialized(*m));
        if(dispatch_candidate)C37WorkerCallbackAccess::receive(*r,*m,info,Interface::Candidate);
      });
    executor=std::make_unique<rclcpp::executors::SingleThreadedExecutor>();
    executor->add_node(owner);executor->add_node(foreign);executor->add_node(reader);
    ASSERT_TRUE(wait_for([this]{return capability_pub->get_subscription_count()==1 &&
      candidate_pub->get_subscription_count()==1 && foreign_capability_pub->get_subscription_count()==1 &&
      foreign_candidate_pub->get_subscription_count()==1;}));
    const auto id=C37WorkerCallbackAccess::identity(*r);const auto manifest_path=(folder/"worker_manifest.json").string();
    owner->declare_parameter<std::string>("run_id",id.at("run_id").get<std::string>());
    owner->declare_parameter<std::string>("contract_hash",id.at("contract_sha256").get<std::string>());
    owner->declare_parameter<std::string>("owned_manifest_file",manifest_path);
    frozen=p1_owned::freeze_parameters(*owner);
    const auto manifest=p1_owned::role_manifest(*owner,"worker",id.at("run_id"),id.at("contract_sha256"),
      std::string(64,'b'),p1::Json::array({
        p1_owned::publisher_endpoint(*capability_pub,"usv_research_interfaces/msg/WorkerCapability"),
        p1_owned::publisher_endpoint(*candidate_pub,"usv_research_interfaces/msg/SolveCandidate")}),
      {{"worker_instance",std::string(64,'e')},{"nominal_hash",id.at("nominal_hash")},
       {"contract_configuration",{{"nominal_hash",id.at("nominal_hash")},{"execute_qualified",false}}}});
    const auto raw=manifest.dump()+"\n";{std::ofstream file(manifest_path);file<<raw;}
    c37_owned::WorkerPins pins;
    pins.manifest_path=manifest_path;pins.manifest_sha256=p1_owned::sha256_bytes(raw);
    pins.run_id=manifest.at("run_id");pins.boot_id=manifest.at("boot_id");
    pins.contract_sha256=manifest.at("contract_sha256");pins.worker_instance=manifest.at("worker_instance");
    pins.nominal_hash=manifest.at("nominal_hash");pins.exe=manifest.at("exe");
    pins.binary_sha256=manifest.at("binary_sha256");pins.source_bundle_sha256=manifest.at("source_bundle_sha256");
    pins.effective_parameters_sha256=manifest.at("effective_parameters_sha256");
    pins.pid=manifest.at("pid").get<int64_t>();pins.process_start_ticks=manifest.at("process_start_ticks").get<uint64_t>();
    C37WorkerCallbackAccess::install(*r,pins);
    cap.schema_version="p1-worker-capability-v1";cap.run_id=pins.run_id;cap.boot_id=pins.boot_id;
    cap.contract_hash=pins.contract_sha256;cap.nominal_hash=pins.nominal_hash;cap.worker_instance=pins.worker_instance;
    cap.clock_name="CLOCK_MONOTONIC";cap.backend="acados";cap.matrix_layout="column_major";
    cap.horizon_steps=20;cap.prediction_dt=.2;cap.pid=getpid();cap.startup_ns=p1::monotonic_ns()-1000;
    cap.fault_injection_enabled=true;
  }
  void TearDown()override{
    executor.reset();capability_sub.reset();candidate_sub.reset();
    capability_pub.reset();candidate_pub.reset();foreign_capability_pub.reset();foreign_candidate_pub.reset();
    frozen.reset();reader.reset();foreign.reset();owner.reset();r.reset();
  }
  template<class T>static std::string serialized(const T &m){
    rclcpp::Serialization<T> serializer;rclcpp::SerializedMessage serialized;
    serializer.serialize_message(&m,&serialized);const auto &cdr=serialized.get_rcl_serialized_message();
    return std::string(reinterpret_cast<const char*>(cdr.buffer),cdr.buffer_length);
  }
  bool wait_for(const std::function<bool()> &predicate,double seconds=4){
    const auto end=std::chrono::steady_clock::now()+std::chrono::duration<double>(seconds);
    while(std::chrono::steady_clock::now()<end){executor->spin_some();if(predicate())return true;
      std::this_thread::sleep_for(std::chrono::milliseconds(2));}return false;
  }
  void valid_capability(){const auto n=capability_metadata.size();capability_pub->publish(cap);
    ASSERT_TRUE(wait_for([this,n]{return capability_metadata.size()==n+1;}));
    ASSERT_TRUE(state().at("worker_valid").get<bool>());}
  p1::Candidate prepared_candidate(){auto m=C37WorkerCallbackAccess::seed_candidate(*r);
    EXPECT_EQ(p1::valid_job(m.job,m.job.run_id,m.job.boot_id,m.job.contract_hash,m.job.nominal_hash,m.worker_instance),"");return m;}
  void valid_candidate(const p1::Candidate &m){dispatch_candidate=true;const auto n=candidate_metadata.size();candidate_pub->publish(m);
    ASSERT_TRUE(wait_for([this,n]{return candidate_metadata.size()==n+1;}));}
  p1::Json state(){return C37WorkerCallbackAccess::state(*r);}
  std::vector<p1::Json> rows(){return C37WorkerCallbackAccess::rows(*r,source);}
  static p1::Json last(const std::vector<p1::Json>& rows,const std::string &type){
    p1::Json result=nullptr;for(const auto &row:rows)if(row.value("type","")==type)result=row;return result;}
  static void trusted_equal(const p1::Json &before,const p1::Json &after){
    for(const auto *key:{"worker_instance","worker_valid","worker_unusable","lease_last_valid_ns","candidate_present","admission_slots"})
      EXPECT_EQ(before.at(key),after.at(key))<<key;
  }
  std::filesystem::path folder,source;std::unique_ptr<Regulator> r;
  rclcpp::Node::SharedPtr owner,foreign,reader;
  rclcpp::Publisher<p1::Capability>::SharedPtr capability_pub,foreign_capability_pub;
  rclcpp::Publisher<p1::Candidate>::SharedPtr candidate_pub,foreign_candidate_pub;
  rclcpp::Subscription<p1::Capability>::SharedPtr capability_sub;
  rclcpp::Subscription<p1::Candidate>::SharedPtr candidate_sub;
  rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr frozen;
  std::unique_ptr<rclcpp::executors::SingleThreadedExecutor> executor;
  std::vector<rclcpp::MessageInfo> capability_metadata,candidate_metadata;
  std::vector<p1::Capability> capability_messages;
  std::vector<std::string> capability_cdr,candidate_cdr;
  bool dispatch_capability=true,dispatch_candidate=false;p1::Capability cap;
};

TEST_F(C37WorkerCallbacks,ActualValidCapabilityRenewsLeaseAndCountsOneReceivedPacket){
  const auto before=state();EXPECT_EQ(before.at("lease_last_valid_ns"),0);
  valid_capability();const auto after=state();
  EXPECT_GT(after.at("lease_last_valid_ns").get<int64_t>(),0);EXPECT_FALSE(after.at("worker_unusable").get<bool>());
  EXPECT_EQ(after.at("capability_received"),1);EXPECT_EQ(after.at("input_commit_ordinal"),before.at("input_commit_ordinal").get<uint64_t>()+1);
  const auto row=last(rows(),"capability_admission");ASSERT_TRUE(row.is_object());EXPECT_TRUE(row.at("renewed").get<bool>());
}
TEST_F(C37WorkerCallbacks,ActualSamePayloadForeignCapabilityDoesNotRenewOrTerminalizeTrustedWorker){
  valid_capability();const auto before=state();foreign_capability_pub->publish(cap);
  ASSERT_TRUE(wait_for([this]{return capability_metadata.size()==2;}));
  trusted_equal(before,state());EXPECT_EQ(state().at("capability_received"),2);
  EXPECT_EQ(state().at("input_commit_ordinal"),before.at("input_commit_ordinal").get<uint64_t>()+1);
  const auto first=c37_typed_payload(c37_decoded_payload<p1::Capability>(capability_cdr[0]));
  EXPECT_EQ(first,c37_typed_payload(c37_decoded_payload<p1::Capability>(capability_cdr[1])));
  EXPECT_EQ(first,c37_typed_payload(cap));
  const auto row=last(rows(),"adapter_worker_callback");ASSERT_TRUE(row.is_object());
  EXPECT_EQ(row.at("authentication_reason"),"callback_foreign_gid");
}
TEST_F(C37WorkerCallbacks,ActualForeignCapabilityBeforeFirstValidDoesNotBindOrRenew){
  const auto before=state();foreign_capability_pub->publish(cap);
  ASSERT_TRUE(wait_for([this]{return capability_metadata.size()==1;}));
  trusted_equal(before,state());EXPECT_EQ(state().at("capability_received"),1);
  EXPECT_EQ(state().at("lease_last_valid_ns"),0);
}
TEST_F(C37WorkerCallbacks,ActualCandidateDataWriterMetadataCannotRenewCapabilityLease){
  valid_capability();p1::Candidate m;m.worker_instance=cap.worker_instance;
  candidate_pub->publish(m);ASSERT_TRUE(wait_for([this]{return candidate_metadata.size()==1;}));
  const auto before=state();C37WorkerCallbackAccess::receive(*r,cap,candidate_metadata[0],Interface::Capability);
  trusted_equal(before,state());EXPECT_EQ(state().at("capability_received"),2);
  const auto row=last(rows(),"adapter_worker_callback");ASSERT_TRUE(row.is_object());
  EXPECT_EQ(row.at("authentication_reason"),"callback_foreign_gid");
}
TEST_F(C37WorkerCallbacks,ActualReceiveResourceBranchRejectsOverBoundTypedCapabilityBeforeSerialization){
  valid_capability();const auto before=state();auto over=cap;over.reason=std::string(257,'x');
  C37WorkerCallbackAccess::receive(*r,over,capability_metadata[0],Interface::Capability);
  trusted_equal(before,state());EXPECT_EQ(state().at("capability_received"),2);
  const auto row=last(rows(),"adapter_worker_callback");ASSERT_TRUE(row.is_object());
  EXPECT_FALSE(row.at("full_cdr_serialized").get<bool>());
}
TEST_F(C37WorkerCallbacks,ActualAuthenticatedFatalCapabilityPreservesOriginalTerminalPolicy){
  valid_capability();auto fatal=cap;fatal.fatal=true;capability_pub->publish(fatal);
  ASSERT_TRUE(wait_for([this]{return capability_metadata.size()==2;}));
  EXPECT_TRUE(state().at("worker_unusable").get<bool>());
  const auto row=last(rows(),"capability_admission");ASSERT_TRUE(row.is_object());
  EXPECT_TRUE(row.at("terminal_run").get<bool>());EXPECT_FALSE(row.at("renewed").get<bool>());
}
TEST_F(C37WorkerCallbacks,ActualValidCandidateWithFullSeededNativeJobRegistersReady){
  valid_capability();const auto m=prepared_candidate();valid_candidate(m);
  EXPECT_TRUE(state().at("candidate_present").get<bool>());EXPECT_EQ(state().at("admission_slots"),1);
  EXPECT_EQ(state().at("candidate_received"),1);
  const auto row=last(rows(),"candidate_registration");ASSERT_TRUE(row.is_object());
  EXPECT_TRUE(row.at("accepted_registration").get<bool>());EXPECT_EQ(row.at("reason"),"");
}
TEST_F(C37WorkerCallbacks,ActualForeignCandidateDoesNotRegisterOrMutateTrustedState){
  valid_capability();const auto m=prepared_candidate();const auto before=state();dispatch_candidate=true;
  foreign_candidate_pub->publish(m);ASSERT_TRUE(wait_for([this]{return candidate_metadata.size()==1;}));
  trusted_equal(before,state());EXPECT_EQ(state().at("candidate_received"),1);
  const auto all=rows();EXPECT_TRUE(last(all,"candidate_registration").is_null());
  EXPECT_EQ(last(all,"adapter_worker_callback").at("authentication_reason"),"callback_foreign_gid");
}
TEST_F(C37WorkerCallbacks,ActualSamePayloadForeignCandidatePreservesExistingReadySlot){
  valid_capability();const auto m=prepared_candidate();valid_candidate(m);
  ASSERT_TRUE(state().at("candidate_present").get<bool>());const auto before=state();
  foreign_candidate_pub->publish(m);ASSERT_TRUE(wait_for([this]{return candidate_metadata.size()==2;}));
  trusted_equal(before,state());EXPECT_EQ(state().at("candidate_received"),2);
  const auto first=c37_typed_payload(c37_decoded_payload<p1::Candidate>(candidate_cdr[0]));
  EXPECT_EQ(first,c37_typed_payload(c37_decoded_payload<p1::Candidate>(candidate_cdr[1])));
  EXPECT_EQ(first,c37_typed_payload(m));
  const auto all=rows();const auto row=last(all,"adapter_worker_callback");
  EXPECT_EQ(row.at("authentication_reason"),"callback_foreign_gid");
  size_t registrations=0;for(const auto &entry:all)if(entry.value("type","")=="candidate_registration")++registrations;
  EXPECT_EQ(registrations,1);
}
TEST_F(C37WorkerCallbacks,ActualReceiveResourceBranchRejectsOverBoundTypedCandidateAndPreservesReady){
  valid_capability();const auto m=prepared_candidate();valid_candidate(m);
  const auto before=state();auto over=m;over.reason=std::string(257,'x');
  C37WorkerCallbackAccess::receive(*r,over,candidate_metadata[0],Interface::Candidate);
  trusted_equal(before,state());EXPECT_EQ(state().at("candidate_received"),2);
  const auto row=last(rows(),"adapter_worker_callback");ASSERT_TRUE(row.is_object());
  EXPECT_FALSE(row.at("full_cdr_serialized").get<bool>());
}
TEST_F(C37WorkerCallbacks,ActualValidGidCandidateStillRequiresFullJobEcho){
  valid_capability();auto m=prepared_candidate();m.job.reference[1]=0.5;valid_candidate(m);
  EXPECT_FALSE(state().at("candidate_present").get<bool>());EXPECT_EQ(state().at("admission_slots"),0);
  const auto row=last(rows(),"candidate_registration");ASSERT_TRUE(row.is_object());
  EXPECT_FALSE(row.at("accepted_registration").get<bool>());EXPECT_EQ(row.at("reason"),"job_echo_mismatch");
}
TEST_F(C37WorkerCallbacks,ActualCapabilityDataWriterMetadataCannotRegisterCandidate){
  valid_capability();auto m=prepared_candidate();const auto before=state();
  C37WorkerCallbackAccess::receive(*r,m,capability_metadata[0],Interface::Candidate);
  trusted_equal(before,state());EXPECT_EQ(state().at("candidate_received"),1);
  const auto all=rows();EXPECT_TRUE(last(all,"candidate_registration").is_null());
  EXPECT_EQ(last(all,"adapter_worker_callback").at("authentication_reason"),"callback_foreign_gid");
}

TEST_F(C37WorkerCallbacks,RegisteredExecChildExitRejectsHeldActualCapabilityBeforeSemanticCallback){
  const auto *registered_binary=std::getenv("C37_WORKER_CHILD_BIN");ASSERT_NE(registered_binary,nullptr);
  const std::string binary(registered_binary);ASSERT_TRUE(std::filesystem::path(binary).is_absolute());
  const auto independently_expected_binary_sha=c36_owned::detail::process_binary_sha(binary);
  const auto child_folder=folder/"controlled_child";ASSERT_FALSE(std::filesystem::exists(child_folder));
  dispatch_capability=false;C37ControlledChild child(binary,child_folder,folder);
  const auto manifest_path=child_folder/"owned_manifest.json";
  ASSERT_TRUE(wait_for([&]{return std::filesystem::is_regular_file(manifest_path);}));
  const auto raw=c36_owned::detail::read_manifest(manifest_path.string());
  const auto manifest=c36_owned::detail::strict_json(raw);
  const auto id=C37WorkerCallbackAccess::identity(*r);
  ASSERT_EQ(manifest.at("pid"),child.pid());ASSERT_EQ(manifest.at("run_id"),id.at("run_id"));
  ASSERT_EQ(manifest.at("boot_id"),p1_owned::boot_id());ASSERT_EQ(manifest.at("contract_sha256"),id.at("contract_sha256"));
  ASSERT_EQ(manifest.at("nominal_hash"),id.at("nominal_hash"));
  ASSERT_EQ(manifest.at("binary_sha256"),independently_expected_binary_sha);
  ASSERT_EQ(manifest.at("source_bundle_sha256"),P1_OWNED_SOURCE_BUNDLE_SHA256);
  c37_owned::WorkerPins pins;
  pins.manifest_path=manifest_path.string();pins.manifest_sha256=p1_owned::sha256_bytes(raw);
  pins.run_id=id.at("run_id");pins.boot_id=p1_owned::boot_id();pins.contract_sha256=id.at("contract_sha256");
  pins.worker_instance=std::string(64,'e');pins.nominal_hash=id.at("nominal_hash");
  pins.exe=binary;pins.binary_sha256=independently_expected_binary_sha;
  pins.source_bundle_sha256=P1_OWNED_SOURCE_BUNDLE_SHA256;
  pins.effective_parameters_sha256=manifest.at("effective_parameters_sha256");
  pins.pid=child.pid();pins.process_start_ticks=manifest.at("process_start_ticks").get<uint64_t>();
  C37WorkerCallbackAccess::install_child(*r,pins);
  ASSERT_TRUE(C37WorkerCallbackAccess::worker_peer_alive(*r));
  p1_owned::write_create_only((child_folder/"publish_request.json").string(),
    {{"schema","p1-C3.7-controlled-child-command-v1"},{"run_id",pins.run_id},
     {"action","publish"},{"manifest_sha256",pins.manifest_sha256},{"child_pid",child.pid()}});
  ASSERT_TRUE(wait_for([&]{return capability_messages.size()==1;}));
  ASSERT_EQ(capability_messages[0].pid,child.pid());
  ASSERT_TRUE(C37WorkerCallbackAccess::worker_authentication(*r,capability_metadata[0]).empty());
  // The received typed object and actual MessageInfo are deliberately held.
  // This is a native queued-receipt branch, not a claim of a network packet
  // first delivered after process death or of a real solver Worker replay.
  const auto held=capability_messages[0];const auto metadata=capability_metadata[0];
  const auto before=state();ASSERT_EQ(before.at("lease_last_valid_ns"),0);
  p1_owned::write_create_only((child_folder/"exit_request.json").string(),
    {{"schema","p1-C3.7-controlled-child-command-v1"},{"run_id",pins.run_id},
     {"action","exit"},{"manifest_sha256",pins.manifest_sha256},{"child_pid",child.pid()}});
  int status=0;ASSERT_TRUE(child.wait_normal(4,status));ASSERT_TRUE(WIFEXITED(status));ASSERT_EQ(WEXITSTATUS(status),0);
  ASSERT_FALSE(C37WorkerCallbackAccess::worker_peer_alive(*r));
  ASSERT_EQ(C37WorkerCallbackAccess::worker_authentication(*r,metadata),"worker_process_exited");
  C37WorkerCallbackAccess::receive(*r,held,metadata,Interface::Capability);
  trusted_equal(before,state());EXPECT_EQ(state().at("capability_received"),1);
  EXPECT_EQ(state().at("input_commit_ordinal"),before.at("input_commit_ordinal").get<uint64_t>()+1);
  const auto all=rows();const auto row=last(all,"adapter_worker_callback");ASSERT_TRUE(row.is_object());
  EXPECT_EQ(row.at("authentication_reason"),"worker_process_exited");
  EXPECT_FALSE(row.at("full_cdr_serialized").get<bool>());EXPECT_FALSE(row.at("semantic_callback_invoked").get<bool>());
  EXPECT_FALSE(row.at("worker_process_alive_at_guard").get<bool>());
  EXPECT_TRUE(last(all,"capability_admission").is_null());EXPECT_TRUE(last(all,"candidate_registration").is_null());
}

TEST_F(C37WorkerCallbacks,MalformedMetadataRejectionRecordsSafelyAndPreservesTrustedState){
  valid_capability();const auto m=prepared_candidate();dispatch_candidate=false;
  candidate_pub->publish(m);ASSERT_TRUE(wait_for([this]{return candidate_metadata.size()==1;}));
  const auto before=state();
  // Explicit metadata mutation component: the legal payload and original
  // MessageInfo come from actual DDS; mutations are not claimed network bytes.
  for(const auto interface:{Interface::Capability,Interface::Candidate})for(int mutation=0;mutation<3;++mutation){
    auto metadata=interface==Interface::Capability?capability_metadata[0]:candidate_metadata[0];
    auto &gid=metadata.get_rmw_message_info().publisher_gid;
    if(mutation==0)gid.implementation_identifier="intentional_test_foreign_rmw";
    if(mutation==1)gid.implementation_identifier=nullptr;
    if(mutation==2)std::fill(std::begin(gid.data),std::end(gid.data),uint8_t{0});
    if(interface==Interface::Capability){ASSERT_NO_THROW(C37WorkerCallbackAccess::receive(*r,cap,metadata,interface));}
    else{ASSERT_NO_THROW(C37WorkerCallbackAccess::receive(*r,m,metadata,interface));}
    trusted_equal(before,state());
  }
  EXPECT_EQ(state().at("capability_received"),4);EXPECT_EQ(state().at("candidate_received"),3);
  EXPECT_EQ(state().at("input_commit_ordinal"),before.at("input_commit_ordinal").get<uint64_t>()+6);
  const auto all=rows();size_t rejections=0;std::vector<std::string> reasons;
  for(const auto &row:all)if(row.value("type","")=="adapter_worker_callback"&&
      !row.at("authentication_reason").get<std::string>().empty()) {
    ++rejections;reasons.push_back(row.at("authentication_reason"));EXPECT_FALSE(row.at("full_cdr_serialized").get<bool>());
    EXPECT_FALSE(row.at("semantic_callback_invoked").get<bool>());
    EXPECT_EQ(row.at("before"),row.at("after"));
  }
  EXPECT_EQ(rejections,6);EXPECT_EQ(reasons,(std::vector<std::string>{"callback_rmw_implementation","callback_rmw_implementation",
    "callback_foreign_gid","callback_rmw_implementation","callback_rmw_implementation","callback_foreign_gid"}));
  EXPECT_EQ(last(all,"adapter_worker_callback").at("authentication_reason"),"callback_foreign_gid");
}
