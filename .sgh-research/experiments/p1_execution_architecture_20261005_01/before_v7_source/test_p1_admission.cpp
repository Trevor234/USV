// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#include <gtest/gtest.h>
#include "p1_admission.hpp"
#include "p1_clock_window.hpp"
#include "usv_mpc_cpp/p1_input_core.hpp"
namespace {p1::Ticket ticket(){p1::Ticket t;t.id=1;t.target=2;t.origin=1000000000;t.deadline=t.origin+p1::DEADLINE;t.target_ns=t.origin+p1::T;t.version={1,1,1,1,0};return t;}}
TEST(Deadline, EqualityRegistrationSurvivesEitherCutoffOrder){for(bool close_first:{true,false}){p1::Admission a;auto t=ticket();if(close_first)EXPECT_FALSE(a.cutoff(t.deadline));EXPECT_EQ(a.register_ready(t,1,t.deadline,t.version),"");EXPECT_TRUE(a.finalize_ready(t.id,t.deadline));EXPECT_FALSE(a.cutoff(t.deadline));EXPECT_TRUE(a.cutoff(t.deadline+1));EXPECT_FALSE(a.take(2,t.target_ns-1));EXPECT_TRUE(a.take(2,t.target_ns));EXPECT_FALSE(a.take(2,t.target_ns));}}
TEST(Deadline, BeforeAndAfterHaveDifferentResults){for(int64_t d:{-1,0,1}){p1::Admission a;auto t=ticket();EXPECT_EQ(a.register_ready(t,1,t.deadline+d,t.version),d<=0?"":"late");}}
TEST(Admission, WrongTargetDuplicateAndVersion){p1::Admission a;auto t=ticket();EXPECT_EQ(a.register_ready(t,2,t.deadline,t.version),"wrong_tick");auto old=t.version;old.task++;EXPECT_EQ(a.register_ready(t,1,t.deadline,old),"version_mismatch");EXPECT_EQ(a.register_ready(t,1,t.deadline,t.version),"");EXPECT_EQ(a.register_ready(t,1,t.deadline,t.version),"duplicate");}
TEST(Admission, ClearBetweenCutoffAndActivationInvalidates){p1::Admission a;auto t=ticket();EXPECT_EQ(a.register_ready(t,1,t.deadline,t.version),"");a.cutoff(t.deadline+1);a.invalidate();EXPECT_FALSE(a.take(2,t.target_ns));}
TEST(Admission, FixedCapacityAndMissedTickNeverRollsForward){p1::Admission a;auto t=ticket();a.register_ready(t,1,t.deadline,t.version);EXPECT_LE(a.slots(),2u);EXPECT_FALSE(a.take(3,t.target_ns+p1::T));EXPECT_FALSE(a.take(3,t.target_ns+2*p1::T));EXPECT_EQ(p1::due_tick(1000000000,1820000000),4u);}
TEST(Activation, SourceSequenceDoesNotReplaceStateAndVersionGate){p1::Limits l;p1::State predicted{},actual{};actual[0]=.1;EXPECT_EQ(p1::state_check(predicted,actual,l),"");actual[0]=.251;EXPECT_EQ(p1::state_check(predicted,actual,l),"activation_state_mismatch");actual[0]=0;predicted[2]=3.14;actual[2]=-3.14;EXPECT_EQ(p1::state_check(predicted,actual,l),"");actual[1]=NAN;EXPECT_EQ(p1::state_check(predicted,actual,l),"nonfinite");}
TEST(Anchor, PartialFailureIsUnknownAndRealPublishUpdatesCannotBeRolledBack){p1::Anchor a;a.known={true,true};a.n={10,10};a.seq={3,3};a.time={1000000000,1000000000};auto b=a;b.known[1]=false;EXPECT_EQ(p1::anchor_check(a,b),"unknown_anchor");b=a;b.seq[0]++;EXPECT_EQ(p1::anchor_check(a,b),"anchor_mismatch");}
TEST(Command, AmplitudeAndActualSteadySpacing){p1::Limits l;p1::Anchor a;a.known={true,true};a.time={1000000000,1000000000};EXPECT_EQ(p1::command_check({16,16},a,1200000000,l),"");EXPECT_EQ(p1::command_check({16.01,16},a,1200000000,l),"command_rate");EXPECT_EQ(p1::command_check({26,16},a,1400000000,l),"command_limit");}
TEST(Fallback, FifthMissRampsAndNeverInstantlyDropsLargeThrust){p1::Limits l;l.rho=10;l.hold_ns=600000000;p1::Anchor a;a.known={true,true};a.n={25,-25};a.time={1800000000,1800000000};auto out=p1::fallback(a,2000000000,1000000000,l,false);EXPECT_DOUBLE_EQ(out[0],23);EXPECT_DOUBLE_EQ(out[1],-23);EXPECT_EQ(p1::command_check(out,a,2000000000,l),"");a.time={1400000000,1400000000};EXPECT_EQ(p1::fallback(a,1500000000,1000000000,l,false),a.n);}
TEST(InputCore, EligibilityPreservesF5ReasonPriority){usv_mpc::InputEligibility c;EXPECT_EQ(usv_mpc::input_eligibility(c).second,"no_odom");c.odom_received=true;c.last_odom_s=1;c.now_s=3.001;c.odom_timeout_s=2;EXPECT_EQ(usv_mpc::input_eligibility(c).second,"odom_timeout");c.now_s=3;EXPECT_EQ(usv_mpc::input_eligibility(c).second,"no_path");c.path_received=true;c.path_size=2;c.require_fcu=true;EXPECT_EQ(usv_mpc::input_eligibility(c).second,"no_state");c.last_state_s=3;c.armed=true;c.mode="GUIDED";c.allowed_modes={"GUIDED"};EXPECT_TRUE(usv_mpc::input_eligibility(c).first);}
TEST(InputCore, NumericAndMixedRate){EXPECT_TRUE(usv_mpc::admit_odom({1,2,3,4,5},{0,0,0,1}));EXPECT_FALSE(usv_mpc::admit_odom({1,2,3,4,NAN},{0,0,0,1}));EXPECT_FALSE(usv_mpc::admit_odom({1,2,3,4,5},{0,0,0,0}));auto s=usv_mpc::compose_odom({1,2,3,4,5},{0,0,0,1});usv_mpc::compose_imu(s,.2);EXPECT_DOUBLE_EQ(s[3],3);EXPECT_DOUBLE_EQ(s[5],.2);EXPECT_FALSE(usv_mpc::admit_imu(INFINITY));}
TEST(InputCore, MappingMatchesDeclaredPhysicalClamp){auto u=usv_mpc::map_vrx({50,-50},1,-25,25,100);EXPECT_DOUBLE_EQ(u[0],25);EXPECT_DOUBLE_EQ(u[1],-25);u=usv_mpc::map_vrx({2,-3},2,-25,25,100);EXPECT_DOUBLE_EQ(u[0],4);EXPECT_DOUBLE_EQ(u[1],-6);}
TEST(InputCore, TargetReferenceIsRebuiltFromPredictedNearestPoint){usv_mpc::ReferenceInput r;for(int i=0;i<10;++i){r.path.push_back({double(i),0,0});r.profile.push_back({1,0,0,double(i)});}r.path_stamp={1,0};r.profile_stamp={1,0};usv_mpc::Vector6d s=usv_mpc::Vector6d::Zero();s[0]=3;usv_mpc::ReferenceMetadata m;auto ref=usv_mpc::build_frozen_reference(s,r,20,.2,2,.6,&m);EXPECT_EQ(m.nearest_index,3);EXPECT_EQ(m.start_index,5);EXPECT_DOUBLE_EQ(m.profile_t0,5);EXPECT_NEAR(ref(0,0),5,1e-12);EXPECT_NEAR(ref(0,1),5.2,1e-12);EXPECT_NEAR(ref(3,0),1,1e-12);}
TEST(InputCore, PublisherHistoryAndTargetTimeHaveIndependentAnalyticFixture){usv_mpc::HydroParams h;h.Xu=h.Xuu=0;h.Yv=h.Yr=h.Nv=h.Nr=h.Yvv=h.Yrr=h.Nvv=h.Nrr=0;h.xg=0;usv_mpc::Vector6d s=usv_mpc::Vector6d::Zero();s[3]=1;EXPECT_TRUE(usv_mpc::propagate_publisher_nominal(s,0,200000000,{0,0},{},h));EXPECT_NEAR(s[0],.2,1e-12);EXPECT_NEAR(s[3],1,1e-12);EXPECT_FALSE(usv_mpc::propagate_publisher_nominal(s,200000000,0,{0,0},{},h));}

