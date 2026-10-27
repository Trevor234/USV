// SPDX-License-Identifier: MIT
#include "nominal_history.hpp"
#include "controlled_reference.hpp"
#include <gtest/gtest.h>
#include <rclcpp/serialization.hpp>
#include <rclcpp/serialized_message.hpp>
namespace {
using Json=p1_owned::Json;const std::string sha(64,'a');
Json hydro(){return {{"mass",14.2},{"Iz",2.13},{"xg",.12},{"d_thruster",.25},{"Xu_dot",-2.},{"Yv_dot",-8.},{"Yr_dot",-.1817725},{"Nv_dot",-.1817725},{"Nr_dot",-3.41},{"Xu",-2.272063},{"Yv",-2.629019},{"Yr",0.},{"Nv",0.},{"Nr",-3.105},{"Xuu",-11.571784},{"Yvv",-.05},{"Yrr",0.},{"Nvv",0.},{"Nrr",-.71}};}
TEST(ControlledFixture,ExplicitHydroAndHashAreAlwaysRecorded){controlled::NominalHistory h(hydro(),sha);const auto r=h.state_at(1000000000,1200000000,true);
 EXPECT_EQ(r["contract_hydro"],hydro());
 EXPECT_EQ(r["model_contract_sha256"],sha);
 EXPECT_EQ(r["plant_connected"],false);
 EXPECT_EQ(r["state"],Json::array({0.,0.,0.,0.,0.,0.}));}
TEST(ControlledFixture,AsymmetricThrustExposesContractVersusHeaderDefaultDifference){controlled::NominalHistory h(hydro(),sha);h.add(1000000000,0,.1,1);h.add(1000000000,1,.2,1);const auto result=h.state_at(1000000000,1200000000,true);auto state=result["state"].get<std::array<double,6>>();usv_mpc::Vector6d defaults=usv_mpc::Vector6d::Zero();Eigen::Vector2d u(.1,.2);usv_mpc::USVDynamicModel default_model(.002,4);for(int k=0;k<100;++k)defaults=default_model.forward(defaults,u);
 EXPECT_GT(std::abs(state[5]),1e-5);
 EXPECT_GT(std::abs(state[5]-defaults[5]),1e-6);
 EXPECT_GT(state[0],0.);}
TEST(ControlledFixture,IndividualChannelCompletionTimesAreReplayedInOrder){controlled::NominalHistory h(hydro(),sha);h.add(1030000000,1,.2,1);h.add(1020000000,0,.1,1);auto r=h.state_at(1000000000,1100000000,true);ASSERT_EQ(r["held_events"].size(),2u);
 EXPECT_EQ(r["held_events"][0]["channel"],0);
 EXPECT_EQ(r["held_events"][0]["publish_end_ns"],1020000000);
 EXPECT_EQ(r["held_events"][1]["channel"],1);
 EXPECT_GT(r["state"][3].get<double>(),0.);}
TEST(ControlledFixture,StationaryControlRetainsActualHistoryWithoutClaimingDynamics){controlled::NominalHistory h(hydro(),sha);h.add(1000000000,0,.1,1);h.add(1000000001,1,.1,1);auto r=h.state_at(1000000000,1200000000,false);
 EXPECT_EQ(r["state"],Json::array({0.,0.,0.,0.,0.,0.}));
 EXPECT_EQ(r["diagnostic_nominal_model_connected"],false);
 EXPECT_EQ(r["held_events"].size(),2u);}
TEST(ControlledFixture,MissingNonfiniteOrExtraHydroIsRejected){auto h=hydro();h.erase("Nr_dot");
 EXPECT_ANY_THROW(controlled::NominalHistory(h,sha));
 h=hydro();h["Nr"]=std::numeric_limits<double>::quiet_NaN();
 EXPECT_ANY_THROW(controlled::NominalHistory(h,sha));
 h=hydro();h["other"]=0.;
 EXPECT_ANY_THROW(controlled::NominalHistory(h,sha));}
TEST(ControlledFixture,DuplicateNonfiniteAndUnboundedEventsAreRejected){controlled::NominalHistory h(hydro(),sha);h.add(1000000000,0,.1,1);
 EXPECT_ANY_THROW(h.add(1000000001,0,.1,1));
 EXPECT_ANY_THROW(h.add(1000000001,1,std::numeric_limits<double>::infinity(),1));
 EXPECT_ANY_THROW(h.add(1000000001,2,.1,2));
 EXPECT_ANY_THROW(h.state_at(1000000000,1000000000+40000000001LL,true));}
TEST(ControlledFixture,FutureEventsNeverInfluenceEarlierState){controlled::NominalHistory h(hydro(),sha);h.add(1200000000,0,1.,1);auto r=h.state_at(1000000000,1100000000,true);
 EXPECT_TRUE(r["held_events"].empty());
 EXPECT_EQ(r["state"],Json::array({0.,0.,0.,0.,0.,0.}));}
TEST(ControlledFixture,DynamicReferenceIsNonzeroAndStationaryControlIsZero){std_msgs::msg::Header header;header.frame_id="map";header.stamp.sec=100;auto c=controlled::reference(header,"C");ASSERT_EQ(c.first.poses.size(),61u);ASSERT_EQ(c.second.data.size(),244u);
 EXPECT_DOUBLE_EQ(c.first.poses.back().pose.position.x,.6);
 EXPECT_DOUBLE_EQ(c.second.data[0],.05);
 EXPECT_DOUBLE_EQ(c.second.data.back(),12.);for(const auto mode:{"A2","B"}){auto z=controlled::reference(header,mode);for(const auto &p:z.first.poses)EXPECT_DOUBLE_EQ(p.pose.position.x,0.);for(size_t k=0;k<61;++k){EXPECT_DOUBLE_EQ(z.second.data[4*k],0.);
 EXPECT_DOUBLE_EQ(z.second.data[4*k+3],.2*k);}}}
TEST(ControlledFixture,DynamicProfileUsesActualRosCdrWithoutNode){std_msgs::msg::Header header;header.frame_id="map";header.stamp.sec=100;auto p=controlled::reference(header,"C").second;rclcpp::Serialization<std_msgs::msg::Float64MultiArray> codec;rclcpp::SerializedMessage bytes;codec.serialize_message(&p,&bytes);std_msgs::msg::Float64MultiArray decoded;codec.deserialize_message(&bytes,&decoded);
 EXPECT_EQ(decoded,p);}
} // namespace
