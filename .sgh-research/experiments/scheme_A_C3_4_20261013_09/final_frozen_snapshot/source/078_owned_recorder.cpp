#include "p1_owned_identity.hpp"
#include <rosbag2_transport/recorder.hpp>
#include <rosbag2_cpp/writer.hpp>
#include <rclcpp/typesupport_helpers.hpp>
#include <chrono>
#include <csignal>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <regex>
#include <set>
#include <sstream>
#include <thread>

namespace fs=std::filesystem;
using Json=nlohmann::json;
using Clock=std::chrono::steady_clock;
volatile std::sig_atomic_t stop_signal=0;
void signal_stop(int signal) {stop_signal=signal;}

std::string file_sha(const fs::path &path) {
  return p1_owned::file_sha256(path.string());
}

std::string pinned_input(const fs::path &path,size_t limit,const std::string &pin) {
  const auto parent=p1_owned::open_directory(path.parent_path());
  const auto name=path.filename().string();
  p1_owned::require(!name.empty()&&name!="."&&name!="..","unsafe input basename");
  p1_owned::Fd fd(::openat(parent.get(),name.c_str(),O_RDONLY|O_NOFOLLOW|O_CLOEXEC));
  struct stat before{},after{};
  p1_owned::require(fd.get()>=0&&::fstat(fd.get(),&before)==0&&S_ISREG(before.st_mode)&&before.st_size>=0&&uint64_t(before.st_size)<=limit,"input must be bounded regular non-symlink file");
  std::string raw;char block[16384];
  while(true) {
    const auto n=::read(fd.get(),block,sizeof(block));
    if(n<0&&errno==EINTR)continue;
    p1_owned::require(n>=0,"input read failed");if(n==0)break;
    p1_owned::require(raw.size()+size_t(n)<=limit,"input exceeds bound during read");raw.append(block,size_t(n));
  }
  p1_owned::require(::fstat(fd.get(),&after)==0&&before.st_dev==after.st_dev&&before.st_ino==after.st_ino&&before.st_size==after.st_size&&before.st_mtim.tv_sec==after.st_mtim.tv_sec&&before.st_mtim.tv_nsec==after.st_mtim.tv_nsec&&before.st_ctim.tv_sec==after.st_ctim.tv_sec&&before.st_ctim.tv_nsec==after.st_ctim.tv_nsec,"input changed during read");
  p1_owned::require(p1_owned::sha256_bytes(raw)==pin,"input SHA mismatch");return raw;
}

struct Args {
  std::string run,contract,contract_sha,topics,topics_sha,topics_raw,manifest,terminal,bag,storage;
  int prepare_ms=15000;
};
Args parse(int argc,char **argv) {
  std::map<std::string,std::string> values;
  for(int i=1;i<argc;i+=2) {
    if(i+1>=argc||!values.emplace(argv[i],argv[i+1]).second) throw std::runtime_error("missing value or duplicate flag");
  }
  const std::set<std::string> allowed={"--run-id","--contract","--contract-sha256","--topics","--topics-sha256","--manifest","--terminal","--bag","--storage-id","--prepare-budget-ms"};
  for(const auto &kv:values) if(!allowed.count(kv.first)) throw std::runtime_error("unknown flag / ROS remapping forbidden");
  Args args;
  auto take=[&](const std::string &flag){if(!values.count(flag)||values.at(flag).empty())throw std::runtime_error("required flag absent");return values.at(flag);};
  args.run=take("--run-id");args.contract=take("--contract");args.contract_sha=take("--contract-sha256");
  args.topics=take("--topics");args.topics_sha=take("--topics-sha256");args.manifest=take("--manifest");args.terminal=take("--terminal");args.bag=take("--bag");args.storage=take("--storage-id");
  if(values.count("--prepare-budget-ms")) {size_t consumed=0;args.prepare_ms=std::stoi(values.at("--prepare-budget-ms"),&consumed);if(consumed!=values.at("--prepare-budget-ms").size())throw std::runtime_error("invalid prepare budget");}
  if(args.prepare_ms<100||args.prepare_ms>15000)throw std::runtime_error("prepare budget outside [100,15000] ms");
  if(!std::regex_match(args.run,std::regex("[A-Za-z0-9_.-]{1,128}")))throw std::runtime_error("invalid run identity");
  if(!std::regex_match(args.contract_sha,std::regex("[0-9a-f]{64}"))||!std::regex_match(args.topics_sha,std::regex("[0-9a-f]{64}")))throw std::runtime_error("invalid SHA identity");
  for(const auto &path:{args.contract,args.topics,args.manifest,args.terminal,args.bag})if(!fs::path(path).is_absolute())throw std::runtime_error("paths must be absolute");
  if(args.manifest==args.terminal||args.manifest==args.bag||args.terminal==args.bag)throw std::runtime_error("output paths must be distinct");
  auto parent_identity=p1_owned::open_directory(fs::path(args.bag).parent_path());(void)parent_identity;
  if(fs::path(args.bag).filename()=="."||fs::path(args.bag).filename()=="..")throw std::runtime_error("unsafe bag basename");
  for(const auto &path:{args.manifest,args.terminal,args.bag}) {
    const auto parent=p1_owned::open_directory(fs::path(path).parent_path());(void)parent;
    const auto name=fs::path(path).filename().string();
    p1_owned::require(!name.empty()&&name!="."&&name!="..","unsafe output basename");
    if(fs::symlink_status(path).type()!=fs::file_type::not_found)throw std::runtime_error("create-only output already exists, including dangling symlink");
  }
  if(args.storage!="sqlite3"&&args.storage!="mcap")throw std::runtime_error("storage id must be explicitly sqlite3 or mcap");
  (void)pinned_input(args.contract,262144,args.contract_sha);
  args.topics_raw=pinned_input(args.topics,65536,args.topics_sha);
  return args;
}

