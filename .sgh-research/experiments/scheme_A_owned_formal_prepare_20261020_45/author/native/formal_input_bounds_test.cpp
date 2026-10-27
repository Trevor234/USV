// SPDX-License-Identifier: MIT
#include "formal_owned_runtime.hpp"
#include <iostream>
int main(){
  using formal_owned::bounded;size_t checks=0;
  auto check=[&checks](bool okay){if(!okay)throw std::runtime_error("new typed domain boundary failed");++checks;};
  rosgraph_msgs::msg::Clock c;check(bounded(c));c.clock.nanosec=1000000000;check(!bounded(c));
  nav_msgs::msg::Odometry o;o.header.frame_id=std::string(128,'x');check(bounded(o));o.header.frame_id+='x';check(!bounded(o));
  sensor_msgs::msg::Imu i;i.header.frame_id=std::string(128,'x');check(bounded(i));i.header.frame_id+='x';check(!bounded(i));
  nav_msgs::msg::Path p;p.poses.resize(2048);check(bounded(p));p.poses.resize(2049);check(!bounded(p));
  p.poses.resize(1);p.poses[0].header.frame_id=std::string(129,'x');check(!bounded(p));
  std_msgs::msg::Float64MultiArray a;a.data.resize(8192);check(bounded(a));a.data.push_back(0);check(!bounded(a));
  a.data.clear();a.layout.dim.resize(4);check(bounded(a));a.layout.dim.resize(5);check(!bounded(a));
  a.layout.dim.resize(1);a.layout.dim[0].label=std::string(64,'x');check(bounded(a));a.layout.dim[0].label+='x';check(!bounded(a));
  formal_owned::Capability cap;cap.reason=std::string(128,'x');check(bounded(cap));cap.reason+='x';check(!bounded(cap));
  std::cout<<"{\"passed\":true,\"checks\":"<<checks<<",\"ROS_context_created\":false}"<<std::endl;
}
