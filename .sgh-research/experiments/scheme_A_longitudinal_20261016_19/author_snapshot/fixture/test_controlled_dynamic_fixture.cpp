// SPDX-License-Identifier: MIT
#include "nominal_history.hpp"
#include "controlled_reference.hpp"
#include "full_replay_reference.hpp"
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
TEST(ControlledFixture,DynamicReferenceIsNonzeroAndStationaryControlIsZero){std_msgs::msg::Header header;header.frame_id="map";header.stamp.sec=100;auto c=controlled::reference(header,"C",.05);ASSERT_EQ(c.first.poses.size(),201u);ASSERT_EQ(c.second.data.size(),804u);
 EXPECT_DOUBLE_EQ(c.first.poses.back().pose.position.x,2.0);
 EXPECT_DOUBLE_EQ(c.second.data[0],.05);
 EXPECT_DOUBLE_EQ(c.second.data.back(),40.);for(const auto mode:{"A2","B"}){auto z=controlled::reference(header,mode,0.);for(const auto &p:z.first.poses)EXPECT_DOUBLE_EQ(p.pose.position.x,0.);for(size_t k=0;k<201;++k){EXPECT_DOUBLE_EQ(z.second.data[4*k],0.);
 EXPECT_DOUBLE_EQ(z.second.data[4*k+3],.2*k);}}}
TEST(ControlledFixture,DynamicProfileUsesActualRosCdrWithoutNode){std_msgs::msg::Header header;header.frame_id="map";header.stamp.sec=100;auto p=controlled::reference(header,"C",.05).second;rclcpp::Serialization<std_msgs::msg::Float64MultiArray> codec;rclcpp::SerializedMessage bytes;codec.serialize_message(&p,&bytes);std_msgs::msg::Float64MultiArray decoded;codec.deserialize_message(&bytes,&decoded);
 EXPECT_EQ(decoded,p);}
