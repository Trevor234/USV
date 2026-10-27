// SPDX-License-Identifier: MIT
// A separate stationary-equilibrium fixture, with an explicit nonzero time axis.
#pragma once
#include <nav_msgs/msg/path.hpp>
#include <std_msgs/msg/float64_multi_array.hpp>
#include <utility>

namespace p1_zero_reference {
constexpr size_t sample_count=61;
constexpr size_t fields_per_sample=4;
constexpr double step_seconds=0.2;
inline std::pair<nav_msgs::msg::Path,std_msgs::msg::Float64MultiArray>
make(const std_msgs::msg::Header &header) {
  nav_msgs::msg::Path path;path.header=header;
  std_msgs::msg::Float64MultiArray profile;
  profile.layout.dim.resize(2);
  profile.layout.dim[0].label="stamp_sec:"+std::to_string(header.stamp.sec);
  profile.layout.dim[0].size=sample_count;
  profile.layout.dim[0].stride=sample_count*fields_per_sample;
  profile.layout.dim[1].label="stamp_nanosec:"+std::to_string(header.stamp.nanosec);
  profile.layout.dim[1].size=fields_per_sample;
  profile.layout.dim[1].stride=fields_per_sample;
  path.poses.reserve(sample_count);profile.data.reserve(sample_count*fields_per_sample);
  for(size_t k=0;k<sample_count;++k) {
    geometry_msgs::msg::PoseStamped pose;pose.header=header;
    pose.pose.orientation.w=1.0;
    path.poses.push_back(pose);
    profile.data.insert(profile.data.end(),{0.0,0.0,0.0,step_seconds*double(k)});
  }
  return {path,profile};
}
} // namespace p1_zero_reference
