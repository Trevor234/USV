// SPDX-License-Identifier: MIT
// Controlled native exec-child Worker-role endpoint fixture. No solver/actuator.
#include "owned_worker_peer_c37_v1.hpp"
#include "protocol.hpp"
#include <rclcpp/serialization.hpp>
#include <thread>
#ifndef P1_OWNED_SOURCE_BUNDLE_SHA256
#error "controlled Worker child requires registered source bundle identity"
#endif

namespace {
void append(int fd,const p1_owned::Json &value) {
  const auto raw=value.dump()+"\n";p1_owned::require(raw.size()<=65536,"child source row bound");
  size_t done=0;while(done<raw.size()){
    const auto count=::write(fd,raw.data()+done,raw.size()-done);
    if(count<0&&errno==EINTR)continue;p1_owned::require(count>0,"child source write");done+=size_t(count);
  }
}
void validate_command(const std::filesystem::path &path,const std::string &action,
  const std::string &manifest_sha) {
  const auto j=c36_owned::detail::strict_json(c36_owned::detail::read_manifest(path.string()));
  p1_owned::require(j.is_object()&&j.size()==5&&j.at("schema")=="p1-C3.7-controlled-child-command-v1"&&
    j.at("run_id")=="shadow-source-linked-test"&&j.at("action")==action&&
    j.at("manifest_sha256")==manifest_sha&&
    c36_owned::detail::uint_field(j,"child_pid",INT_MAX)==uint64_t(::getpid()),"child command identity");
}
} // namespace

