#include <gtest/gtest.h>
#include <rclcpp/serialization.hpp>
#include <rclcpp/serialized_message.hpp>
#include <nav_msgs/msg/path.hpp>
#include <std_msgs/msg/float64_multi_array.hpp>
#include <usv_research_interfaces/msg/solve_job.hpp>
#include <usv_research_interfaces/msg/solve_candidate.hpp>
#include <usv_research_interfaces/msg/worker_capability.hpp>
#include "p1_resources.hpp"
using Job=usv_research_interfaces::msg::SolveJob;
using Candidate=usv_research_interfaces::msg::SolveCandidate;
using Capability=usv_research_interfaces::msg::WorkerCapability;
using Json=nlohmann::json;
static Json contract(){return {{"diagnostic_contract_revision",5},{"resource_policy",p1::resource_policy_v1},{"resource_budget_scope",p1::resource_cdr_encoding_v1},{"job_cdr_max_bytes",6460},{"candidate_cdr_max_bytes",8204},{"max_job_bytes",8192},{"max_candidate_bytes",16384},{"history_capacity",256},{"max_path_points",2048},{"max_profile_rows",2048},{"log_capacity",512},{"dds_depth",1},{"max_profile_dims",4},{"max_profile_label_bytes",64},{"max_path_frame_bytes",128}};}
static Job maximum(){Job j;j.schema_version=std::string(64,'a');j.run_id=std::string(128,'a');j.boot_id=j.contract_hash=j.nominal_hash=j.worker_instance=std::string(64,'a');j.anchor_source=std::string(32,'a');j.anchor_producer=std::string(64,'a');j.anchor_run_id=std::string(128,'a');j.history_sim_ns.resize(256);j.history_channel.resize(256);j.history_n.resize(256);return j;}
template<class M>static size_t serialized(const M & m){rclcpp::Serialization<M> serializer;rclcpp::SerializedMessage raw;serializer.serialize_message(&m,&raw);return raw.get_rcl_serialized_message().buffer_length;}
TEST(Resources, InstalledSerializationAtFullJobAndCandidateBoundary){auto j=maximum();
  EXPECT_EQ(serialized(j),p1::max_job_cdr_bytes());
  EXPECT_EQ(serialized(j),6460u);Candidate c;c.job=j;c.worker_instance=std::string(64,'w');c.reason=std::string(256,'r');c.backend=std::string(16,'b');
  EXPECT_EQ(serialized(c),p1::max_candidate_cdr_bytes());
  EXPECT_EQ(serialized(c),8204u);
  EXPECT_TRUE(p1::check_candidate_resources(c,p1::ResourceLimits{}));}
TEST(Resources, ActualSizeMatchesSerializationAcrossPaddingAndHistory){for(size_t n:{0,1,2,255,256}){auto j=maximum();j.run_id.resize(n%129);j.anchor_source.resize(n%33);j.history_sim_ns.resize(n);j.history_channel.resize(n);j.history_n.resize(n);
  EXPECT_EQ(serialized(j),p1::job_cdr_bytes(j));Candidate c;c.job=j;c.reason=std::string(n%257,'r');
  EXPECT_EQ(serialized(c),p1::candidate_cdr_bytes(c));}}
TEST(Resources, EveryJobStringAllowsBoundaryAndRejectsOneByteOver){std::array<std::pair<std::string Job::*,size_t>,9> fields{{{&Job::schema_version,64},{&Job::run_id,128},{&Job::boot_id,64},{&Job::contract_hash,64},{&Job::nominal_hash,64},{&Job::worker_instance,64},{&Job::anchor_source,32},{&Job::anchor_producer,64},{&Job::anchor_run_id,128}}};for(auto field:fields){Job j;j.*field.first=std::string(field.second,'a');
  EXPECT_TRUE(p1::check_job_resources(j,{}));j.*field.first+='a';auto c=p1::check_job_resources(j,{});
  EXPECT_FALSE(c);
  EXPECT_EQ(c.observed,field.second+1);
  EXPECT_EQ(c.limit,field.second);}}
TEST(Resources, EveryCandidateStringRejectsOverLimitBeforeCopy){for(auto field:std::array<std::pair<std::string Candidate::*,size_t>,3>{{{&Candidate::worker_instance,64},{&Candidate::reason,256},{&Candidate::backend,16}}}){Candidate c;c.*field.first=std::string(field.second,'a');
  EXPECT_TRUE(p1::check_candidate_resources(c,{}));c.*field.first+='a';
  EXPECT_FALSE(p1::check_candidate_resources(c,{}));}Candidate c;c.job.run_id=std::string(129,'x');
  EXPECT_FALSE(p1::check_candidate_resources(c,{}));}
TEST(Resources, EveryCapabilityStringRejectsOverLimit){for(auto field:std::array<std::pair<std::string Capability::*,size_t>,10>{{{&Capability::schema_version,64},{&Capability::run_id,128},{&Capability::boot_id,64},{&Capability::contract_hash,64},{&Capability::nominal_hash,64},{&Capability::worker_instance,64},{&Capability::clock_name,32},{&Capability::backend,16},{&Capability::matrix_layout,32},{&Capability::reason,256}}}){Capability c;c.*field.first=std::string(field.second,'a');
  EXPECT_TRUE(p1::check_capability_resources(c));c.*field.first+='a';
  EXPECT_FALSE(p1::check_capability_resources(c));}}