TEST(ControlledFixture,EachPositiveSpeedHasAStaticFortySecondMatchingReference) {
 std_msgs::msg::Header header;header.frame_id="map";header.stamp.sec=100;
 for(const double speed:{.05,.1,.3,.6}) {
  const auto r=controlled::reference(header,"C",speed);
  ASSERT_EQ(r.first.poses.size(),201u);
  ASSERT_EQ(r.second.data.size(),804u);
  for(size_t k=0;k<201;++k){EXPECT_DOUBLE_EQ(r.first.poses[k].pose.position.x,speed*(.2*k));EXPECT_DOUBLE_EQ(r.second.data[4*k],speed);EXPECT_DOUBLE_EQ(r.second.data[4*k+3],.2*k);}
  EXPECT_GE(r.first.poses.back().pose.position.x,speed*(20.+4.));
 }
}
TEST(ControlledFixture,SpeedAndStationaryModeDomainAreExplicit) {
 std_msgs::msg::Header header;
 EXPECT_ANY_THROW(controlled::reference(header,"C",0.));
 EXPECT_ANY_THROW(controlled::reference(header,"C",.2));
 EXPECT_ANY_THROW(controlled::reference(header,"C",std::numeric_limits<double>::quiet_NaN()));
 EXPECT_ANY_THROW(controlled::reference(header,"A2",.05));
 EXPECT_NO_THROW(controlled::reference(header,"A2",0.));
}
TEST(ControlledFixture,TwentySecondIncrementalAsymmetricHistoryMatchesPreservedFullReplayOracle) {
 controlled::NominalHistory cached(hydro(),sha);full_replay_reference::NominalHistory oracle(hydro(),sha);
 constexpr int64_t origin=1000000000;size_t total_steps=0;double maximum_error=0.;
 for(int frame=1;frame<=1000;++frame) {
  const int64_t target=origin+20000000LL*frame;
  if(frame%10==0) {
   const uint64_t seq=uint64_t(frame/10);const double left=.15+.05*std::sin(.1*seq),right=.25+.04*std::cos(.2*seq);
   cached.add(target-3123456,0,left,seq);oracle.add(target-3123456,0,left,seq);
   cached.add(target-1654321,1,right,seq);oracle.add(target-1654321,1,right,seq);
  }
  const auto row=cached.state_at(origin,target,true);const auto &work=row["work"];
  EXPECT_EQ(work["ordinary_incremental"],true);EXPECT_EQ(work["rollback_ns"],0);
  EXPECT_EQ(work["integrated_ns"],20000000);EXPECT_LE(work["integration_steps"].get<size_t>(),12u);
  EXPECT_EQ(work["retained_channel_events"],2*(frame/10));total_steps+=row["integration_steps"].get<size_t>();
  if(frame%50==0) {
   const auto reference=oracle.state_at(origin,target,true);auto a=row["state"].get<std::array<double,6>>(),b=reference["state"].get<std::array<double,6>>();
   for(size_t k=0;k<6;++k)maximum_error=std::max(maximum_error,std::abs(a[k]-b[k]));
   EXPECT_EQ(row["held_events"],reference["held_events"]);
  }
 }
 EXPECT_LT(maximum_error,1e-9);EXPECT_LE(total_steps,12000u);EXPECT_GT(total_steps,9000u);
}
TEST(ControlledFixture,LateActualInputRollsBackCheckpointAndCorrectsFutureWithoutRewritingPast) {
 controlled::NominalHistory cached(hydro(),sha);full_replay_reference::NominalHistory oracle(hydro(),sha);constexpr int64_t origin=1000000000;
 cached.add(origin,0,.1,1);cached.add(origin,1,.1,1);oracle.add(origin,0,.1,1);oracle.add(origin,1,.1,1);
 cached.state_at(origin,origin+200000000,true);const auto past=cached.state_at(origin,origin+400000000,true);const auto saved_past=past.dump();
 cached.add(origin+350000000,0,.2,2);cached.add(origin+351000000,1,.05,2);
 oracle.add(origin+350000000,0,.2,2);oracle.add(origin+351000000,1,.05,2);
 const auto corrected=cached.state_at(origin,origin+420000000,true);const auto reference=oracle.state_at(origin,origin+420000000,true);
 EXPECT_EQ(corrected["work"]["cache_rewound"],true);EXPECT_EQ(corrected["work"]["integration_start_ns"],origin+200000000);
 EXPECT_EQ(corrected["work"]["rollback_ns"],200000000);EXPECT_EQ(corrected["work"]["late_channel_events_since_last_sensor"],2);
 EXPECT_EQ(corrected["held_events"],reference["held_events"]);EXPECT_EQ(past.dump(),saved_past);
 const auto a=corrected["state"].get<std::array<double,6>>(),b=reference["state"].get<std::array<double,6>>();
 for(size_t k=0;k<6;++k)EXPECT_NEAR(a[k],b[k],1e-9);
 const auto next=cached.state_at(origin,origin+440000000,true);EXPECT_EQ(next["work"]["ordinary_incremental"],true);EXPECT_EQ(next["work"]["integrated_ns"],20000000);
 EXPECT_EQ(next["held_events"].size(),4u);EXPECT_EQ(next["work"]["state_correction_count"],1);
}
TEST(ControlledFixture,EventExactlyAtCheckpointIsReplayedFromStrictlyEarlierCheckpoint) {
 controlled::NominalHistory cached(hydro(),sha);full_replay_reference::NominalHistory oracle(hydro(),sha);constexpr int64_t origin=1000000000;
 cached.state_at(origin,origin+20000000,true);cached.state_at(origin,origin+40000000,true);
 cached.add(origin+20000000,0,.2,1);oracle.add(origin+20000000,0,.2,1);
 const auto a=cached.state_at(origin,origin+60000000,true),b=oracle.state_at(origin,origin+60000000,true);
 EXPECT_EQ(a["work"]["integration_start_ns"],origin);EXPECT_EQ(a["held_events"],b["held_events"]);
 for(size_t k=0;k<6;++k)EXPECT_NEAR(a["state"][k].get<double>(),b["state"][k].get<double>(),1e-9);
}
TEST(ControlledFixture,QueryWorkCapIsTerminalAndDoesNotPretendToProduceAState) {
 controlled::NominalHistory cached(hydro(),sha);constexpr int64_t origin=1000000000;
 cached.state_at(origin,origin+20000000,true);
 EXPECT_ANY_THROW(cached.state_at(origin,origin+1100000000,true));
 EXPECT_ANY_THROW(cached.state_at(origin,origin+40000000,true));
}
TEST(ControlledFixture,LateInputBeyondReplayWorkBudgetIsExplicitFailure) {
 controlled::NominalHistory cached(hydro(),sha);constexpr int64_t origin=1000000000;
 for(int frame=1;frame<=100;++frame)cached.state_at(origin,origin+20000000LL*frame,true);
 cached.add(origin+10000000,0,.2,1);
 EXPECT_ANY_THROW(cached.state_at(origin,origin+2020000000LL,true));
}
} // namespace