int main(int argc,char **argv) {
  try {
    p1_owned::require(argc==3&&std::string(argv[1])=="--fixture-dir","child CLI --fixture-dir required");
    const std::filesystem::path folder(argv[2]);
    p1_owned::require(folder.is_absolute()&&folder.string().size()<=4096&&
      !folder.filename().empty()&&folder.filename()!="."&&folder.filename()!="..","child fixture directory domain");
    const auto parent=p1_owned::open_directory(folder.parent_path());
    p1_owned::require(::mkdirat(parent.get(),folder.filename().c_str(),0700)==0,"child directory create-only");
    const auto directory=p1_owned::open_directory(folder);
    const auto source_path=(folder/"source.jsonl").string();
    c36_owned::detail::Fd source(::openat(directory.get(),"source.jsonl",O_WRONLY|O_CREAT|O_EXCL|O_APPEND|O_NOFOLLOW|O_CLOEXEC,0600));
    p1_owned::require(source.get()>=0,"child source create-only");
    int ros_argc=1;char *ros_argv[]={argv[0],nullptr};
    rclcpp::init(ros_argc,ros_argv,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);
    const auto options=rclcpp::NodeOptions().enable_rosout(false).start_parameter_services(false)
      .start_parameter_event_publisher(false).use_intra_process_comms(false);
    auto node=std::make_shared<rclcpp::Node>("c37_controlled_worker_child",options);
    const auto manifest_path=(folder/"owned_manifest.json").string();
    const auto run=std::string("shadow-source-linked-test");
    const auto contract=std::string("0e3eb70e74e922059ff17014ab1971b8a9fe20be0171964fc26410b7d769a933");
    const auto nominal=p1::candidate_baseline().at("nominal_hash").get<std::string>();
    const auto instance=std::string(64,'e');
    node->declare_parameter<std::string>("run_id",run);
    node->declare_parameter<std::string>("contract_hash",contract);
    node->declare_parameter<std::string>("owned_manifest_file",manifest_path);
    node->declare_parameter<std::string>("source_file",source_path);
    auto capability=node->create_publisher<p1::Capability>("/p1/worker_capability",rclcpp::QoS(10).reliable());
    auto candidate=node->create_publisher<p1::Candidate>("/p1/solve_candidate",rclcpp::QoS(10).reliable());
    const auto frozen=p1_owned::freeze_parameters(*node);
    const auto manifest=p1_owned::role_manifest(*node,"worker",run,contract,P1_OWNED_SOURCE_BUNDLE_SHA256,
      p1_owned::Json::array({p1_owned::publisher_endpoint(*capability,"usv_research_interfaces/msg/WorkerCapability"),
        p1_owned::publisher_endpoint(*candidate,"usv_research_interfaces/msg/SolveCandidate")}),
      {{"worker_instance",instance},{"nominal_hash",nominal},
       {"contract_configuration",{{"nominal_hash",nominal},{"execute_qualified",false}}},
       {"source_fd",p1_owned::source_fd_identity(source_path)},
       {"fixture_scope","controlled_native_exec_child_no_solver"}});
    p1_owned::write_create_only(manifest_path,manifest);
    const auto manifest_sha=p1_owned::sha256_bytes(manifest.dump()+"\n");
    append(source.get(),{{"type","controlled_child_header"},{"schema","p1-C3.7-child-source-v1"},
      {"owned_manifest_sha256",manifest_sha},{"pid",::getpid()},{"process_start_ticks",p1_owned::process_start_ticks()},
      {"boot_id",p1_owned::boot_id()},{"source_bundle_sha256",P1_OWNED_SOURCE_BUNDLE_SHA256},
      {"binary_sha256",manifest.at("binary_sha256")},{"run_id",run},{"worker_instance",instance},
      {"endpoints",manifest.at("endpoints")},{"solver_invoked",false},{"actual_actuator_publish",false}});
    rclcpp::executors::SingleThreadedExecutor executor;executor.add_node(node);
    const auto deadline=p1_owned::steady_ns()+10000000000LL;bool published=false,normal_exit=false;
    while(rclcpp::ok()&&p1_owned::steady_ns()<deadline) {
      executor.spin_some();
      if(!published&&std::filesystem::exists(folder/"publish_request.json")&&capability->get_subscription_count()>0) {
        validate_command(folder/"publish_request.json","publish",manifest_sha);
        p1::Capability m;m.schema_version="p1-worker-capability-v1";m.run_id=run;m.boot_id=p1_owned::boot_id();
        m.contract_hash=contract;m.nominal_hash=nominal;m.worker_instance=instance;
        m.clock_name="CLOCK_MONOTONIC";m.backend="acados";m.matrix_layout="column_major";
        m.horizon_steps=20;m.prediction_dt=.2;m.pid=::getpid();m.startup_ns=manifest.at("created_steady_ns");
        m.fault_injection_enabled=true;
        rclcpp::Serialization<p1::Capability> serializer;rclcpp::SerializedMessage serialized;
        serializer.serialize_message(&m,&serialized);const auto &cdr=serialized.get_rcl_serialized_message();
        const auto bytes=std::string(reinterpret_cast<const char*>(cdr.buffer),cdr.buffer_length);
        append(source.get(),{{"type","controlled_child_capability_publish_attempt"},{"publish_seq",1},
          {"publish_start_ns",p1_owned::steady_ns()},{"cdr_bytes",cdr.buffer_length},
          {"cdr_hex",p1_owned::hex(cdr.buffer,cdr.buffer_length)},{"cdr_sha256",p1_owned::sha256_bytes(bytes)}});
        capability->publish(m);published=true;
        append(source.get(),{{"type","controlled_child_capability_publish_result"},{"publish_seq",1},
          {"publish_end_ns",p1_owned::steady_ns()},{"returned",true},{"solver_invoked",false}});
      }
      if(std::filesystem::exists(folder/"exit_request.json")) {
        validate_command(folder/"exit_request.json","exit",manifest_sha);
        append(source.get(),{{"type","controlled_child_normal_exit_requested"},{"observed_ns",p1_owned::steady_ns()},
          {"capability_published",published},{"actual_actuator_publish",false}});normal_exit=true;break;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    p1_owned::require(normal_exit&&published,"child bounded timeout or publication absent");
    executor.remove_node(node);capability.reset();candidate.reset();node.reset();rclcpp::shutdown();
    append(source.get(),{{"type","controlled_child_closed"},{"closed_ns",p1_owned::steady_ns()},
      {"normal_exit",true},{"solver_invoked",false},{"actual_actuator_publish",false}});
    p1_owned::require(::fsync(source.get())==0,"child source fsync");return 0;
  }catch(const std::exception &e){fprintf(stderr,"C37 controlled Worker child fatal: %s\n",e.what());
    if(rclcpp::ok())rclcpp::shutdown();return 2;}
}