TEST(Resources, Utf8ReasonUsesBytes){Candidate c;for(int i=0;i<85;++i)c.reason+=u8"船";
  EXPECT_EQ(c.reason.size(),255u);
  EXPECT_TRUE(p1::check_candidate_resources(c,{}));c.reason+=u8"船";
  EXPECT_EQ(c.reason.size(),258u);
  EXPECT_FALSE(p1::check_candidate_resources(c,{}));}
TEST(Resources, HistoryUsesContractCapacityAndDoesNotReplaceShapeGate){auto j=maximum();p1::ResourceLimits r;r.history_capacity=1;
  EXPECT_FALSE(p1::check_job_resources(j,r));j.history_sim_ns.resize(1);j.history_channel.resize(1);j.history_n.resize(1);
  EXPECT_TRUE(p1::check_job_resources(j,r));j.history_n.resize(0);
  EXPECT_TRUE(p1::check_job_resources(j,r));}
TEST(Resources, ContractMustBeIntegralAndWithinHardCaps){for(auto key:{"history_capacity","max_path_points","max_profile_rows","log_capacity","dds_depth","max_job_bytes","max_candidate_bytes","max_profile_dims","max_profile_label_bytes","max_path_frame_bytes","job_cdr_max_bytes","candidate_cdr_max_bytes","diagnostic_contract_revision"}){auto c=contract();c.erase(key);
  EXPECT_THROW(p1::resource_limits_from_contract(c),std::runtime_error);for(auto bad:std::vector<Json>{true,1.0,"1",nullptr,0,-1,18446744073709551615ULL}){c=contract();c[key]=bad;
  EXPECT_THROW(p1::resource_limits_from_contract(c),std::runtime_error);}c=contract();c[key]=c[key].get<int>()+1;
  EXPECT_THROW(p1::resource_limits_from_contract(c),std::runtime_error);}}
TEST(Resources, ByteBudgetExactTypeMaximumIsAllowedButOneLessRejected){auto c=contract();c["max_job_bytes"]=6460;c["max_candidate_bytes"]=8204;
  EXPECT_NO_THROW(p1::resource_limits_from_contract(c));c["max_job_bytes"]=6459;
  EXPECT_THROW(p1::resource_limits_from_contract(c),std::runtime_error);c=contract();c["max_candidate_bytes"]=8203;
  EXPECT_THROW(p1::resource_limits_from_contract(c),std::runtime_error);}
TEST(Resources, ContractPoliciesAreExact){for(auto key:{"resource_policy","resource_budget_scope"}){auto c=contract();c[key]="undeclared";
  EXPECT_THROW(p1::resource_limits_from_contract(c),std::runtime_error);}}
TEST(Resources, SmallerCacheDoesNotShrinkWireSchemaBudget){auto c=contract();c["history_capacity"]=1;c["max_job_bytes"]=6460;auto r=p1::resource_limits_from_contract(c);
  EXPECT_EQ(r.history_capacity,1u);
  EXPECT_EQ(r.max_job_bytes,6460u);}
TEST(Resources, PathMetadataBoundaryAndCountRejection){nav_msgs::msg::Path p;p.header.frame_id=std::string(128,'x');p.poses.resize(2048);
  EXPECT_TRUE(p1::check_path_resources(p,{}));p.header.frame_id+='x';
  EXPECT_FALSE(p1::check_path_resources(p,{}));p.header.frame_id="map";p.poses.resize(2049);
  EXPECT_FALSE(p1::check_path_resources(p,{}));}
TEST(Resources, ProfileDimensionsLabelsAndDataBoundaries){std_msgs::msg::Float64MultiArray p;p.layout.dim.resize(4);for(auto & d:p.layout.dim)d.label=std::string(64,'x');p.data.resize(8192);
  EXPECT_TRUE(p1::check_profile_resources(p,{}));p.layout.dim.back().label+='x';
  EXPECT_FALSE(p1::check_profile_resources(p,{}));p.layout.dim.back().label="stamp_nanosec:0";p.layout.dim.resize(5);
  EXPECT_FALSE(p1::check_profile_resources(p,{}));p.layout.dim.resize(4);p.data.resize(8193);
  EXPECT_FALSE(p1::check_profile_resources(p,{}));}
TEST(Resources, ExistingProducerLayoutsRemainAllowedIncludingClear){std_msgs::msg::Float64MultiArray p;for(auto label:{"points","v_kappa_r_t","stamp_sec:2147483647","stamp_nanosec:999999999"}){std_msgs::msg::MultiArrayDimension d;d.label=label;p.layout.dim.push_back(d);}p.data={.6,0.,0.,0.};
  EXPECT_TRUE(p1::check_profile_resources(p,{}));p.data.clear();
  EXPECT_TRUE(p1::check_profile_resources(p,{}));nav_msgs::msg::Path path;path.header.frame_id="map";
  EXPECT_TRUE(p1::check_path_resources(path,{}));}
