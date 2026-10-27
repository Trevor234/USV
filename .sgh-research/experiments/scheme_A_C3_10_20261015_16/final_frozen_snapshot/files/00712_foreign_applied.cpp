// SPDX-License-Identifier: MIT
// An independent controlled DDS writer. Publishes no actuator topics.
#include "foreign_protocol.hpp"
#include <atomic>
#include <csignal>
#include <thread>
#ifndef P1_OWNED_SOURCE_BUNDLE_SHA256
#error "Exact source bundle required"
#endif
static std::atomic<bool> stopped{false};
static void stop_signal(int){stopped=true;}
class Foreign final:public rclcpp::Node {
 public:
  Foreign():Node("p1_c310_foreign_applied"){
    run_=declare_parameter<std::string>("run_id","");const auto contract_file=declare_parameter<std::string>("contract_file","");
    contract_sha_=declare_parameter<std::string>("contract_sha256","");output_=declare_parameter<std::string>("output_dir","");
    const auto command_file=declare_parameter<std::string>("command_file","");command_sha_=declare_parameter<std::string>("command_sha256","");emit_file_=declare_parameter<std::string>("emit_file","");
    p1_owned::require(p1_owned::sha256_shape(contract_sha_)&&p1_owned::file_sha256(contract_file)==contract_sha_,"independent contract SHA differs");
    c310::contract(c310::strict_json(p1_owned::read_bounded(contract_file)));
    p1_owned::require(p1_owned::sha256_shape(command_sha_)&&p1_owned::file_sha256(command_file)==command_sha_,"foreign command SHA differs");
    command_=c310::strict_json(p1_owned::read_bounded(command_file));original_=c310::command(command_,run_,p1_owned::boot_id());
    p1_owned::require(!std::filesystem::exists(emit_file_),"emit gate must be initially absent");
    const auto emit_dir=p1_owned::open_directory(std::filesystem::path(emit_file_).parent_path());(void)emit_dir;
    pub_=create_generic_publisher("/research/control/applied","usv_research_interfaces/msg/AppliedControl",rclcpp::QoS(10).reliable());
    source_.open(output_+"/source.jsonl",std::ios::out|std::ios::app);p1_owned::require(bool(source_),"foreign Source unavailable");
    endpoint_=p1_owned::publisher_endpoint(*pub_,"usv_research_interfaces/msg/AppliedControl");frozen_=p1_owned::freeze_parameters(*this);
    const auto manifest=p1_owned::role_manifest(*this,"foreign",run_,contract_sha_,P1_OWNED_SOURCE_BUNDLE_SHA256,c310::Json::array({endpoint_}),{{"diagnostic_only",true},{"physical_publisher_endpoints",0},{"command_file",command_file},{"command_sha256",command_sha_},{"independent_contract_file",contract_file},{"source_fd",p1_owned::source_fd_identity(output_+"/source.jsonl")},{"source_packet_identity","producer packet_index; copied Applied sequence intentionally collides"}});
    p1_owned::write_create_only(output_+"/owned_manifest.json",manifest);manifest_sha_=p1_owned::file_sha256(output_+"/owned_manifest.json");
    log({{"type","foreign_ready"},{"prepared_ns",p1_owned::steady_ns()},{"manifest_sha256",manifest_sha_},{"command_sha256",command_sha_},{"publisher_gid",endpoint_.at("gid")},{"execute_qualified",false},{"stage_qualified",false}});
    created_=p1_owned::steady_ns();
  }
  void poll(){
    if(emitted_)return;
    const auto now=p1_owned::steady_ns();p1_owned::require(now-created_<=5000000000LL,"foreign finite emit deadline");
    if(!std::filesystem::exists(emit_file_))return;
    const auto raw=p1_owned::read_bounded(emit_file_);const auto gate=c310::strict_json(raw);c310::emit(gate,command_,command_sha_,manifest_sha_,uint64_t(now));
    if(pub_->get_subscription_count()<3)return;
    log({{"type","foreign_emit_observed"},{"observed_ns",p1_owned::steady_ns()},{"issued_ns",gate.at("issued_ns")},{"emit_sha256",p1_owned::sha256_bytes(raw)},{"matched_subscriptions",pub_->get_subscription_count()},{"command_sha256",command_sha_},{"manifest_sha256",manifest_sha_}});
    auto mutated=c310::decode(original_);mutated.final_n={1.0,-1.0};
    const std::array<std::string,3> packets={original_,c310::encode(mutated),original_};
    const std::array<const char*,3> labels={"clone_zero_first","clone_nonzero","clone_zero_repeat"};
    for(size_t i=0;i<packets.size();++i){
      const auto m=c310::decode(packets[i]);const auto start=p1_owned::steady_ns();
      c310::Json event={{"type","foreign_publish_start"},{"packet_index",i+1},{"label",labels[i]},{"topic","/research/control/applied"},{"ros_type","usv_research_interfaces/msg/AppliedControl"},{"sequence",m.sequence},{"publisher_gid",endpoint_.at("gid")},{"serialization","cdr"},{"cdr_hex",p1_owned::hex(reinterpret_cast<const unsigned char*>(packets[i].data()),packets[i].size())},{"cdr_bytes",packets[i].size()},{"payload_sha256",p1_owned::sha256_bytes(packets[i])},{"publish_start_ns",start},{"final_n",m.final_n},{"physical_publish_attempted",false},{"stage_qualified",false},{"execute_qualified",false}};
      log(event);++generated_;bool returned=false;std::string error;
      try{auto raw=c310::serialized(packets[i]);pub_->publish(raw);returned=true;++returned_;}
      catch(const std::exception&e){error=e.what();}
      event["type"]="foreign_publish_result";event["publish_end_ns"]=p1_owned::steady_ns();event["returned"]=returned;event["error"]=error;log(event);
      p1_owned::require(returned,"foreign native publish threw");
      // Finite spacing gives the existing reliable subscribers time to take.
      const auto next=p1_owned::steady_ns()+25000000LL;while(!stopped&&rclcpp::ok()&&p1_owned::steady_ns()<next){rclcpp::spin_some(shared_from_this());std::this_thread::sleep_for(std::chrono::milliseconds(1));}
    }
    emitted_=true;
  }
  void close(){log({{"type","foreign_summary"},{"finished_ns",p1_owned::steady_ns()},{"generated",generated_},{"returned",returned_},{"expected_packets",3},{"normal_source_complete",emitted_&&generated_==3&&returned_==3},{"physical_publish_attempted",false},{"execute_qualified",false},{"stage_qualified",false}});source_.flush();p1_owned::require(bool(source_),"foreign final Source flush");p1_owned::write_create_only(output_+"/terminal.json",{{"schema","p1-C3.10-foreign-Applied-terminal-v1"},{"run_id",run_},{"boot_id",p1_owned::boot_id()},{"closed_ns",p1_owned::steady_ns()},{"manifest_sha256",manifest_sha_},{"command_sha256",command_sha_},{"source_sha256",p1_owned::file_sha256(output_+"/source.jsonl")},{"generated",generated_},{"returned",returned_},{"normal_end",emitted_&&generated_==3&&returned_==3},{"physical_publisher_endpoints",0},{"execute_qualified",false},{"stage_qualified",false}});}
 private:
  void log(c310::Json event){event["source_ordinal"]=++ordinal_;source_<<event.dump()<<'\n';source_.flush();p1_owned::require(bool(source_),"foreign Source append failed");}
  std::string run_,output_,contract_sha_,command_sha_,emit_file_,manifest_sha_,original_;c310::Json command_,endpoint_;std::ofstream source_;int64_t created_=0;uint64_t generated_=0,returned_=0,ordinal_=0;bool emitted_=false;
  rclcpp::GenericPublisher::SharedPtr pub_;rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr frozen_;
};
int main(int argc,char **argv){try{rclcpp::init(argc,argv,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);std::signal(SIGINT,stop_signal);std::signal(SIGTERM,stop_signal);auto n=std::make_shared<Foreign>();while(rclcpp::ok()&&!stopped){rclcpp::spin_some(n);n->poll();std::this_thread::sleep_for(std::chrono::milliseconds(2));}n->close();n.reset();rclcpp::shutdown();return 0;}catch(const std::exception&e){std::fprintf(stderr,"foreign Applied failed: %s\n",e.what());if(rclcpp::ok())rclcpp::shutdown();return 2;}}
