// SPDX-License-Identifier: MIT
#include "controlled_protocol.hpp"
#include <gtest/gtest.h>
#include <std_msgs/msg/string.hpp>
#include <rclcpp/serialization.hpp>
#include <rclcpp/serialized_message.hpp>
namespace {
using Json=p1_owned::Json;using Decision=usv_research_interfaces::msg::ExecutionDecision;using Applied=usv_research_interfaces::msg::AppliedControl;
const std::string hash(64,'a');
Json identity(){return {{"run_id","controlled-owner"},{"producer_instance_id","controlled-owner:1"},{"baseline_id",controlled::baseline}};}
Decision decision(){Decision d;d.sequence=3;d.tick=7;d.tick_planned_ns=1000000000;d.schema_version="p1-execution-decision-v2";d.run_id="observer";d.boot_id=p1_owned::boot_id();d.contract_hash=hash;d.mode="shadow";d.diagnostic_only=true;d.activation_commit_ns=d.tick_planned_ns+1;d.tick_end_ns=d.tick_planned_ns+2;return d;}
Applied applied(){Applied a;a.sequence=4;a.cycle_sequence=3;a.run_id="controlled-owner";a.producer_instance_id="controlled-owner:1";a.baseline_id=controlled::baseline;a.left_publish_success=a.right_publish_success=true;a.left_publish_start_steady_ns=1000000003;a.left_publish_end_steady_ns=1000000004;a.right_publish_start_steady_ns=1000000005;a.right_publish_end_steady_ns=1000000006;return a;}
TEST(ControlledOwner,ModesAreExplicitFiniteDomain){EXPECT_TRUE(controlled::mode_valid("A2"));
 EXPECT_TRUE(controlled::mode_valid("B"));
 EXPECT_TRUE(controlled::mode_valid("C"));
 EXPECT_FALSE(controlled::mode_valid("A"));
 EXPECT_FALSE(controlled::mode_valid(""));}
TEST(ControlledOwner,ActualPhaseHasExactlySeventeenKeys){auto p=controlled::phase(identity(),hash,decision(),applied(),1000000007);
 EXPECT_EQ(p.size(),17u);
 EXPECT_EQ(p["schema"],"p1-controlled-owner-phase-v1");
 EXPECT_EQ(p["baseline_id"],controlled::baseline);
 EXPECT_EQ(p["stage_qualified"],false);
 EXPECT_EQ(p["execute_qualified"],false);}
TEST(ControlledOwner,ActualCommandAndIndividualPublicationTimesAreRetained){auto a=applied();a.final_n={.1,.2};auto p=controlled::phase(identity(),hash,decision(),a,1000000007);
 EXPECT_EQ(p["command_n"],Json::array({.1,.2}));
 EXPECT_EQ(p["start_ns"],Json::array({1000000003,1000000005}));
 EXPECT_EQ(p["end_ns"],Json::array({1000000004,1000000006}));
 EXPECT_EQ(p["applied_sequence"],4);
 EXPECT_EQ(p["decision_sequence"],3);
 EXPECT_EQ(p["held_until_ns"],1200000000);}
TEST(ControlledOwner,PhaseCannotPrecedePhysicalReturn){EXPECT_ANY_THROW(controlled::phase(identity(),hash,decision(),applied(),1000000005));}
TEST(ControlledOwner,PartialFailureCannotEmitPhase){auto a=applied();a.right_publish_success=false;
 EXPECT_ANY_THROW(controlled::phase(identity(),hash,decision(),a,1000000007));}
TEST(ControlledOwner,ReorderedChannelCallsCannotEmitPhase){auto a=applied();a.right_publish_start_steady_ns=a.left_publish_end_steady_ns-1;
 EXPECT_ANY_THROW(controlled::phase(identity(),hash,decision(),a,1000000007));}
TEST(ControlledOwner,PhaseMustMeetUnchangedObserverFreezeBudget){EXPECT_NO_THROW(controlled::phase(identity(),hash,decision(),applied(),1149999999));
 EXPECT_ANY_THROW(controlled::phase(identity(),hash,decision(),applied(),1150000000));}
TEST(ControlledOwner,NoF5BaselineBorrowing){auto a=applied();a.baseline_id="F5_20261005_atomic_freeze_01";
 EXPECT_ANY_THROW(controlled::phase(identity(),hash,decision(),a,1000000007));}
TEST(ControlledOwner,ExactDecisionCorrelationRequired){auto a=applied();a.cycle_sequence=2;
 EXPECT_ANY_THROW(controlled::phase(identity(),hash,decision(),a,1000000007));}
TEST(ControlledOwner,NonfiniteCommandCannotEmitPhase){auto a=applied();a.final_n[0]=std::numeric_limits<double>::quiet_NaN();
 EXPECT_ANY_THROW(controlled::phase(identity(),hash,decision(),a,1000000007));}
TEST(ControlledOwner,DecisionHasActualRunContractClockAndFiniteCommandDomain){auto d=decision();
 EXPECT_TRUE(controlled::decision_domain(d,"observer",hash,1000000003));d.final_n[0]=std::numeric_limits<double>::infinity();
 EXPECT_FALSE(controlled::decision_domain(d,"observer",hash,1000000003));d=decision();
 EXPECT_FALSE(controlled::decision_domain(d,"foreign",hash,1000000003));}
TEST(ControlledOwner,PulseRequiresRealFreezeAndPredeclaredOffset){usv_research_interfaces::msg::SolveJob j;j.schema_version="p1-solve-job-v1";j.run_id="observer";j.boot_id=p1_owned::boot_id();j.contract_hash=hash;j.job_id=1;j.tick_origin_steady_ns=1000000000;j.freeze_steady_ns=1000000001;j.target_steady_ns=1200000000;
 EXPECT_TRUE(controlled::job_domain(j,"observer",hash,1000000002));
 EXPECT_FALSE(controlled::job_domain(j,"observer",hash,1100000000));
 EXPECT_FALSE(controlled::job_domain(j,"foreign",hash,1000000002));}
TEST(ControlledOwner,PhaseStringSurvivesActualRosCdr){auto p=controlled::phase(identity(),hash,decision(),applied(),1000000007);std_msgs::msg::String m;m.data=p.dump();rclcpp::Serialization<std_msgs::msg::String> codec;rclcpp::SerializedMessage bytes;codec.serialize_message(&m,&bytes);std_msgs::msg::String decoded;codec.deserialize_message(&bytes,&decoded);
 EXPECT_EQ(decoded,m);
 EXPECT_EQ(Json::parse(decoded.data),p);}
} // namespace