std::map<std::string,std::string> read_topics(const Args &args) {
  // Hash and parse the exact same bounded bytes from one no-follow regular FD.
  const auto document=Json::parse(args.topics_raw);
  if(!document.is_object()||document.size()!=2||document.at("schema")!="p1-owned-recorder-topics/v1"||!document.at("topics").is_object())throw std::runtime_error("invalid topic declaration schema");
  auto topics=document.at("topics").get<std::map<std::string,std::string>>();
  if(topics.empty()||topics.size()>64)throw std::runtime_error("topic count outside [1,64]");
  for(const auto &kv:topics) {
    if(!std::regex_match(kv.first,std::regex("/[A-Za-z0-9_/]{1,255}"))||!std::regex_match(kv.second,std::regex("[A-Za-z][A-Za-z0-9_]*?/msg/[A-Za-z][A-Za-z0-9_]*")))throw std::runtime_error("invalid topic/type declaration");
  }
  return topics;
}

bool actual_type_matches(const rclcpp::SubscriptionBase &sub,const std::string &type) {
  auto library=rclcpp::get_typesupport_library(type,"rosidl_typesupport_cpp");
  const auto *expected=rclcpp::get_message_typesupport_handle(type,"rosidl_typesupport_cpp",*library);
  const auto &actual=sub.get_message_type_support_handle();
  return expected&&actual.data==expected->data&&actual.func==expected->func&&std::string(actual.typesupport_identifier)==expected->typesupport_identifier;
}

Json own_endpoints(rosbag2_transport::Recorder &recorder,const std::map<std::string,std::string> &topics) {
  if(recorder.is_discovery_running())throw std::runtime_error("subscription snapshot requires stopped discovery");
  const auto &subscriptions=recorder.subscriptions();
  if(subscriptions.size()!=topics.size())throw std::runtime_error("actual subscription set differs from declaration");
  Json endpoints=Json::array();
  for(const auto &kv:topics) {
    auto found=subscriptions.find(kv.first);
    if(found==subscriptions.end()||!found->second||!actual_type_matches(*found->second,kv.second))throw std::runtime_error("actual subscription/type differs from declaration");
    endpoints.push_back(p1_owned::subscription_endpoint(*found->second,kv.second));
  }
  return endpoints;
}

