// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
// W1: the v4 diagnostic profile must be reachable only through its own scope,
// and the v3 frozen contract must keep its exact previous acceptance rules.
#include <gtest/gtest.h>
#include <fstream>
#include <sstream>
#include "p1_full_contract.hpp"

namespace {
std::string read_text(const std::string & p) {
  std::ifstream f(p);
  std::stringstream ss;
  ss << f.rdbuf();
  return ss.str();
}
}  // namespace

TEST(V4DiagnosticContract, DiagnosticProfileIsDistinctFromFrozen) {
  const auto text = read_text(P1_V4_CONTRACT);
  const auto c = p1::parse_unique_contract(text);
  EXPECT_EQ(p1::validate_contract_fields(c), p1::ContractProfile::DiagnosticExecute);
  EXPECT_NE(p1::validate_contract_fields(c), p1::ContractProfile::Frozen);
  EXPECT_TRUE(c.at("fault_injection_enabled").get<bool>());
  EXPECT_FALSE(c.at("execute_qualified").get<bool>());
  EXPECT_TRUE(c.at("parameters_are_diagnostic_only").get<bool>());
}

TEST(V4DiagnosticContract, DiagnosticProfilePermitsExecuteMode) {
  const auto c = p1::parse_unique_contract(read_text(P1_V4_CONTRACT));
  EXPECT_NO_THROW(p1::validate_contract_mode(c, "execute"));
  EXPECT_NO_THROW(p1::validate_contract_mode(c, "no_output"));
  EXPECT_THROW(p1::validate_contract_mode(c, "shadow"), std::runtime_error);
}

TEST(V4DiagnosticContract, FrozenProfileStillRejectsFaultInjection) {
  const auto text = read_text(P1_V3_CONTRACT);
  const auto c = p1::parse_unique_contract(text);
  EXPECT_EQ(p1::validate_contract_fields(c), p1::ContractProfile::Frozen);
  auto mutated = c;
  mutated["fault_injection_enabled"] = true;
  EXPECT_THROW(p1::validate_contract_fields(mutated), std::runtime_error);
}

TEST(V4DiagnosticContract, V4RejectsFrozenQualification) {
  auto c = p1::parse_unique_contract(read_text(P1_V4_CONTRACT));
  c["qualification"] = "execution_frozen";
  EXPECT_THROW(p1::validate_contract_fields(c), std::runtime_error);
}

TEST(V4DiagnosticContract, V4RequiresFaultInjectionEnabled) {
  auto c = p1::parse_unique_contract(read_text(P1_V4_CONTRACT));
  c["fault_injection_enabled"] = false;
  EXPECT_THROW(p1::validate_contract_fields(c), std::runtime_error);
}

TEST(V4DiagnosticContract, V4RejectsExecuteQualifiedTrue) {
  auto c = p1::parse_unique_contract(read_text(P1_V4_CONTRACT));
  c["execute_qualified"] = true;
  EXPECT_THROW(p1::validate_contract_fields(c), std::runtime_error);
}

TEST(V4DiagnosticContract, UnknownProfileIsStillRejected) {
  auto c = p1::parse_unique_contract(read_text(P1_V4_CONTRACT));
  c["supported_parameter_profile"] = "not_a_profile";
  EXPECT_THROW(p1::validate_contract_fields(c), std::runtime_error);
}
