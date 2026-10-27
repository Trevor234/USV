// SPDX-License-Identifier: MIT
#include "zero_reference.hpp"
#include <gtest/gtest.h>
#include <rclcpp/serialization.hpp>
#include <rclcpp/serialized_message.hpp>
#include <cmath>

namespace {
std_msgs::msg::Header header() {
  std_msgs::msg::Header h;h.frame_id="map";h.stamp.sec=100;h.stamp.nanosec=123456789;
  return h;
}
template<class Message> Message roundtrip(const Message &input) {
  rclcpp::Serialization<Message> codec;rclcpp::SerializedMessage bytes;
  codec.serialize_message(&input,&bytes);
  EXPECT_GT(bytes.size(),0u);
  Message output;codec.deserialize_message(&bytes,&output);return output;
}
TEST(ZeroReference,StationaryPoseHasValidIdentityQuaternionAtEverySample) {
  const auto reference=p1_zero_reference::make(header());
  ASSERT_EQ(reference.first.poses.size(),61u);
  for(const auto &pose:reference.first.poses) {
    EXPECT_EQ(pose.header,header());
    EXPECT_DOUBLE_EQ(pose.pose.position.x,0.0);
    EXPECT_DOUBLE_EQ(pose.pose.position.y,0.0);
    EXPECT_DOUBLE_EQ(pose.pose.position.z,0.0);
    EXPECT_DOUBLE_EQ(pose.pose.orientation.x,0.0);
    EXPECT_DOUBLE_EQ(pose.pose.orientation.y,0.0);
    EXPECT_DOUBLE_EQ(pose.pose.orientation.z,0.0);
    EXPECT_DOUBLE_EQ(pose.pose.orientation.w,1.0);
  }
}
TEST(ZeroReference,ZeroVelocityYawAndAccelerationWithFiniteStrictTimeAxis) {
  const auto reference=p1_zero_reference::make(header());
  const auto &data=reference.second.data;
  ASSERT_EQ(data.size(),244u);
  for(size_t k=0;k<61;++k) {
    for(size_t j=0;j<4;++j)EXPECT_TRUE(std::isfinite(data[4*k+j]));
    EXPECT_DOUBLE_EQ(data[4*k],0.0);EXPECT_DOUBLE_EQ(data[4*k+1],0.0);
    EXPECT_DOUBLE_EQ(data[4*k+2],0.0);EXPECT_DOUBLE_EQ(data[4*k+3],0.2*double(k));
    if(k)EXPECT_GT(data[4*k+3],data[4*(k-1)+3]);
  }
  EXPECT_DOUBLE_EQ(data.back(),12.0);
}
TEST(ZeroReference,ProfileLayoutRetainsContractStampAndStride) {
  const auto profile=p1_zero_reference::make(header()).second;
  ASSERT_EQ(profile.layout.dim.size(),2u);
  EXPECT_EQ(profile.layout.data_offset,0u);
  EXPECT_EQ(profile.layout.dim[0].label,"stamp_sec:100");
  EXPECT_EQ(profile.layout.dim[1].label,"stamp_nanosec:123456789");
  EXPECT_EQ(profile.layout.dim[0].size,61u);EXPECT_EQ(profile.layout.dim[0].stride,244u);
  EXPECT_EQ(profile.layout.dim[1].size,4u);EXPECT_EQ(profile.layout.dim[1].stride,4u);
}
TEST(ZeroReference,PathSurvivesActualRosCdrSerialization) {
  const auto path=p1_zero_reference::make(header()).first;
  EXPECT_EQ(roundtrip(path),path);
}
TEST(ZeroReference,ProfileSurvivesActualRosCdrSerialization) {
  const auto profile=p1_zero_reference::make(header()).second;
  EXPECT_EQ(roundtrip(profile),profile);
}
TEST(ZeroReference,NewStampDoesNotChangeEquilibriumOrTimeAxis) {
  const auto first=p1_zero_reference::make(header());
  auto next=header();next.stamp.sec+=42;next.stamp.nanosec=999999999;
  const auto second=p1_zero_reference::make(next);
  EXPECT_EQ(first.second.data,second.second.data);
  EXPECT_EQ(second.second.layout.dim[0].label,"stamp_sec:142");
  EXPECT_EQ(second.second.layout.dim[1].label,"stamp_nanosec:999999999");
  ASSERT_EQ(second.first.poses.size(),first.first.poses.size());
  for(size_t k=0;k<second.first.poses.size();++k) {
    EXPECT_EQ(first.first.poses[k].pose,second.first.poses[k].pose);
    EXPECT_EQ(second.first.poses[k].header,next);
  }
}
} // namespace