TEST(Deadline, RegistrationCompletionAfterDeadlineRetractsSlot){p1::Admission a;auto t=ticket();EXPECT_EQ(a.register_ready(t,1,t.deadline-1,t.version),"");EXPECT_FALSE(a.finalize_ready(t.id,t.deadline+1));EXPECT_FALSE(a.take(t.target,t.target_ns));}

// P1_SOURCE_SIM_AGE_GATE_V2: independent integer fixtures, no ROS-time assumption.
TEST(SourceTime, ReceiveAgeAndPhysicalLagAreIndependent){
  p1::SourceAgeLimits l;const int64_t now=1000000000,sim=2000000000;
  EXPECT_EQ(p1::state_source_check(now,sim,now,{sim-100000001,now},{},false,l),"odom_sim_lag");
  EXPECT_EQ(p1::state_source_check(now,sim,now,{sim,now-100000001},{},false,l),"odom_receive_stale");
  EXPECT_EQ(p1::state_source_check(now,sim,now,{sim,now-100000000},{},false,l),"");
}
TEST(SourceTime, LagAndFutureLimitsAreInclusive){
  const int64_t now=1000000000,sim=2000000000;
  for(int64_t delta:{-1,0,1}){
    EXPECT_EQ(p1::source_time_check(now,sim,now,{sim-100000000-delta,now},100000000,100000000,20000000),delta<=0?"":"sim_lag");
    EXPECT_EQ(p1::source_time_check(now,sim,now,{sim+20000000+delta,now},100000000,100000000,20000000),delta<=0?"":"sim_future");
  }
}
TEST(SourceTime, PhysicalNowExtrapolatesClockToCommitAtOneToOne){
  const int64_t clock_receive=1000000000,now=1050000000,sim=2000000000;
  EXPECT_EQ(p1::source_time_check(now,sim,clock_receive,{1950000000,now},100000000,100000000,20000000),"");
  EXPECT_EQ(p1::source_time_check(now,sim,clock_receive,{1949999999,now},100000000,100000000,20000000),"sim_lag");
  EXPECT_EQ(p1::source_time_check(now,sim,clock_receive,{2070000001,now},100000000,100000000,20000000),"sim_future");
}
TEST(SourceTime, OnlyMixedStateUsesImuPhysicalAge){
  p1::SourceAgeLimits l;const int64_t now=1000000000,sim=2000000000;
  EXPECT_EQ(p1::state_source_check(now,sim,now,{sim,now},{sim-100000001,now},false,l),"");
  EXPECT_EQ(p1::state_source_check(now,sim,now,{sim,now},{sim-100000001,now},true,l),"imu_sim_lag");
  EXPECT_EQ(p1::state_source_check(now,sim,now,{sim,now},{sim+20000001,now},true,l),"imu_sim_future");
  EXPECT_EQ(p1::state_source_check(now,sim,now,{sim,now},{sim,now-100000001},true,l),"imu_receive_stale");
}
TEST(SourceTime, InvalidChronologyAndExtrapolationOverflowAreRejected){
  EXPECT_EQ(p1::source_time_check(1000,2000,1000,{2000,1001},100,100,20),"receive_future");
  EXPECT_EQ(p1::source_time_check(1000,2000,1001,{2000,1000},100,100,20),"clock_anchor_invalid");
  EXPECT_EQ(p1::source_time_check(1000,2000,1000,{2000,0},100,100,20),"time_invalid");
  const int64_t maximum=std::numeric_limits<int64_t>::max();
  EXPECT_EQ(p1::source_time_check(1002,maximum-1,1000,{maximum,1002},100,100,20),"clock_extrapolation_overflow");
}

