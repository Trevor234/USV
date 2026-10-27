#include <gtest/gtest.h>
#include "witness_v2_c37_fixture.hpp"
#include <filesystem>
#include <fstream>
#include <iterator>
#include <unistd.h>

using namespace c37_witness_fixture;
static p1::WitnessSummary result(std::string_view mode) {
  p1::Witness w(true,header());populate(w,mode);return w.summary();
}
TEST(WitnessV2C37,AcceptedRealProducerBindsFirstActivation) {
  const auto s=result("accepted");EXPECT_TRUE(s.observation_complete);EXPECT_TRUE(s.business_ready_observed);
  EXPECT_TRUE(s.normal_contract_qualified);EXPECT_EQ(s.accepted_activations,1u);
}
TEST(WitnessV2C37,AllRejectedStillCompleteWithoutNormalBusiness) {
  const auto s=result("all_rejected");EXPECT_TRUE(s.observation_complete);EXPECT_FALSE(s.business_ready_observed);
  EXPECT_FALSE(s.normal_contract_qualified);EXPECT_EQ(s.accepted_activations,0u);
}
TEST(WitnessV2C37,LaterRejectedDoesNotEraseEarlierBoundReady) {
  const auto s=result("accepted_then_rejected");EXPECT_TRUE(s.observation_complete);
  EXPECT_TRUE(s.business_ready_observed);EXPECT_TRUE(s.normal_contract_qualified);EXPECT_EQ(s.activation.published,2u);
}
TEST(WitnessV2C37,AppendRejectionRetainsIncompleteEvidence) {
  const auto s=result("append_rejected");EXPECT_FALSE(s.observation_complete);EXPECT_TRUE(s.incomplete);
  EXPECT_FALSE(s.normal_contract_qualified);EXPECT_EQ(s.submit.rejected,1u);
}
TEST(WitnessV2C37,CapacityDropCannotQualifyNormal) {
  const auto s=result("overflow");EXPECT_FALSE(s.observation_complete);EXPECT_TRUE(s.overflow);
  EXPECT_FALSE(s.normal_contract_qualified);EXPECT_EQ(s.tick.overflow,1u);
}
TEST(WitnessV2C37,DisabledNeverCreatesEvidenceFile) {
  p1::Witness w(false,header());populate(w,"accepted");const auto s=w.summary();
  EXPECT_FALSE(s.enabled);EXPECT_FALSE(s.observation_complete);EXPECT_FALSE(s.business_ready_observed);
  EXPECT_FALSE(s.normal_contract_qualified);EXPECT_FALSE(w.write_terminal("/tmp/c37_disabled_should_never_be_created"));
}
TEST(WitnessV2C37,DuplicateSubmitIsRecordedButNotNormal) {
  const auto s=result("duplicate_submit");EXPECT_FALSE(s.observation_complete);EXPECT_TRUE(s.business_ready_observed);
  EXPECT_FALSE(s.normal_contract_qualified);
}
TEST(WitnessV2C37,MismatchedReadyIsNotBusinessReady) {
  const auto s=result("mismatched_ready");EXPECT_FALSE(s.observation_complete);
  EXPECT_FALSE(s.business_ready_observed);EXPECT_FALSE(s.normal_contract_qualified);
}
TEST(WitnessV2C37,DuplicateReadyCannotPickOneConvenientRow) {
  const auto s=result("duplicate_ready");EXPECT_FALSE(s.observation_complete);
  EXPECT_FALSE(s.business_ready_observed);EXPECT_FALSE(s.normal_contract_qualified);
}
TEST(WitnessV2C37,StartupReadinessNeverSubstitutesAcceptedActivation) {
  const auto s=result("startup_ready");EXPECT_FALSE(s.observation_complete);
  EXPECT_FALSE(s.business_ready_observed);EXPECT_FALSE(s.normal_contract_qualified);
}
TEST(WitnessV2C37,WrongReadyObservationDoesNotBind) {
  const auto s=result("wrong_ready_observation");EXPECT_FALSE(s.observation_complete);
  EXPECT_FALSE(s.business_ready_observed);EXPECT_FALSE(s.normal_contract_qualified);
}
TEST(WitnessV2C37,MissingReadyRetainsObservationOnly) {
  const auto s=result("missing_ready");EXPECT_TRUE(s.observation_complete);
  EXPECT_FALSE(s.business_ready_observed);EXPECT_FALSE(s.normal_contract_qualified);
}
TEST(WitnessV2C37,ClosePhaseMissingDoesNotGrantNormal) {
  const auto s=result("missing_close");EXPECT_FALSE(s.observation_complete);
  EXPECT_TRUE(s.business_ready_observed);EXPECT_FALSE(s.normal_contract_qualified);
}
TEST(WitnessV2C37,FailedTickRetainsRecordsWithoutNormalClaim) {
  const auto s=result("failed_tick");EXPECT_TRUE(s.observation_complete);
  EXPECT_TRUE(s.business_ready_observed);EXPECT_FALSE(s.normal_contract_qualified);
}
TEST(WitnessV2C37,SourceFailureCannotHideBehindAcceptedReady) {
  const auto s=result("source_failure");EXPECT_TRUE(s.observation_complete);
  EXPECT_TRUE(s.business_ready_observed);EXPECT_FALSE(s.normal_contract_qualified);
}
TEST(WitnessV2C37,HeaderInvalidationCannotBeOverwrittenByReady) {
  const auto s=result("header_invalid");EXPECT_FALSE(s.observation_complete);
  EXPECT_TRUE(s.business_ready_observed);EXPECT_FALSE(s.normal_contract_qualified);
}
TEST(WitnessV2C37,AfterCloseAppendRetainsFailure) {
  const auto s=result("after_close");EXPECT_FALSE(s.observation_complete);
  EXPECT_TRUE(s.incomplete);EXPECT_FALSE(s.normal_contract_qualified);
}
TEST(WitnessV2C37,TimeReversalDoesNotGrantNormal) {
  const auto s=result("reversed_ticks");EXPECT_FALSE(s.observation_complete);
  EXPECT_TRUE(s.business_ready_observed);EXPECT_FALSE(s.normal_contract_qualified);
}
TEST(WitnessV2C37,SecondReadyCannotReplaceFirstAcceptedBinding) {
  const auto s=result("different_first_accepted");EXPECT_FALSE(s.observation_complete);
  EXPECT_FALSE(s.business_ready_observed);EXPECT_FALSE(s.normal_contract_qualified);
}
TEST(WitnessV2C37,TerminalSchemaSeparatesFieldsAndIsCreateOnly) {
  std::string pattern="/tmp/c37_witness_native_XXXXXX";char *directory=::mkdtemp(pattern.data());ASSERT_NE(directory,nullptr);
  const std::filesystem::path path=std::filesystem::path(directory)/"witness.json";
  p1::Witness w(true,header());populate(w,"all_rejected");ASSERT_TRUE(w.write_terminal(path.c_str()));
  std::ifstream input(path);const std::string bytes{std::istreambuf_iterator<char>(input),{}};
  EXPECT_NE(bytes.find("\"schema\":\"p1-fixed-witness-v2\""),std::string::npos);
  EXPECT_NE(bytes.find("\"observation_complete\":true"),std::string::npos);
  EXPECT_NE(bytes.find("\"business_ready_observed\":false"),std::string::npos);
  EXPECT_NE(bytes.find("\"normal_contract_qualified\":false"),std::string::npos);
  EXPECT_EQ(bytes.find("\"audit_complete\""),std::string::npos);
  EXPECT_FALSE(w.write_terminal(path.c_str()));
  std::ifstream reread(path);const std::string preserved{std::istreambuf_iterator<char>(reread),{}};EXPECT_EQ(bytes,preserved);
  std::filesystem::remove_all(directory);
}
