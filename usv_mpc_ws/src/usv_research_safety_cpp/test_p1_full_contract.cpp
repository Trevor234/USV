#include <gtest/gtest.h>

#include <array>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <limits>
#include <set>
#include <string_view>
#include <unistd.h>

#include "p1_full_contract.hpp"
#include "p1_sys_utils.hpp"
#include "usv_nmpc/mpc_solver.hpp"
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
TEST(P1FullContract,BoolsFloatsAndInt64OverflowAreNotIntegerBounds){for(const auto & field:p1::integer_contract_fields()){if(!p1::candidate_baseline().contains(field))continue;for(const Json & bad:{Json(true),Json(100000000.0),Json(uint64_t(-1))}){auto c=p1::candidate_baseline();c[field]=bad;
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

// 受控仿真合同必须显式声明 controlled_sim_faults_enabled（布尔），
// 否则闭环刺激就没有门控，等于默认允许注入。
TEST(P1FullContract, ControlledSimRequiresTheFaultsFlag) {
  auto sim = p1::candidate_baseline();
  sim["schema"] = "p1-execution-contract-v2-sim";
  sim["qualification"] = "controlled_sim";
  sim["fault_injection_enabled"] = true;
  // 未声明：拒绝。
  sim.erase("controlled_sim_faults_enabled");
  EXPECT_THROW(p1::validate_contract_fields(sim), std::runtime_error);
  // 声明为非布尔：拒绝。
  sim["controlled_sim_faults_enabled"] = "yes";
  EXPECT_THROW(p1::validate_contract_fields(sim), std::runtime_error);
  // 声明为布尔：通过。
  sim["controlled_sim_faults_enabled"] = true;
  EXPECT_NO_THROW(p1::validate_contract_fields(sim));
}

namespace {

Json controlled_sim() {
  auto sim = p1::candidate_baseline();
  sim["schema"] = "p1-execution-contract-v2-sim";
  sim["qualification"] = "controlled_sim";
  sim["controlled_sim_faults_enabled"] = false;
  return sim;
}

class ContractFile {
 public:
  explicit ContractFile(const Json & contract) : text_(contract.dump()) {
    auto pattern = (std::filesystem::temp_directory_path() / "p1-contract-XXXXXX").string();
    const int fd = mkstemp(pattern.data());
    if (fd == -1) throw std::runtime_error("cannot create test contract");
    close(fd);
    path_ = std::move(pattern);
    std::ofstream output(path_);
    output << text_;
    output.close();
    if (!output) throw std::runtime_error("cannot write test contract");
  }

  ~ContractFile() {
    std::error_code ignored;
    std::filesystem::remove(path_, ignored);
  }

  const std::string & path() const { return path_; }
  std::string hash() const { return p1::digest(text_); }

 private:
  std::string text_;
  std::string path_;
};

TEST(P1FullContract, ControlledSimLoadRejectsMissingCoreFields) {
  for (const auto * key : {"hydro", "Q", "command_min_n", "activation_tolerance",
                          "odom_age_ns", "expected_imu_frame", "input_topics",
                          "worker_failure_policy", "execute_qualified", "history_capacity"}) {
    SCOPED_TRACE(key);
    auto sim = controlled_sim();
    sim.erase(key);
    const ContractFile file(sim);
    EXPECT_THROW(p1::load_verified_contract(file.path(), file.hash(), "controlled_sim"),
      std::runtime_error);
    EXPECT_THROW(p1::load_contract(file.path(), file.hash()), std::runtime_error);
  }
}

TEST(P1FullContract, ControlledSimRejectsWrongTypesShapesAndBounds) {
  struct BadValue {
    const char * key;
    Json value;
  };
  const BadValue cases[] = {
    {"hydro", {{"mass", 14.2}}},
    {"Q", {20, 20, 50}},
    {"R", {0.05, -0.1}},
    {"rho_n_s", 0},
    {"activation_tolerance", {0.25, 0.25, 0.15, 0.0, 0.2, 0.15}},
    {"odom_age_ns", 1.0},
    {"imu_sim_lag_ns", -1},
    {"reference_start_offset", std::numeric_limits<int>::max()},
    {"reference_start_offset", std::uint64_t(std::numeric_limits<int>::max()) + 1},
    {"deadline_ns", 200'000'001},
    {"rtf_low", 1.1},
    {"recording_ready_timeout_ns", 60'000'000'001LL},
    {"expected_imu_frame", ""},
    {"fault_injection_enabled", "true"},
    {"execute_qualified", true},
    {"history_capacity", 257},
  };
  for (const auto & bad : cases) {
    SCOPED_TRACE(bad.key);
    auto sim = controlled_sim();
    sim[bad.key] = bad.value;
    EXPECT_THROW(p1::validate_contract_fields(sim), std::runtime_error);
  }
  auto sim = controlled_sim();
  sim["hydro"]["Nrr"] = std::numeric_limits<double>::quiet_NaN();
  EXPECT_THROW(p1::validate_contract_fields(sim), std::runtime_error);
}

TEST(P1FullContract, VerifiedSimRetainsRawContractAndDecodesTunableParameters) {
  auto sim = controlled_sim();
  sim["hydro"]["mass"] = 15.0;
  sim["hydro"]["Yr_dot"] = -0.25;
  sim["Q"][0] = 22.0;
  sim["R"][1] = 0.075;
  sim["Rd"][0] = 0.3;
  sim["Qf_scale"] = 9;
  sim["command_min_n"] = -23;
  sim["command_max_n"] = 21;
  sim["backend_rate_n_s"] = 70;
  sim["odom_age_ns"] = 123'000'000;
  sim["history_capacity"] = 8;

  const ContractFile file(sim);
  const auto loaded = p1::load_verified_contract(file.path(), file.hash(), "controlled_sim");
  ASSERT_EQ(loaded.profile, p1::ContractProfile::ControlledSim);
  EXPECT_EQ(loaded.raw, sim);
  EXPECT_EQ(p1::load_contract(file.path(), file.hash()), sim);
  EXPECT_THROW(p1::load_verified_contract(file.path(), file.hash(), "execute"), std::runtime_error);
  EXPECT_THROW(p1::load_verified_contract(file.path(), std::string(64, '0'), "controlled_sim"),
    std::runtime_error);

  const auto & spec = loaded.spec;
  EXPECT_EQ(spec.identity.schema, sim.at("schema").get<std::string>());
  EXPECT_EQ(spec.identity.diagnostic_contract_revision, 5);
  EXPECT_EQ(spec.timing.odom_age_ns, 123'000'000);
  EXPECT_EQ(spec.resources.history_capacity, 8u);
  EXPECT_EQ(spec.topics.input_topics.odom, sim.at("input_topics").at("odom").get<std::string>());
  EXPECT_TRUE(spec.faults.fault_injection_enabled);
  EXPECT_FALSE(spec.faults.faults_enabled(loaded.profile));

  const auto params = p1::solver_params(spec);
  const auto legacy = p1::solver_params(loaded.raw);
  EXPECT_EQ(params.N, 20);
  EXPECT_DOUBLE_EQ(params.dt, 0.2);
  EXPECT_DOUBLE_EQ(params.hydro.mass, 15.0);
  EXPECT_DOUBLE_EQ(params.hydro.Yr_dot, -0.25);
  EXPECT_DOUBLE_EQ(params.Q_diag[0], 22.0);
  EXPECT_DOUBLE_EQ(params.R_diag[1], 0.075);
  EXPECT_DOUBLE_EQ(params.Rd_diag[0], 0.3);
  EXPECT_DOUBLE_EQ(params.Qf_scale, 9.0);
  EXPECT_DOUBLE_EQ(params.T_min, -23.0);
  EXPECT_DOUBLE_EQ(params.T_max, 21.0);
  EXPECT_DOUBLE_EQ(params.dT_max, 70.0);
  EXPECT_EQ(params.Q_diag, legacy.Q_diag);
  EXPECT_EQ(params.R_diag, legacy.R_diag);
  EXPECT_EQ(params.Rd_diag, legacy.Rd_diag);
  EXPECT_DOUBLE_EQ(params.hydro.Yr_dot, legacy.hydro.Yr_dot);
}

TEST(P1FullContract, ControlledSimFaultPermissionUsesOnlyTheSimFlag) {
  auto sim = controlled_sim();
  sim["fault_injection_enabled"] = false;
  sim["controlled_sim_faults_enabled"] = true;
  const ContractFile file(sim);
  const auto loaded = p1::load_verified_contract(file.path(), file.hash(), "controlled_sim");
  EXPECT_FALSE(loaded.spec.faults.fault_injection_enabled);
  EXPECT_TRUE(loaded.spec.faults.faults_enabled(loaded.profile));
}

void expect_same_resources(const p1::ResourceLimits & actual, const p1::ResourceLimits & expected) {
  EXPECT_EQ(actual.max_job_bytes, expected.max_job_bytes);
  EXPECT_EQ(actual.max_candidate_bytes, expected.max_candidate_bytes);
  EXPECT_EQ(actual.history_capacity, expected.history_capacity);
  EXPECT_EQ(actual.max_path_points, expected.max_path_points);
  EXPECT_EQ(actual.max_profile_rows, expected.max_profile_rows);
  EXPECT_EQ(actual.log_capacity, expected.log_capacity);
  EXPECT_EQ(actual.dds_depth, expected.dds_depth);
  EXPECT_EQ(actual.max_profile_dims, expected.max_profile_dims);
  EXPECT_EQ(actual.max_profile_label_bytes, expected.max_profile_label_bytes);
  EXPECT_EQ(actual.max_path_frame_bytes, expected.max_path_frame_bytes);
}

auto hydro_values(const usv_mpc::HydroParams & h) {
  return std::array{h.mass, h.Iz, h.xg, h.d_thruster, h.Xu_dot, h.Yv_dot, h.Yr_dot, h.Nv_dot,
    h.Nr_dot, h.Xu, h.Yv, h.Yr, h.Nv, h.Nr, h.Xuu, h.Yvv, h.Yrr, h.Nvv, h.Nrr};
}

void expect_same_mpc(const usv_mpc::MpcParams & actual, const usv_mpc::MpcParams & expected) {
  EXPECT_EQ(actual.N, expected.N);
  EXPECT_EQ(actual.dt, expected.dt);
  EXPECT_EQ(actual.Q_diag, expected.Q_diag);
  EXPECT_EQ(actual.R_diag, expected.R_diag);
  EXPECT_EQ(actual.Rd_diag, expected.Rd_diag);
  EXPECT_EQ(actual.Qf_scale, expected.Qf_scale);
  EXPECT_EQ(actual.T_min, expected.T_min);
  EXPECT_EQ(actual.T_max, expected.T_max);
  EXPECT_EQ(actual.dT_max, expected.dT_max);
  EXPECT_EQ(hydro_values(actual.hydro), hydro_values(expected.hydro));
}

TEST(P1FullContract, CompactAndFullV4ContractsMatchLegacyProfiles) {
  using Profile = p1::ContractProfile;
  const struct {
    const char * name;
    Profile profile;
    Json legacy;
    Json extra;
    std::set<std::string> modes;
  } cases[] = {
    {"diagnostic", Profile::Diagnostic, p1::candidate_baseline(), Json::object(), {"no_output", "shadow"}},
    {"controlled_sim", Profile::ControlledSim, controlled_sim(), {{"faults", {{"enabled", false}}}},
      {"controlled_sim"}},
    {"pre_freeze", Profile::PreFreeze, pre(), Json::object(), {"no_output"}},
    {"frozen", Profile::Frozen, frozen(), {{"identity", {{"freeze_evidence_sha256", std::string(64, 'a')}}}},
      {"no_output", "execute"}},
  };
  for (const auto & test : cases) {
    SCOPED_TRACE(test.name);
    const ContractFile legacy_file(test.legacy);
    const auto legacy = p1::load_verified_contract(legacy_file.path(), legacy_file.hash());
    ASSERT_EQ(legacy.profile, test.profile);

    auto minimal = test.extra;
    minimal["schema"] = "p1-contract-v4";
    minimal["profile"] = test.name;
    EXPECT_EQ(p1::to_v4_contract_json(legacy.spec, test.profile), minimal);

    const auto full = p1::to_v4_contract_json(legacy.spec, test.profile, false);
    for (const auto * section : {"identity", "mpc", "actuator", "timing", "topics", "resources"}) {
      ASSERT_TRUE(full.contains(section));
      for (const auto & item : full.at(section).items()) {
        SCOPED_TRACE(item.key());
        EXPECT_EQ(item.value(), test.legacy.at(item.key()));
      }
    }
    for (const auto & v4 : {minimal, full}) {
      const ContractFile file(v4);
      const auto actual = p1::load_verified_contract(file.path(), file.hash());
      EXPECT_EQ(actual.profile, test.profile);
      EXPECT_EQ(actual.raw, v4);
      EXPECT_EQ(p1::load_contract(file.path(), file.hash()), v4);
      EXPECT_EQ(p1::to_v4_contract_json(actual.spec, actual.profile, false), full);
      EXPECT_EQ(actual.spec.identity.schema, legacy.spec.identity.schema);
      EXPECT_EQ(actual.spec.identity.qualification, legacy.spec.identity.qualification);
      EXPECT_EQ(actual.spec.faults.execute_qualified, legacy.spec.faults.execute_qualified);
      EXPECT_EQ(actual.spec.faults.parameters_are_diagnostic_only,
        legacy.spec.faults.parameters_are_diagnostic_only);
      EXPECT_EQ(actual.spec.faults.fault_injection_enabled, legacy.spec.faults.fault_injection_enabled);
      EXPECT_EQ(actual.spec.faults.controlled_sim_faults_enabled,
        legacy.spec.faults.controlled_sim_faults_enabled);
      expect_same_resources(actual.spec.resources, legacy.spec.resources);
      expect_same_resources(p1::resource_limits_from_contract(v4), legacy.spec.resources);
      expect_same_mpc(p1::solver_params(actual.spec), p1::solver_params(legacy.spec));
      expect_same_mpc(p1::solver_params(v4), p1::solver_params(test.legacy));

      for (const auto * mode : {"controlled_sim", "no_output", "shadow", "execute", "unknown"}) {
        SCOPED_TRACE(mode);
        if (test.modes.count(mode)) {
          EXPECT_NO_THROW(p1::validate_contract_mode(test.legacy, mode));
          EXPECT_NO_THROW(p1::validate_contract_mode(v4, mode));
          EXPECT_NO_THROW(p1::load_verified_contract(file.path(), file.hash(), mode));
        } else {
          EXPECT_THROW(p1::validate_contract_mode(test.legacy, mode), std::runtime_error);
          EXPECT_THROW(p1::validate_contract_mode(v4, mode), std::runtime_error);
          EXPECT_THROW(p1::load_verified_contract(file.path(), file.hash(), mode), std::runtime_error);
        }
        if (test.modes.count(mode) && std::string_view(mode) != "execute") {
          EXPECT_NO_THROW(p1::require_runtime_contract_mode(test.legacy, mode));
          EXPECT_NO_THROW(p1::require_runtime_contract_mode(v4, mode));
        } else {
          EXPECT_THROW(p1::require_runtime_contract_mode(test.legacy, mode), std::runtime_error);
          EXPECT_THROW(p1::require_runtime_contract_mode(v4, mode), std::runtime_error);
        }
      }
    }
  }
}

TEST(P1FullContract, V4ControlledSimMergesPartialOverridesAndPreservesDefaults) {
  const Json compact = {
    {"schema", "p1-contract-v4"}, {"profile", "controlled_sim"}, {"faults", {{"enabled", true}}},
    {"mpc", {{"hydro", {{"mass", 15.0}}}}},
    {"timing", {{"odom_age_ns", 123'000'000}}},
    {"topics", {{"input_topics", {{"path", "/sim/reference"}}}}},
    {"resources", {{"history_capacity", 12}}},
  };
  auto legacy = controlled_sim();
  legacy["controlled_sim_faults_enabled"] = true;
  legacy["hydro"]["mass"] = 15.0;
  legacy["odom_age_ns"] = 123'000'000;
  legacy["input_topics"]["path"] = "/sim/reference";
  legacy["history_capacity"] = 12;

  const ContractFile file(compact);
  const ContractFile legacy_file(legacy);
  const auto actual = p1::load_verified_contract(file.path(), file.hash(), "controlled_sim");
  const auto expected = p1::load_verified_contract(legacy_file.path(), legacy_file.hash(), "controlled_sim");
  EXPECT_TRUE(actual.spec.faults.faults_enabled(actual.profile));
  EXPECT_EQ(actual.spec.mpc.hydro.mass, 15.0);
  EXPECT_EQ(actual.spec.timing.odom_age_ns, 123'000'000);
  EXPECT_EQ(actual.spec.timing.imu_age_ns, p1::candidate_baseline().at("imu_age_ns").get<std::int64_t>());
  EXPECT_EQ(actual.spec.topics.input_topics.path, "/sim/reference");
  EXPECT_EQ(actual.spec.topics.input_topics.odom, expected.spec.topics.input_topics.odom);
  EXPECT_EQ(actual.spec.resources.history_capacity, 12u);
  expect_same_resources(actual.spec.resources, expected.spec.resources);
  expect_same_mpc(p1::solver_params(actual.spec), p1::solver_params(expected.spec));
  EXPECT_EQ(p1::to_v4_contract_json(actual.spec, actual.profile), compact);
  EXPECT_EQ(p1::to_v4_contract_json(expected.spec, expected.profile), compact);
}

TEST(P1FullContract, V4RejectsInvalidKeysTypesConstantsAndTuning) {
  const Json valid = {
    {"schema", "p1-contract-v4"}, {"profile", "controlled_sim"}, {"faults", {{"enabled", false}}},
  };
  const struct {
    const char * pointer;
    Json value;
  } cases[] = {
    {"/extra", true},
    {"/mpc/foo", 1},
    {"/topics/bar", 1},
    {"/mpc/hydro/baz", 1},
    {"/topics/input_topics/baz", 1},
    {"/resources/foo", 1},
    {"/faults/execute_qualified", false},
    {"/identity/qualification", "controlled_sim"},
    {"/identity/clock", "CLOCK_REALTIME"},
    {"/identity/diagnostic_contract_revision", 6},
    {"/identity/diagnostic_contract_revision", 5.0},
    {"/identity/worker_failure_policy", "continue"},
    {"/profile", "production"},
    {"/profile", 1},
    {"/faults/enabled", 1},
    {"/mpc/N", 15},
    {"/mpc/N", 20.0},
    {"/mpc/hydro", Json::array()},
    {"/mpc/hydro/mass", std::numeric_limits<double>::infinity()},
    {"/mpc/hydro/mass", -1},
    {"/mpc/reference_start_offset", std::numeric_limits<int>::max()},
    {"/mpc/Q", {1, 2}},
    {"/timing/deadline_ns", 100},
    {"/timing/odom_age_ns", 123.0},
    {"/timing/odom_age_ns", std::numeric_limits<std::uint64_t>::max()},
    {"/timing/rtf_low", 2.0},
    {"/actuator/rho_n_s", 0},
    {"/actuator", false},
    {"/topics/input_topics/path", ""},
    {"/topics/expected_imu_frame", std::string(129, 'x')},
    {"/resources", nullptr},
    {"/resources/history_capacity", 257},
    {"/resources/history_capacity", 0},
    {"/resources/history_capacity", 1.0},
    {"/resources/dds_depth", 2},
    {"/resources/job_cdr_max_bytes", 6459},
  };
  for (const auto & test : cases) {
    SCOPED_TRACE(test.pointer);
    auto contract = valid;
    contract[Json::json_pointer(test.pointer)] = test.value;
    EXPECT_THROW(p1::validate_contract_fields(contract), std::runtime_error);
  }
  for (const auto * key : {"profile", "faults"}) {
    auto contract = valid;
    contract.erase(key);
    EXPECT_THROW(p1::validate_contract_fields(contract), std::runtime_error) << key;
  }
  auto contract = valid;
  contract["faults"] = Json::object();
  EXPECT_THROW(p1::validate_contract_fields(contract), std::runtime_error);
  EXPECT_THROW(p1::parse_unique_contract(
    R"({"schema":"p1-contract-v4","profile":"diagnostic","profile":"pre_freeze"})"), std::runtime_error);
  EXPECT_THROW(p1::parse_unique_contract(
    R"({"schema":"p1-contract-v4","profile":"controlled_sim","mpc":{"hydro":{"mass":14,"mass":15}}})"),
    std::runtime_error);
}

TEST(P1FullContract, V4DiagnosticAndFormalProfilesEnforceQualification) {
  for (const auto * profile : {"diagnostic", "pre_freeze", "frozen"}) {
    SCOPED_TRACE(profile);
    Json contract = {{"schema", "p1-contract-v4"}, {"profile", profile}};
    if (std::string_view(profile) == "frozen") {
      EXPECT_THROW(p1::validate_contract_fields(contract), std::runtime_error);
      contract["identity"]["freeze_evidence_sha256"] = std::string(64, 'g');
      EXPECT_THROW(p1::validate_contract_fields(contract), std::runtime_error);
      contract["identity"]["freeze_evidence_sha256"] = std::string(64, 'a');
      auto pending = contract;
      pending["identity"]["pending_final_calibration"] = {"rho"};
      EXPECT_THROW(p1::validate_contract_fields(pending), std::runtime_error);
      EXPECT_NO_THROW(p1::validate_contract_mode(contract, "execute"));
      try {
        p1::require_runtime_contract_mode(contract, "execute");
        FAIL() << "frozen contract unexpectedly enabled physical execute";
      } catch (const std::runtime_error & error) {
        EXPECT_NE(std::string_view(error.what()).find("B5/M4"), std::string_view::npos);
      }
    }
    EXPECT_NO_THROW(p1::validate_contract_fields(contract));
    auto drift = contract;
    drift["mpc"]["hydro"]["mass"] = 15;
    EXPECT_THROW(p1::validate_contract_fields(drift), std::runtime_error);
    drift = contract;
    drift["mpc"]["Q"] = {21, 20, 50, 8, 1, 8};
    EXPECT_THROW(p1::validate_contract_fields(drift), std::runtime_error);

    contract["faults"]["enabled"] = true;
    if (std::string_view(profile) == "diagnostic") {
      EXPECT_NO_THROW(p1::validate_contract_fields(contract));
      contract["faults"]["enabled"] = false;
      const ContractFile file(contract);
      const auto loaded = p1::load_verified_contract(file.path(), file.hash(), "shadow");
      EXPECT_FALSE(loaded.spec.faults.faults_enabled(loaded.profile));
      EXPECT_EQ(p1::to_v4_contract_json(loaded.spec, loaded.profile), contract);
    } else {
      EXPECT_THROW(p1::validate_contract_fields(contract), std::runtime_error);
      contract["faults"]["enabled"] = false;
      EXPECT_NO_THROW(p1::validate_contract_fields(contract));
    }
  }
}

}  // namespace