TEST(ClockWindow, HighRateClockRetainsRequiredDurationAtFiniteCapacity){
  for(int64_t spacing:{20000000,4000000,2000000,500000}){
    p1::ClockWindow w;p1::RtfEstimate e;
    for(int64_t t=0;t<=1000000000;t+=spacing){
      e=w.observe(1000000000+t,2000000000+t,.95,1.05);
      EXPECT_LE(e.stored_samples,p1::ClockWindow::capacity);
      EXPECT_LE(e.span_ns,p1::ClockWindow::max_span_ns);
      if(t>=p1::ClockWindow::min_span_ns){EXPECT_TRUE(e.valid);EXPECT_DOUBLE_EQ(e.value,1);}
    }
  }
}
TEST(ClockWindow, DurationAndRealtimeRatioBoundariesAreInclusive){
  p1::ClockWindow w;w.observe(1000000000,0,.95,1.05);
  EXPECT_FALSE(w.observe(1399999999,399999999,.95,1.05).valid);
  EXPECT_TRUE(w.observe(1400000000,400000000,.95,1.05).valid);
  for(double ratio:{.949,.95,1.05,1.051}){
    w.reset();w.observe(1000000000,0,.95,1.05);
    const auto e=w.observe(1400000000,static_cast<int64_t>(ratio*400000000),.95,1.05);
    EXPECT_EQ(e.valid,ratio>=.95&&ratio<=1.05);
  }
}
TEST(ClockWindow, RepeatedSimulationTimeCannotKeepPreviousValidRatio){
  p1::ClockWindow w;p1::RtfEstimate e;
  for(int64_t t=0;t<=1000000000;t+=4000000)e=w.observe(1000000000+t,2000000000+t,.95,1.05);
  ASSERT_TRUE(e.valid);
  for(int64_t t=4000000;t<=600000000;t+=4000000)e=w.observe(2000000000+t,3000000000,.95,1.05);
  EXPECT_FALSE(e.valid);EXPECT_DOUBLE_EQ(e.value,0);
}
TEST(ClockWindow, ReceiveGapRemovesStaleValidityAndNeedsNewCoverage){
  p1::ClockWindow w;w.observe(1000000000,0,.95,1.05);
  ASSERT_TRUE(w.observe(1400000000,400000000,.95,1.05).valid);
  auto e=w.observe(2100000000,1100000000,.95,1.05);
  EXPECT_FALSE(e.valid);EXPECT_EQ(e.span_ns,0);EXPECT_EQ(e.stored_samples,1u);
  EXPECT_TRUE(w.observe(2500000000,1500000000,.95,1.05).valid);
}
TEST(ClockWindow, ResetBackwardJumpAndDuplicateReceiveRequireFreshWindow){
  for(int mode=0;mode<4;++mode){
    p1::ClockWindow w;w.observe(1000000000,0,.95,1.05);
    ASSERT_TRUE(w.observe(1400000000,400000000,.95,1.05).valid);
    if(mode==0)w.reset();
    const int64_t receive=mode==3?1400000000:1500000000;
    const int64_t sim=mode==1?0:mode==2?6000000000:500000000;
    auto e=w.observe(receive,sim,.95,1.05);
    EXPECT_FALSE(e.valid);EXPECT_EQ(e.span_ns,0);EXPECT_EQ(e.stored_samples,1u);
    EXPECT_TRUE(w.observe(receive+400000000,sim+400000000,.95,1.05).valid);
  }
}
TEST(ClockWindow, InvalidInputsAndBurstsCannotClaimEstablishedAlignment){
  p1::ClockWindow w;
  EXPECT_FALSE(w.observe(0,0,.95,1.05).valid);
  EXPECT_FALSE(w.observe(1000000000,-1,.95,1.05).valid);
  EXPECT_FALSE(w.observe(1000000000,0,NAN,1.05).valid);
  EXPECT_FALSE(w.observe(1000000000,0,1.05,.95).valid);
  for(int64_t t=0;t<100000000;t+=1000){
    auto e=w.observe(1000000000+t,t,.95,1.05);
    EXPECT_FALSE(e.valid);EXPECT_LE(e.stored_samples,11u);
  }
}
