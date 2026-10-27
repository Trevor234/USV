#include <gtest/gtest.h>
#include "p1_full_contract.hpp"
using Json=nlohmann::json;
namespace {
Json pre(){auto c=p1::candidate_baseline();c.erase("diagnostic_contract_revision");c["schema"]="p1-execution-contract-v3";c["qualification"]="execution_pre_freeze";c["fault_injection_enabled"]=false;c["execution_contract_revision"]=1;c["resource_contract_revision"]=1;c["supported_parameter_profile"]=p1::contract_parameter_profile;c["freeze_evidence_sha256"]="";return c;}
Json frozen(){auto c=pre();c["qualification"]="execution_frozen";c["execute_qualified"]=true;c["parameters_are_diagnostic_only"]=false;c["pending_final_calibration"]=Json::array();c["freeze_evidence_sha256"]=std::string(64,'a');return c;}
}
TEST(P1FullContract,DiagnosticModesRetainExplicitExecuteRejection){auto c=p1::candidate_baseline();
EXPECT_NO_THROW(p1::validate_contract_mode(c,"no_output"));
EXPECT_NO_THROW(p1::validate_contract_mode(c,"shadow"));
EXPECT_THROW(p1::validate_contract_mode(c,"execute"),std::runtime_error);}
TEST(P1FullContract,FormalPreFreezeHasIndependentResourceVersion){auto c=pre();
EXPECT_NO_THROW(p1::validate_contract_fields(c));
EXPECT_NO_THROW(p1::require_runtime_contract_mode(c,"no_output"));
EXPECT_THROW(p1::validate_contract_mode(c,"shadow"),std::runtime_error);
EXPECT_THROW(p1::validate_contract_mode(c,"execute"),std::runtime_error);}
TEST(P1FullContract,FrozenSchemaCannotSelfAuthorizePhysicalStartup){auto c=frozen();
EXPECT_NO_THROW(p1::validate_contract_mode(c,"execute"));
EXPECT_NO_THROW(p1::validate_contract_mode(c,"no_output"));try{p1::require_runtime_contract_mode(c,"execute");FAIL();}catch(const std::runtime_error & e){
EXPECT_NE(std::string(e.what()).find("B5/M4"),std::string::npos);}EXPECT_FALSE(p1::physical_execute_release_enabled);}
TEST(P1FullContract,EveryTopLevelFieldIsRequired){for(const auto & baseline:{p1::candidate_baseline(),pre()})for(auto it=baseline.begin();it!=baseline.end();++it){auto c=baseline;c.erase(it.key());
EXPECT_THROW(p1::validate_contract_fields(c),std::runtime_error)<<it.key();}}
TEST(P1FullContract,UnknownOrMixedRevisionsReject){auto c=pre();c["diagnostic_contract_revision"]=5;
EXPECT_THROW(p1::validate_contract_fields(c),std::runtime_error);c=pre();c["execution_contract_revision"]=2;
EXPECT_THROW(p1::validate_contract_fields(c),std::runtime_error);c=pre();c["resource_contract_revision"]=true;
EXPECT_THROW(p1::validate_contract_fields(c),std::runtime_error);}
TEST(P1FullContract,BoolsFloatsAndInt64OverflowAreNotIntegerBounds){for(const auto & field:p1::integer_contract_fields()){if(!p1::candidate_baseline().contains(field))continue;for(const Json bad:{Json(true),Json(100000000.0),Json(uint64_t(-1))}){auto c=p1::candidate_baseline();c[field]=bad;
EXPECT_THROW(p1::validate_contract_fields(c),std::runtime_error)<<field;}}}
TEST(P1FullContract,NonfiniteAndArrayShapeReject){auto c=pre();c["dt"]=std::numeric_limits<double>::infinity();
EXPECT_THROW(p1::validate_contract_fields(c),std::runtime_error);c=pre();c["Q"][0]=true;
EXPECT_THROW(p1::validate_contract_fields(c),std::runtime_error);c=pre();c["activation_tolerance"].erase(0);
EXPECT_THROW(p1::validate_contract_fields(c),std::runtime_error);}
TEST(P1FullContract,FixedNominalAndCommandProfileRejectDrift){for(const auto & key:{"rho_n_s","command_max_n","map_scale","T_ns","deadline_ns","reference_start_offset"}){auto c=pre();c[key]=999;
EXPECT_THROW(p1::validate_contract_fields(c),std::runtime_error)<<key;}auto c=pre();c["hydro"]["mass"]=15.;
EXPECT_THROW(p1::validate_contract_fields(c),std::runtime_error);}
TEST(P1FullContract,FormalFlagsFaultsAndEvidenceMarkersAreChecked){auto c=pre();c["execute_qualified"]=true;
EXPECT_THROW(p1::validate_contract_fields(c),std::runtime_error);c=pre();c["fault_injection_enabled"]=true;
EXPECT_THROW(p1::validate_contract_fields(c),std::runtime_error);c=frozen();c["freeze_evidence_sha256"]="pending";
EXPECT_THROW(p1::validate_contract_fields(c),std::runtime_error);c=frozen();c["pending_final_calibration"].push_back("rho");
EXPECT_THROW(p1::validate_contract_fields(c),std::runtime_error);}
TEST(P1FullContract,ResourceDomainPreservedWithoutClaimingCoverage){auto c=pre();c["history_capacity"]=1;c["log_capacity"]=1;c["max_job_bytes"]=6460;c["max_candidate_bytes"]=8204;
EXPECT_NO_THROW(p1::validate_contract_fields(c));c["max_job_bytes"]=6459;
EXPECT_THROW(p1::validate_contract_fields(c),std::runtime_error);}
TEST(P1FullContract,DuplicateKeysRejectAtAllObjectDepths){
EXPECT_THROW(p1::parse_unique_contract("{\"schema\":1,\"schema\":2}"),std::runtime_error);
EXPECT_THROW(p1::parse_unique_contract("{\"hydro\":{\"mass\":1,\"mass\":2}}"),std::runtime_error);
EXPECT_NO_THROW(p1::parse_unique_contract(p1::candidate_baseline().dump()));}
TEST(P1FullContract,EmptyOversizeAndInvalidNumericJsonReject){
EXPECT_THROW(p1::parse_unique_contract(""),std::runtime_error);
EXPECT_THROW(p1::parse_unique_contract(std::string(65537,' ')),std::runtime_error);
EXPECT_ANY_THROW(p1::parse_unique_contract("{\"value\":1e309}"));}
