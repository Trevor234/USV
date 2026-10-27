// SPDX-License-Identifier: MIT
// Explicit synthetic sensors/reference only; no plant/Gazebo/FCU connection.
#include "p1_owned_identity.hpp"
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
 Synthetic():Node("p1_synthetic_source") {
  run_=declare_parameter<std::string>("run_id","");
  contract_=declare_parameter<std::string>("contract_hash","");
  output_=declare_parameter<std::string>("output_dir","");
  start_file_=declare_parameter<std::string>("start_file","");
  topics_file_=declare_parameter<std::string>("topics_file","");
  topics_sha_=declare_parameter<std::string>("topics_sha256","");
  p1_owned::require(p1_owned::file_sha256(topics_file_)==topics_sha_,"synthetic topic declaration differs");
  odom_=create_publisher<nav_msgs::msg::Odometry>("/wamv/sensors/position/ground_truth_odometry",rclcpp::SensorDataQoS());
  imu_=create_publisher<sensor_msgs::msg::Imu>("/wamv/sensors/imu/imu/data",rclcpp::SensorDataQoS());
  path_=create_publisher<nav_msgs::msg::Path>("/path/reference",rclcpp::QoS(1).reliable());
  profile_=create_publisher<std_msgs::msg::Float64MultiArray>("/path/reference_profile",rclcpp::QoS(1).reliable());
  clock_=create_publisher<rosgraph_msgs::msg::Clock>("/clock",rclcpp::ClockQoS());
  p1_owned::Json eps=p1_owned::Json::array({p1_owned::publisher_endpoint(*odom_,"nav_msgs/msg/Odometry"),p1_owned::publisher_endpoint(*imu_,"sensor_msgs/msg/Imu"),p1_owned::publisher_endpoint(*path_,"nav_msgs/msg/Path"),p1_owned::publisher_endpoint(*profile_,"std_msgs/msg/Float64MultiArray"),p1_owned::publisher_endpoint(*clock_,"rosgraph_msgs/msg/Clock")});
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
  auto manifest=p1_owned::role_manifest(*this,"synthetic_source",run_,contract_,P1_OWNED_SOURCE_BUNDLE_SHA256,eps,{{"synthetic",true},{"plant_connected",false},{"rate_hz",50},{"source_state","stationary_zero"},{"reference_speed_m_s",0.6},{"transport_observer",true},{"source_fd",p1_owned::source_fd_identity(output_+"/transport_source.jsonl")}});
  p1_owned::write_create_only(output_+"/owned_manifest.json",manifest);
  timer_=create_wall_timer(std::chrono::milliseconds(20),[this]{publish();});
 }
 void close(){p1_owned::Json counts={{"/clock",count_},{"/wamv/sensors/position/ground_truth_odometry",count_},{"/wamv/sensors/imu/imu/data",count_},{"/path/reference",reference_count_},{"/path/reference_profile",reference_count_}};
  log_.flush();failed_=failed_||!log_;p1_owned::write_create_only(output_+"/terminal.json",{{"run_id",run_},{"synthetic",true},{"closed_steady_ns",p1_owned::steady_ns()},{"published_counts",counts},{"transport_counts",transport_counts_},{"normal_end",!failed_},{"failed",failed_},{"transport_total",ordinal_}});}
 void stop_publishing(){timer_->cancel();}
 private:
 void publish(){if(!start_){if(!std::filesystem::exists(start_file_))return;auto command=p1_owned::Json::parse(p1_owned::read_bounded(start_file_));p1_owned::require(command.at("run_id")==run_&&command.at("boot_id")==p1_owned::boot_id()&&command.at("schema")=="p1-synthetic-start-v1","synthetic start identity differs");start_=p1_owned::steady_ns();}
  int64_t ns=100000000000LL+p1_owned::steady_ns()-start_;builtin_interfaces::msg::Time stamp;stamp.sec=int32_t(ns/1000000000);stamp.nanosec=uint32_t(ns%1000000000);
  rosgraph_msgs::msg::Clock c;c.clock=stamp;clock_->publish(c);
  nav_msgs::msg::Odometry o;o.header.stamp=stamp;o.header.frame_id="map";o.child_frame_id="wamv/base_link";o.pose.pose.orientation.w=1;odom_->publish(o);
  sensor_msgs::msg::Imu i;i.header.stamp=stamp;i.header.frame_id="wamv/wamv/base_link/imu_sensor";i.orientation.w=1;imu_->publish(i);
  if(count_%25==0){nav_msgs::msg::Path p;p.header=o.header;std_msgs::msg::Float64MultiArray f;f.layout.dim.resize(2);f.layout.dim[0].label="stamp_sec:"+std::to_string(stamp.sec);f.layout.dim[0].size=61;f.layout.dim[0].stride=244;f.layout.dim[1].label="stamp_nanosec:"+std::to_string(stamp.nanosec);f.layout.dim[1].size=4;f.layout.dim[1].stride=4;
   for(int k=0;k<=60;++k){geometry_msgs::msg::PoseStamped ps;ps.header=o.header;ps.pose.position.x=.5*k;ps.pose.orientation.w=1;p.poses.push_back(ps);f.data.insert(f.data.end(),{.6,0.,0.,.5*k/.6});}
   path_->publish(p);profile_->publish(f);++reference_count_;}
  ++count_;
 }
 std::string run_,contract_,output_,start_file_,topics_file_,topics_sha_;int64_t start_=0;uint64_t count_=0,reference_count_=0,ordinal_=0;bool failed_=false;std::ofstream log_;p1_owned::Json transport_counts_=p1_owned::Json::object();std::vector<rclcpp::GenericSubscription::SharedPtr> subs_;
 rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odom_;rclcpp::Publisher<sensor_msgs::msg::Imu>::SharedPtr imu_;rclcpp::Publisher<nav_msgs::msg::Path>::SharedPtr path_;rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr profile_;rclcpp::Publisher<rosgraph_msgs::msg::Clock>::SharedPtr clock_;rclcpp::TimerBase::SharedPtr timer_;rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr frozen_;
};
int main(int argc,char **argv){try{rclcpp::init(argc,argv,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);std::signal(SIGINT,stop_signal);std::signal(SIGTERM,stop_signal);auto node=std::make_shared<Synthetic>();while(rclcpp::ok()&&!stop_requested){rclcpp::spin_some(node);std::this_thread::sleep_for(std::chrono::milliseconds(2));}node->stop_publishing();auto drain=p1_owned::steady_ns()+200000000LL;while(rclcpp::ok()&&p1_owned::steady_ns()<drain){rclcpp::spin_some(node);std::this_thread::sleep_for(std::chrono::milliseconds(2));}node->close();node.reset();rclcpp::shutdown();return 0;}catch(const std::exception&e){fprintf(stderr,"synthetic source failed: %s\n",e.what());if(rclcpp::ok())rclcpp::shutdown();return 2;}}
