// SPDX-License-Identifier: MIT
// Explicit synthetic sensors/reference only; no plant/Gazebo/FCU connection.
#include "p1_owned_identity.hpp"
#include "m4_owned_runtime.hpp"
#include "exact_peer.hpp"
#include "controlled_protocol.hpp"
#include "nominal_history.hpp"
#include "controlled_reference.hpp"
#include <nav_msgs/msg/odometry.hpp>
#include <nav_msgs/msg/path.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <std_msgs/msg/float64_multi_array.hpp>
#include <rosgraph_msgs/msg/clock.hpp>
#include <csignal>
#include <atomic>
#include <thread>
#ifndef P1_OWNED_SOURCE_BUNDLE_SHA256
#error "source bundle must be pinned"
#endif
static std::atomic<bool> stop_requested{false};
static void stop_signal(int){stop_requested=true;}
class Synthetic final: public rclcpp::Node {
 public:
 Synthetic():Node("p1_synthetic_source",formal_owned::node_options()) {
  formal_owned::entry_arguments(*this);
  run_=declare_parameter<std::string>("run_id","");
  contract_=declare_parameter<std::string>("contract_hash","");
  output_=declare_parameter<std::string>("output_dir","");
  start_file_=declare_parameter<std::string>("start_file","");
  topics_file_=declare_parameter<std::string>("topics_file","");
  topics_sha_=declare_parameter<std::string>("topics_sha256","");
  mode_=declare_parameter<std::string>("controlled_phase_mode","C");
  reference_speed_=declare_parameter<double>("reference_speed_m_s",mode_=="C"?.05:0.);
  p1_owned::require(mode_=="C"&&reference_speed_==.05,"M4 fixed calibrated nominal/reference domain");
  contract_file_=declare_parameter<std::string>("contract_file","");owner_run_=run_;
  const auto scope=declare_parameter<std::string>("m4_release_scope","");
  contract_configuration_=m4_owned::contract(contract_file_,contract_,"execute",scope);
  const auto driver_file=declare_parameter<std::string>("driver_pins_file","");
  const auto driver_hash=declare_parameter<std::string>("driver_pins_sha256","");
  driver_pin_=formal_owned::read_pinned(driver_file,driver_hash);driver_=formal_owned::driver_peer(driver_pin_,run_,contract_);
  formal_owned::overrides(*this,{"run_id","contract_hash","output_dir","start_file","topics_file","topics_sha256","controlled_phase_mode","reference_speed_m_s","contract_file","m4_release_scope","driver_pins_file","driver_pins_sha256","use_sim_time"});
  hydro_=contract_configuration_.at("hydro");model_=std::make_unique<controlled::NominalHistory>(hydro_,contract_);
  nominal_.open(output_+"/nominal_steps.jsonl",std::ios::out|std::ios::app);p1_owned::require(bool(nominal_),"M4 nominal Source unavailable");
  applied_=create_subscription<usv_research_interfaces::msg::AppliedControl>("/research/control/applied",rclcpp::QoS(100).reliable(),[this](usv_research_interfaces::msg::AppliedControl::ConstSharedPtr m,const rclcpp::MessageInfo &info){applied(*m,info);});

  p1_owned::require(p1_owned::file_sha256(topics_file_)==topics_sha_,"synthetic topic declaration differs");
  odom_=create_publisher<nav_msgs::msg::Odometry>("/wamv/sensors/position/ground_truth_odometry",rclcpp::SensorDataQoS());
  imu_=create_publisher<sensor_msgs::msg::Imu>("/wamv/sensors/imu/imu/data",rclcpp::SensorDataQoS());
  path_=create_publisher<nav_msgs::msg::Path>("/path/reference",rclcpp::QoS(1).reliable());
  profile_=create_publisher<std_msgs::msg::Float64MultiArray>("/path/reference_profile",rclcpp::QoS(1).reliable());
  clock_=create_publisher<rosgraph_msgs::msg::Clock>("/clock",rclcpp::ClockQoS());
  p1_owned::Json eps=p1_owned::Json::array({p1_owned::publisher_endpoint(*odom_,"nav_msgs/msg/Odometry"),p1_owned::publisher_endpoint(*imu_,"sensor_msgs/msg/Imu"),p1_owned::publisher_endpoint(*path_,"nav_msgs/msg/Path"),p1_owned::publisher_endpoint(*profile_,"std_msgs/msg/Float64MultiArray"),p1_owned::publisher_endpoint(*clock_,"rosgraph_msgs/msg/Clock")});
  eps.push_back(p1_owned::subscription_endpoint(*applied_,"usv_research_interfaces/msg/AppliedControl"));
  log_.open(output_+"/transport_source.jsonl",std::ios::out|std::ios::app);
  p1_owned::require(bool(log_),"transport source unavailable");
  auto topics=p1_owned::Json::parse(p1_owned::read_bounded(topics_file_)).at("topics");
  for(auto it=topics.begin();it!=topics.end();++it){auto topic=it.key(),type=it.value().get<std::string>();rclcpp::QoS qos(100);if(type=="nav_msgs/msg/Odometry"||type=="sensor_msgs/msg/Imu"||type=="rosgraph_msgs/msg/Clock")qos.best_effort();else qos.reliable();if(topic=="/p1/worker_capability")qos.transient_local();
   auto sub=create_generic_subscription(topic,type,qos,[this,topic,type](std::shared_ptr<rclcpp::SerializedMessage> message,const rclcpp::MessageInfo &info){
    auto &raw=message->get_rcl_serialized_message();const auto ns=p1_owned::steady_ns();
    p1_owned::Json row={{"type","transport_message"},{"topic",topic},{"ros_type",type},{"serialization","cdr"},{"publisher_gid",p1_owned::gid_json(info.get_rmw_message_info().publisher_gid)},{"payload_sha256",p1_owned::sha256_bytes(std::string(reinterpret_cast<char*>(raw.buffer),raw.buffer_length))},{"serialized_bytes",raw.buffer_length},{"receive_ns",ns},{"ordinal",++ordinal_}};
    log_<<row.dump()<<'\n';log_.flush();if(!log_)failed_=true;transport_counts_[topic]=transport_counts_[topic].get<uint64_t>()+1;
   });eps.push_back(p1_owned::subscription_endpoint(*sub,type));subs_.push_back(sub);transport_counts_[topic]=0;
  }
  frozen_=p1_owned::freeze_parameters(*this);
  auto manifest=p1_owned::role_manifest(*this,"synthetic_source",run_,contract_,P1_OWNED_SOURCE_BUNDLE_SHA256,eps,{{"synthetic",true},{"plant_connected",false},{"rate_hz",50},{"source_state","actual_owned_Applied_nominal_RK4"},{"physical_publishers",0},{"contract_configuration",contract_configuration_},{"m4_release_scope",m4_owned::scope},{"Applied_subscribers",1},{"Applied_publishers",0},{"reference_speed_m_s",reference_speed_},{"reference_kind",mode_=="C"?"fixed_long_straight_line":"stationary_zero_equilibrium"},{"reference_points",201},{"reference_dt_s",.2},{"reference_duration_s",40.},{"controlled_phase_mode",mode_},{"diagnostic_nominal_model_connected",mode_=="C"},{"nominal_model_source_fd",p1_owned::source_fd_identity(output_+"/nominal_steps.jsonl")},{"model_contract_sha256",contract_},{"contract_hydro",hydro_},{"transport_observer",true},{"source_fd",p1_owned::source_fd_identity(output_+"/transport_source.jsonl")}});
  p1_owned::write_create_only(output_+"/owned_manifest.json",manifest);
  timer_=create_wall_timer(std::chrono::milliseconds(20),[this]{publish();});
 }
 void close(){p1_owned::Json counts={{"/clock",count_},{"/wamv/sensors/position/ground_truth_odometry",count_},{"/wamv/sensors/imu/imu/data",count_},{"/path/reference",reference_count_},{"/path/reference_profile",reference_count_}};
  source({{"type","nominal_source_closed"},{"closed_ns",p1_owned::steady_ns()},{"Applied_received",applied_received_},{"Applied_accepted",applied_accepted_},{"model_steps",count_},{"sensor_messages_per_channel",count_},{"last_Applied_sequence",last_applied_sequence_},{"executor_publishing_stopped",true}});
  log_.flush();nominal_.flush();failed_=failed_||!log_||!nominal_;p1_owned::write_create_only(output_+"/terminal.json",{{"run_id",run_},{"synthetic",true},{"closed_steady_ns",p1_owned::steady_ns()},{"published_counts",counts},{"transport_counts",transport_counts_},{"normal_end",!failed_},{"failed",failed_},{"transport_total",ordinal_}});}
 void stop_publishing(){timer_->cancel();}
 private:
 void source(p1_owned::Json row){row["source_written_ns"]=p1_owned::steady_ns();row["stage_qualified"]=false;row["execute_qualified"]=false;nominal_<<row.dump()<<'\n';nominal_.flush();p1_owned::require(bool(nominal_),"nominal Source write failed");}
 void applied(const usv_research_interfaces::msg::AppliedControl &m,const rclcpp::MessageInfo &info){
  const auto entry=p1_owned::steady_ns();const auto received=++applied_received_;auto raw=controlled::receipt(m,info,received,entry,"/research/control/applied","usv_research_interfaces/msg/AppliedControl");
  p1_owned::require(bool(owner_peer_),"M4 Applied before owner authentication");auto reason=owner_peer_->reason(info);const auto &owner=owner_peer_->manifest();
  if(reason.empty()&&(m.schema_version!="p0-contract-v1"||m.run_id!=owner_run_||m.producer_instance_id!=owner.at("producer_instance_id")||m.config_hash!=owner.at("config_hash")||m.baseline_id!=contract_configuration_.at("baseline_input")||m.steady_clock_domain!=p1_owned::boot_id()+":steady_clock"))reason="payload_owner_identity";
  if(reason.empty()&&(m.sequence==0||m.sequence<=last_applied_sequence_))reason="duplicate_or_reordered_Applied";
  if(reason.empty()&&(!m.left_publish_success||!m.right_publish_success||m.left_publish_start_steady_ns<=0||m.left_publish_start_steady_ns>m.left_publish_end_steady_ns||m.left_publish_end_steady_ns>m.right_publish_start_steady_ns||m.right_publish_start_steady_ns>m.right_publish_end_steady_ns||m.right_publish_end_steady_ns>entry||!std::isfinite(m.final_n[0])||!std::isfinite(m.final_n[1])||std::abs(m.final_n[0])>25||std::abs(m.final_n[1])>25))reason="actual_channel_call_domain";
  if(reason.empty()){model_->add(m.left_publish_end_steady_ns,0,m.final_n[0],m.sequence);model_->add(m.right_publish_end_steady_ns,1,m.final_n[1],m.sequence);last_applied_sequence_=m.sequence;++applied_accepted_;}
  source({{"type","nominal_applied_callback"},{"raw_input",raw},{"authentication_reason",reason},{"accepted",reason.empty()},{"sequence",m.sequence},{"processed_ns",p1_owned::steady_ns()},{"applied_received_watermark",applied_received_},{"applied_accepted_watermark",applied_accepted_},{"final_n",m.final_n},{"left_publish_end_ns",m.left_publish_end_steady_ns},{"right_publish_end_ns",m.right_publish_end_steady_ns}});
 }
 void publish(){if(!driver_->alive()){stop_requested=true;return;}if(!start_){if(!std::filesystem::exists(start_file_))return;
    auto command=c36_owned::detail::strict_json(c36_owned::detail::read_manifest(start_file_));
    const std::set<std::string> keys={"schema","run_id","boot_id","contract_sha256","scope","driver_manifest_sha256","owner","issued_ns","sequence"};
    p1_owned::require(command.size()==keys.size(),"M4 Fixture start exact fields");for(const auto &k:keys)p1_owned::require(command.contains(k),"M4 Fixture start missing field");
    p1_owned::require(command.at("run_id")==run_&&command.at("boot_id")==p1_owned::boot_id()&&command.at("schema")=="M4-owned-inputs-start-v1"&&command.at("contract_sha256")==contract_&&command.at("scope")==m4_owned::scope&&command.at("driver_manifest_sha256")==driver_pin_.at("manifest_sha256")&&c36_owned::detail::uint_field(command,"sequence",1)==1,"M4 Fixture start actual identity");
    const auto issued=c36_owned::detail::uint_field(command,"issued_ns",INT64_MAX);const auto checked=p1_owned::steady_ns();
    p1_owned::require(issued>0&&issued<=uint64_t(checked)&&uint64_t(checked)-issued<=2000000000ULL&&driver_->stable_manifest(),"M4 Fixture start time/Driver");
    const auto &p=command.at("owner");formal_owned::Peer checked_owner(p,m4_owned::owner_role,run_,contract_);
    p1_owned::require(checked_owner.manifest().at("contract_configuration")==contract_configuration_&&checked_owner.manifest().at("m4_release_scope")==m4_owned::scope,"M4 Fixture exact owner contract/scope");
    for(const auto &key:{"left","right"})p1_owned::require(m4_owned::graph_publisher(*this,checked_owner.manifest(),contract_configuration_.at("output_topics").at(key),"std_msgs/msg/Float64"),"M4 Fixture sole actual owner outputs");
    owner_peer_=std::make_unique<controlled::ExactPeer>(controlled::ExpectedPeer{p.at("manifest_path"),m4_owned::owner_role,run_,contract_,p.at("binary_sha256"),p.at("source_bundle_sha256"),"/research/control/applied","usv_research_interfaces/msg/AppliedControl"});
    source({{"type","nominal_owner_peer_bound"},{"peer",owner_peer_->evidence()},{"start_request",command},{"contract_hydro",hydro_},{"model_contract_sha256",contract_},{"initial_zero_force_is_nominal_fixture_assumption_not_command_authority",true}});
    start_=p1_owned::steady_ns();}

  const auto target=p1_owned::steady_ns();auto model_step=model_->state_at(start_,target,mode_=="C");const auto state=model_step.at("state").get<std::array<double,6>>();
  int64_t ns=100000000000LL+target-start_;builtin_interfaces::msg::Time stamp;stamp.sec=int32_t(ns/1000000000);stamp.nanosec=uint32_t(ns%1000000000);
  rosgraph_msgs::msg::Clock c;c.clock=stamp;clock_->publish(c);
  nav_msgs::msg::Odometry o;o.header.stamp=stamp;o.header.frame_id="map";o.child_frame_id="wamv/base_link";o.pose.pose.position.x=state[0];o.pose.pose.position.y=state[1];o.pose.pose.orientation.z=std::sin(state[2]/2);o.pose.pose.orientation.w=std::cos(state[2]/2);o.twist.twist.linear.x=state[3];o.twist.twist.linear.y=state[4];o.twist.twist.angular.z=state[5];odom_->publish(o);
  sensor_msgs::msg::Imu i;i.header.stamp=stamp;i.header.frame_id="wamv/wamv/base_link/imu_sensor";i.orientation.z=std::sin(state[2]/2);i.orientation.w=std::cos(state[2]/2);i.angular_velocity.z=state[5];imu_->publish(i);
  model_step["sensor_sequence"]=count_+1;model_step["sim_stamp_ns"]=ns;model_step["applied_received_watermark"]=applied_received_;model_step["applied_accepted_watermark"]=applied_accepted_;model_step["sensor_publish_end_ns"]=p1_owned::steady_ns();source(model_step);
  if(count_%25==0){auto reference=controlled::reference(o.header,mode_,reference_speed_);path_->publish(reference.first);profile_->publish(reference.second);++reference_count_;}
  ++count_;
 }
 p1_owned::Json contract_configuration_,driver_pin_;std::unique_ptr<formal_owned::Peer> driver_;
 double reference_speed_=0.;
 std::string mode_,owner_manifest_,owner_binary_,owner_source_,owner_run_,contract_file_;p1_owned::Json hydro_;std::ofstream nominal_;
 std::unique_ptr<controlled::ExactPeer> owner_peer_;std::unique_ptr<controlled::NominalHistory> model_;
 rclcpp::Subscription<usv_research_interfaces::msg::AppliedControl>::SharedPtr applied_;
 uint64_t applied_received_=0,applied_accepted_=0,last_applied_sequence_=0;
 std::string run_,contract_,output_,start_file_,topics_file_,topics_sha_;int64_t start_=0;uint64_t count_=0,reference_count_=0,ordinal_=0;bool failed_=false;std::ofstream log_;p1_owned::Json transport_counts_=p1_owned::Json::object();std::vector<rclcpp::GenericSubscription::SharedPtr> subs_;
 rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odom_;rclcpp::Publisher<sensor_msgs::msg::Imu>::SharedPtr imu_;rclcpp::Publisher<nav_msgs::msg::Path>::SharedPtr path_;rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr profile_;rclcpp::Publisher<rosgraph_msgs::msg::Clock>::SharedPtr clock_;rclcpp::TimerBase::SharedPtr timer_;rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr frozen_;
};
int main(int argc,char **argv){try{rclcpp::init(argc,argv,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);std::signal(SIGINT,stop_signal);std::signal(SIGTERM,stop_signal);auto node=std::make_shared<Synthetic>();while(rclcpp::ok()&&!stop_requested){rclcpp::spin_some(node);std::this_thread::sleep_for(std::chrono::milliseconds(2));}node->stop_publishing();auto drain=p1_owned::steady_ns()+200000000LL;while(rclcpp::ok()&&p1_owned::steady_ns()<drain){rclcpp::spin_some(node);std::this_thread::sleep_for(std::chrono::milliseconds(2));}node->close();node.reset();rclcpp::shutdown();return 0;}catch(const std::exception&e){fprintf(stderr,"synthetic source failed: %s\n",e.what());if(rclcpp::ok())rclcpp::shutdown();return 2;}}
