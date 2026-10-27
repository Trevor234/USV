// SPDX-License-Identifier: MIT
#pragma once
#include "controlled_protocol.hpp"
#include <nav_msgs/msg/path.hpp>
#include <std_msgs/msg/float64_multi_array.hpp>
namespace controlled {
inline std::pair<nav_msgs::msg::Path,std_msgs::msg::Float64MultiArray> reference(const std_msgs::msg::Header &header,const std::string &mode,double speed) {
 p1_owned::require(mode_valid(mode),"controlled reference mode");
 p1_owned::require(std::isfinite(speed)&&(mode=="C"?(speed==.05||speed==.1||speed==.3||speed==.6):speed==0.),"controlled reference speed domain");
 nav_msgs::msg::Path path;path.header=header;std_msgs::msg::Float64MultiArray profile;profile.layout.dim.resize(2);
 profile.layout.dim[0].label="stamp_sec:"+std::to_string(header.stamp.sec);profile.layout.dim[0].size=201;profile.layout.dim[0].stride=804;
 profile.layout.dim[1].label="stamp_nanosec:"+std::to_string(header.stamp.nanosec);profile.layout.dim[1].size=4;profile.layout.dim[1].stride=4;
 for(int k=0;k<=200;++k){geometry_msgs::msg::PoseStamped pose;pose.header=header;pose.pose.position.x=speed*(.2*k);pose.pose.orientation.w=1.;path.poses.push_back(pose);profile.data.insert(profile.data.end(),{speed,0.,0.,.2*k});}
 return {path,profile};
}
} // namespace controlled
