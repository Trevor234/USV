// SPDX-License-Identifier: MIT
#include "formal_owned_runtime.hpp"
#include <thread>
namespace fo=formal_owned;
namespace {std::atomic<bool> stopped{false};void on_signal(int){stopped=true;}}
class FormalFixture final:public rclcpp::Node {
 public:
  FormalFixture():Node("p1_synthetic_source",fo::node_options()){
    fo::entry_arguments(*this);
    run_=declare_parameter<std::string>("run_id","");hash_=declare_parameter<std::string>("contract_hash","");
    const auto file=declare_parameter<std::string>("contract_file","");const auto mode=declare_parameter<std::string>("mode","");
    c_=fo::load_contract(file,hash_,mode);out_=declare_parameter<std::string>("output_dir","");
    start_file_=declare_parameter<std::string>("start_file","");
    const auto driver_path=declare_parameter<std::string>("driver_pins_file","");
    const auto driver_hash=declare_parameter<std::string>("driver_pins_sha256","");
    fo::overrides(*this,{"run_id","contract_hash","contract_file","mode","output_dir","start_file","driver_pins_file","driver_pins_sha256","use_sim_time"});
    fo::require(p1::formal_prepare::text(run_,128),"Fixture run domain");
    driver_pin_=fo::read_pinned(driver_path,driver_hash);driver_=fo::driver_peer(driver_pin_,run_,hash_);
    fo::require(!std::filesystem::exists(start_file_)&&!std::filesystem::is_symlink(std::filesystem::symlink_status(start_file_)),"Fixture fresh start token");
    source_=std::make_unique<fo::Source>(out_+"/source.jsonl");
    const auto t=fo::inputs(c_);
    clock_=create_publisher<rosgraph_msgs::msg::Clock>(t[0].first,rclcpp::ClockQoS());
    odom_=create_publisher<nav_msgs::msg::Odometry>(t[1].first,rclcpp::SensorDataQoS());
    imu_=create_publisher<sensor_msgs::msg::Imu>(t[2].first,rclcpp::SensorDataQoS());
    path_=create_publisher<nav_msgs::msg::Path>(t[3].first,rclcpp::QoS(1).reliable());
    profile_=create_publisher<std_msgs::msg::Float64MultiArray>(t[4].first,rclcpp::QoS(1).reliable());
    cap_=create_subscription<fo::Capability>(fo::cap_topic,rclcpp::QoS(1).reliable().transient_local(),
      [this](fo::Capability::ConstSharedPtr m,const rclcpp::MessageInfo &info){
        fo::require(fo::bounded(*m),"Fixture typed Capability bound before copy");
        source_->add({{"type","capability_transport_receipt"},{"received_ns",p1_owned::steady_ns()},
          {"publisher_gid",p1_owned::gid_json(info.get_rmw_message_info().publisher_gid)},
          {"payload",fo::capability_json(*m)},{"cdr",fo::cdr(*m)}});++cap_count_;});
    auto eps=fo::Json::array({p1_owned::publisher_endpoint(*clock_,t[0].second),p1_owned::publisher_endpoint(*odom_,t[1].second),
      p1_owned::publisher_endpoint(*imu_,t[2].second),p1_owned::publisher_endpoint(*path_,t[3].second),
      p1_owned::publisher_endpoint(*profile_,t[4].second),p1_owned::subscription_endpoint(*cap_,"usv_research_interfaces/msg/WorkerCapability")});
    frozen_=p1_owned::freeze_parameters(*this);
    p1_owned::write_create_only(out_+"/manifest.json",p1_owned::role_manifest(*this,"synthetic_source",run_,hash_,P1_OWNED_SOURCE_BUNDLE_SHA256,eps,
      {{"source_fd",p1_owned::source_fd_identity(out_+"/source.jsonl")},{"mode",mode},{"contract_configuration",c_},
       {"source_state","stationary_zero_equilibrium"},{"rate_hz",50},{"reference_points",21},{"reference_profile_columns",4},
       {"physical_publishers",0},{"Applied_publishers",0},{"Applied_subscribers",0},{"plant_connected",false},
       {"spec_sha256",p1::full_contract_spec_sha256},{"driver_manifest_sha256",driver_pin_.at("manifest_sha256")}}));
    own_sha_=p1_owned::file_sha256(out_+"/manifest.json");
    source_->add({{"type","fixture_waiting"},{"manifest_sha256",own_sha_},{"source_state","stationary_zero_equilibrium"}});
    timer_=create_wall_timer(std::chrono::milliseconds(20),[this]{tick();});
  }
  void close(){
    timer_->cancel();source_->add({{"type","fixture_closed"},{"published_counts",counts_},{"capability_receipts",cap_count_},
      {"publish_calls",calls_},{"publish_returned",returned_},{"Applied_messages",0},{"physical_publish_calls",0},
      {"normal_source_complete",calls_==returned_&&source_->good()}});source_->finish();
    p1_owned::write_create_only(out_+"/terminal.json",{{"schema","formal-fixture-terminal-v1"},{"run_id",run_},{"boot_id",p1_owned::boot_id()},
      {"contract_sha256",hash_},{"manifest_sha256",own_sha_},{"published_counts",counts_},{"publish_calls",calls_},
      {"publish_returned",returned_},{"normal_source_complete",calls_==returned_&&source_->good()},
      {"physical_publish_calls",0},{"Applied_messages",0},{"stage_qualified",false},{"execute_qualified",false}});
  }
 private:
  template<class M>void publish(rclcpp::Publisher<M> &pub,const M &m,const std::string &topic){
    const auto bytes=fo::cdr(m);const auto start=p1_owned::steady_ns();++calls_;
    try{pub.publish(m);++returned_;counts_[topic]=counts_.value(topic,uint64_t(0))+1;
      source_->add({{"type","input_publish_result"},{"topic",topic},{"frame_sequence",sequence_},
        {"sim_ns",sim_ns_},{"publish_start_ns",start},{"publish_end_ns",p1_owned::steady_ns()},
        {"returned",true},{"cdr",bytes},{"publisher_gid",p1_owned::gid_json(pub.get_gid())}});
    }catch(...){source_->add({{"type","input_publish_result"},{"topic",topic},{"returned",false},{"cdr",bytes}});throw;}
  }
  void tick(){
    if(!start_ns_){
      if(!std::filesystem::exists(start_file_))return;
      const auto j=c36_owned::detail::strict_json(c36_owned::detail::read_manifest(start_file_));
      fo::require(driver_->stable_manifest()&&j.at("schema")=="formal-fixture-start-v1"&&j.at("run_id")==run_&&
        j.at("boot_id")==p1_owned::boot_id()&&j.at("contract_sha256")==hash_&&j.at("fixture_manifest_sha256")==own_sha_&&
        j.at("driver_manifest_sha256")==driver_pin_.at("manifest_sha256"),"Fixture start bound identity");
      const auto now=p1_owned::steady_ns();const auto issued=p1::formal_prepare::integer(j,"issued_ns",1);
      fo::require(issued<=now&&now-issued<=2000000000LL&&j.at("sequence")==1,"Fixture start TTL/sequence");
      fo::require(clock_->get_subscription_count()==2&&odom_->get_subscription_count()==2&&imu_->get_subscription_count()==2&&
        path_->get_subscription_count()==2&&profile_->get_subscription_count()==2,"Fixture actual input Reader counts");
      start_ns_=now;source_->add({{"type","fixture_started"},{"start_ns",now},{"start_request",j}});
    }
    fo::require(driver_->alive(),"Fixture Driver exited");
    sim_ns_=100000000000LL+p1_owned::steady_ns()-start_ns_;++sequence_;
    builtin_interfaces::msg::Time stamp;stamp.sec=int32_t(sim_ns_/1000000000LL);stamp.nanosec=uint32_t(sim_ns_%1000000000LL);
    rosgraph_msgs::msg::Clock clock;clock.clock=stamp;
    nav_msgs::msg::Odometry odom;odom.header.stamp=stamp;odom.header.frame_id=c_.at("expected_pose_frame");
    odom.child_frame_id=c_.at("expected_child_frame");odom.pose.pose.orientation.w=1.;
    sensor_msgs::msg::Imu imu;imu.header.stamp=stamp;imu.header.frame_id=c_.at("expected_imu_frame");imu.orientation.w=1.;
    nav_msgs::msg::Path path;path.header=odom.header;
    std_msgs::msg::Float64MultiArray profile;profile.layout.dim.resize(2);
    profile.layout.dim[0].label="stamp_sec:"+std::to_string(stamp.sec);profile.layout.dim[0].size=21;profile.layout.dim[0].stride=84;
    profile.layout.dim[1].label="stamp_nanosec:"+std::to_string(stamp.nanosec);profile.layout.dim[1].size=4;profile.layout.dim[1].stride=4;
    for(int k=0;k<=20;++k){geometry_msgs::msg::PoseStamped p;p.header=odom.header;p.pose.orientation.w=1.;path.poses.push_back(p);
      profile.data.insert(profile.data.end(),{0.,0.,0.,.2*k});}
    const auto t=fo::inputs(c_);publish(*clock_,clock,t[0].first);publish(*odom_,odom,t[1].first);
    publish(*imu_,imu,t[2].first);publish(*path_,path,t[3].first);publish(*profile_,profile,t[4].first);
  }
  std::string run_,hash_,out_,start_file_,own_sha_;fo::Json c_,driver_pin_,counts_=fo::Json::object();
  std::unique_ptr<fo::Peer> driver_;std::unique_ptr<fo::Source> source_;int64_t start_ns_=0,sim_ns_=0;
  uint64_t sequence_=0,calls_=0,returned_=0,cap_count_=0;
  rclcpp::Publisher<rosgraph_msgs::msg::Clock>::SharedPtr clock_;rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odom_;
  rclcpp::Publisher<sensor_msgs::msg::Imu>::SharedPtr imu_;rclcpp::Publisher<nav_msgs::msg::Path>::SharedPtr path_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr profile_;rclcpp::Subscription<fo::Capability>::SharedPtr cap_;
  rclcpp::TimerBase::SharedPtr timer_;rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr frozen_;
};
int main(int argc,char **argv){try{
  rclcpp::init(argc,argv,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);std::signal(SIGINT,on_signal);std::signal(SIGTERM,on_signal);
  auto node=std::make_shared<FormalFixture>();while(rclcpp::ok()&&!stopped){rclcpp::spin_some(node);std::this_thread::sleep_for(std::chrono::milliseconds(1));}
  node->close();node.reset();rclcpp::shutdown();return 0;
}catch(const std::exception&e){fprintf(stderr,"formal Fixture: %s\n",e.what());if(rclcpp::ok())rclcpp::shutdown();return 2;}}