int main(int argc,char **argv) {
  std::shared_ptr<rosbag2_transport::Recorder> recorder;
  std::shared_ptr<rosbag2_cpp::Writer> writer;
  std::unique_ptr<rclcpp::executors::SingleThreadedExecutor> executor;
  std::shared_ptr<rclcpp::node_interfaces::OnSetParametersCallbackHandle> frozen_parameters;
  Args args;Json published_manifest;bool initialized=false,record_started=false,prepared=false,stop_completed=false;
  std::string error;int result=0;
  const auto started=Clock::now();
  try {
    args=parse(argc,argv);const auto topics=read_topics(args);
    std::signal(SIGINT,signal_stop);std::signal(SIGTERM,signal_stop);
    // Preserve the ROS context during Recorder::stop(), so stop can flush storage.
    rclcpp::init(argc,argv,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);initialized=true;
    executor=std::make_unique<rclcpp::executors::SingleThreadedExecutor>();
    rosbag2_storage::StorageOptions storage;storage.uri=args.bag;storage.storage_id=args.storage;storage.max_cache_size=1048576;
    rosbag2_transport::RecordOptions options;options.disable_keyboard_controls=true;options.rmw_serialization_format="cdr";options.topic_polling_interval=std::chrono::milliseconds(25);
    Json qos_declaration=Json::object();
    for(const auto &kv:topics) {
      options.topics.push_back(kv.first);
      rclcpp::QoS qos(100);
      const bool sensor=kv.second=="nav_msgs/msg/Odometry"||kv.second=="sensor_msgs/msg/Imu"||kv.second=="rosgraph_msgs/msg/Clock";
      if(sensor)qos.best_effort();else qos.reliable();
      const bool capability=kv.first=="/p1/worker_capability";
      if(capability)qos.transient_local();else qos.durability_volatile();
      options.topic_qos_profile_overrides.emplace(kv.first,qos);
      qos_declaration[kv.first]={{"depth",100},{"reliability",sensor?"best_effort":"reliable"},{"durability",capability?"transient_local":"volatile"}};
    }
    writer=std::make_shared<rosbag2_cpp::Writer>();
    rclcpp::NodeOptions node_options;node_options.enable_rosout(false).start_parameter_services(false).start_parameter_event_publisher(false);
    recorder=std::make_shared<rosbag2_transport::Recorder>(writer,storage,options,"p1_owned_recorder",node_options);
    frozen_parameters=p1_owned::freeze_parameters(*recorder);
    executor->add_node(recorder);record_started=true;recorder->record();
    const auto deadline=started+std::chrono::milliseconds(args.prepare_ms);
    Json endpoints;
    // subscriptions() returns a reference. Stop/join discovery before accessing it;
    // retry discovery only when no snapshot is being inspected.
    while(!stop_signal&&Clock::now()<deadline) {
      executor->spin_some(std::chrono::milliseconds(5));recorder->stop_discovery();
      if(recorder->subscriptions().size()==topics.size()) {endpoints=own_endpoints(*recorder,topics);prepared=true;break;}
      recorder->start_discovery();std::this_thread::sleep_for(std::chrono::milliseconds(25));
    }
    recorder->stop_discovery();
    if(!prepared)throw std::runtime_error(stop_signal?"stopped before prepared":"subscription prepare deadline");
    Json extra={{"topic_declaration_path",args.topics},{"topic_declaration_sha256",args.topics_sha},{"storage_options",{{"uri",args.bag},{"storage_id",args.storage},{"max_cache_size",1048576},{"snapshot_mode",false}}},{"record_options",{{"topics",topics},{"all_topics",false},{"use_sim_time",false},{"start_paused",false},{"compression_mode",""},{"qos_overrides",qos_declaration}}},{"discovery_stopped",true},{"true_recorder_storage",true},{"prepare_elapsed_ms",std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now()-started).count()}};
    published_manifest=p1_owned::role_manifest(*recorder,"recorder",args.run,args.contract_sha,P1_OWNED_SOURCE_BUNDLE_SHA256,endpoints,extra);
    p1_owned::write_create_only(args.manifest,published_manifest);
    while(!stop_signal&&rclcpp::ok()) {
      executor->spin_some(std::chrono::milliseconds(5));
      if(recorder->is_paused()||recorder->is_discovery_running()||own_endpoints(*recorder,topics)!=endpoints)throw std::runtime_error("recorder configuration/endpoint changed after prepare");
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    if(!stop_signal)throw std::runtime_error("ROS context exited without an owned stop signal");
  } catch(const std::exception &exception) {error=exception.what();result=2;}
  try {if(recorder&&record_started){recorder->stop_discovery();recorder->stop();stop_completed=true;}}
  catch(const std::exception &exception){error+=(error.empty()?"":"; ")+std::string("Recorder stop: ")+exception.what();result=3;}
  const auto stop_time=Clock::now();
  try {
    if(!args.terminal.empty()) {
      Json terminal={{"schema","p1-owned-recorder-terminal/v1"},{"run_id",args.run},{"contract_sha256",args.contract_sha},{"source_bundle_sha256",P1_OWNED_SOURCE_BUNDLE_SHA256},{"prepared",prepared},{"manifest_written",!published_manifest.empty()&&fs::exists(args.manifest)},{"manifest_sha256",fs::exists(args.manifest)?file_sha(args.manifest):""},{"Recorder_stop_completed",stop_completed},{"storage_uri",args.bag},{"storage_id",args.storage},{"stop_signal",static_cast<int>(stop_signal)},{"elapsed_ms",std::chrono::duration_cast<std::chrono::milliseconds>(stop_time-started).count()},{"error",error},{"clean",result==0&&stop_completed},{"storage_stream_accounting_verified",false}};
      const auto metadata=fs::path(args.bag)/"metadata.yaml";
      terminal["boot_id"]=p1_owned::boot_id();terminal["pid"]=::getpid();terminal["process_start_ticks"]=p1_owned::process_start_ticks();
      terminal["metadata_exists"]=fs::exists(metadata);terminal["metadata_sha256"]=fs::exists(metadata)?file_sha(metadata):"";
      if(!fs::exists(metadata)){terminal["clean"]=false;result=result?result:3;}
      // This receipt states the public stop() result. Reader/source/Witness accounting
      // remains external and false here, including all prepare and terminal messages.
      p1_owned::write_create_only(args.terminal,terminal);
    }
  } catch(const std::exception &exception){std::cerr<<"terminal receipt failure: "<<exception.what()<<'\n';result=4;}
  if(recorder&&executor)executor->remove_node(recorder);
  recorder.reset();writer.reset();executor.reset();if(initialized)rclcpp::shutdown();
  if(!error.empty())std::cerr<<error<<'\n';
  return result;
}
