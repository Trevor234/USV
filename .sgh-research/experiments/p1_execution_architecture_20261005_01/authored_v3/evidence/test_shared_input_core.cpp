// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
// Public fixture code. The private F5 oracle is generated and retained only
// on the ROS host from a SHA-bound backup, never copied to this workspace.
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <string>
#include <utility>
#include <vector>
#include <gtest/gtest.h>
#include "usv_mpc_cpp/p1_input_core.hpp"
#include "f5_input_oracle.hpp"

namespace
{
using usv_mpc::InputEligibility;
using usv_mpc::ReferenceInput;
using usv_mpc::ReferenceMetadata;
using usv_mpc::Vector6d;

void same_metadata(const ReferenceMetadata & a, const ReferenceMetadata & b)
{
  EXPECT_EQ(a.horizon_steps, b.horizon_steps);
  EXPECT_DOUBLE_EQ(a.prediction_dt, b.prediction_dt);
  EXPECT_EQ(a.path_received_sequence, b.path_received_sequence);
  EXPECT_EQ(a.profile_received_sequence, b.profile_received_sequence);
  EXPECT_EQ(a.path_stamp_ns, b.path_stamp_ns);
  EXPECT_EQ(a.profile_stamp_ns, b.profile_stamp_ns);
  EXPECT_EQ(a.profile_stamp_known, b.profile_stamp_known);
  EXPECT_EQ(a.path_size, b.path_size);
  EXPECT_EQ(a.profile_size, b.profile_size);
  EXPECT_EQ(a.nearest_index, b.nearest_index);
  EXPECT_EQ(a.start_index, b.start_index);
  EXPECT_EQ(a.configured_start_offset, b.configured_start_offset);
  EXPECT_EQ(a.effective_start_offset, b.effective_start_offset);
  EXPECT_EQ(a.reference_mode, b.reference_mode);
  EXPECT_EQ(a.profile_sync_reason, b.profile_sync_reason);
  EXPECT_EQ(a.profile_synced, b.profile_synced);
  EXPECT_EQ(a.profile_t0_known, b.profile_t0_known);
  EXPECT_DOUBLE_EQ(a.profile_t0, b.profile_t0);
}

ReferenceInput straight()
{
  ReferenceInput input;
  input.path_stamp = {100, 21};
  input.profile_stamp = input.path_stamp;
  input.path_sequence = 17;
  input.profile_sequence = 19;
  for (int i = 0; i < 41; ++i) {
    double x = 0.5 * i;
    input.path.push_back({x, 0.0, 0.0});
    input.profile.push_back({0.8, 12.0, 0.1, x / 0.8});
  }
  return input;
}

usv_mpc::HydroParams analytic_hydro()
{
  usv_mpc::HydroParams h;
  h.mass = 2.0; h.Iz = 3.0; h.xg = 0.0; h.d_thruster = 0.25;
  h.Xu_dot = 0.0; h.Yv_dot = 0.0; h.Yr_dot = 0.0;
  h.Nv_dot = 0.0; h.Nr_dot = 0.0;
  h.Xu = 0.0; h.Yv = 0.0; h.Yr = 0.0; h.Nv = 0.0; h.Nr = 0.0;
  h.Xuu = 0.0; h.Yvv = 0.0; h.Yrr = 0.0; h.Nvv = 0.0; h.Nrr = 0.0;
  return h;
}

TEST(P1SharedInputCore, F5ReferenceAndEveryMetadataFieldMatchSameBoundedFixtures)
{
  auto base = straight();
  std::vector<ReferenceInput> cases{base};
  auto changed = base;
  changed.profile_stamp.first++;
  cases.push_back(changed);
  changed = base; changed.profile.pop_back(); cases.push_back(changed);
  changed = base; changed.profile.clear(); cases.push_back(changed);
  changed = base; changed.profile_stamp = {-1, -1}; cases.push_back(changed);
  changed = base; changed.path_stamp = {-1, -1}; cases.push_back(changed);
  changed = base; changed.profile_stamp = {-1, -1}; changed.path_stamp = {-1, -1};
  cases.push_back(changed);
  changed = base; changed.path.clear(); cases.push_back(changed);
  changed = base; changed.path.resize(1); changed.profile.resize(1); cases.push_back(changed);
  changed = base;
  for (size_t i = 0; i < changed.path.size(); ++i) {
    changed.path[i][1] = 0.05 * i * i;
    changed.path[i][2] = i % 2 ? -3.12 : 3.12;
    changed.profile[i][0] = 0.6 + 0.01 * i;
    changed.profile[i][2] = -0.2 + 0.01 * i;
  }
  cases.push_back(changed);
  for (size_t c = 0; c < cases.size(); ++c) {
    SCOPED_TRACE(c);
    for (int n : {2, 20}) {
      for (int offset : {-2, 0, 1, 2, 3, 10}) {
        for (double x : {0.0, 0.1, 0.3, 3.5, 30.0}) {
          Vector6d state; state << x, 0.2, -3.1, 0.9, 0.1, -0.2;
          usv_mpc::F5ReferenceOracle old(cases[c], n, 0.2, offset, 0.6);
          ReferenceMetadata old_meta, new_meta;
          const auto expected = old.build_reference(state, &old_meta);
          const auto actual = usv_mpc::build_frozen_reference(
            state, cases[c], n, 0.2, offset, 0.6, &new_meta);
          ASSERT_EQ(actual.rows(), expected.rows());
          ASSERT_EQ(actual.cols(), expected.cols());
          EXPECT_TRUE(actual.isApprox(expected, 0.0));
          same_metadata(old_meta, new_meta);
          const auto without_metadata = usv_mpc::build_frozen_reference(
            state, cases[c], n, 0.2, offset, 0.6, nullptr);
          EXPECT_TRUE(without_metadata.isApprox(expected, 0.0));
          if (!cases[c].path.empty()) {
            EXPECT_EQ(old.cached_synced(), new_meta.profile_synced);
            EXPECT_EQ(old.cached_reason(), new_meta.profile_sync_reason);
          }
        }
      }
    }
  }
}

TEST(P1SharedInputCore, F5EligibilityOrderAndStrictTimeoutBoundaryMatch)
{
  InputEligibility c;
  c.odom_received = true; c.path_received = true; c.path_size = 3;
  c.now_s = 20.0; c.last_odom_s = 19.0; c.odom_timeout_s = 1.0;
  c.last_state_s = 19.0; c.state_timeout_s = 1.0;
  c.require_fcu = true; c.armed = true; c.mode = "GUIDED";
  c.allowed_modes = {"GUIDED", "AUTO"};
  std::vector<InputEligibility> cases{c};
  auto add = [&](const InputEligibility & v) {cases.push_back(v);};
  auto v = c; v.odom_received = false; add(v);
  v = c; v.now_s = std::nextafter(20.0, 21.0); add(v);
  v = c; v.path_received = false; add(v);
  v = c; v.path_size = 0; add(v);
  v = c; v.path_size = 1; add(v);
  v = c; v.last_state_s = 0.0; add(v);
  v = c; v.last_state_s = std::nextafter(19.0, 18.0); add(v);
  v = c; v.armed = false; add(v);
  v = c; v.mode = "MANUAL"; add(v);
  v = c; v.allowed_modes.clear(); v.mode = "MANUAL"; add(v);
  v = c; v.require_fcu = false; v.armed = false; v.last_state_s = 0; add(v);
  v = c; v.odom_timeout_s = 0; v.state_timeout_s = 0; v.now_s = 1000; add(v);
  v = c; v.odom_received = false; v.path_received = false; v.armed = false; add(v);
  v = c; v.path_received = false; v.last_state_s = 0; add(v);
  for (size_t i = 0; i < cases.size(); ++i) {
    SCOPED_TRACE(i);
    const usv_mpc::F5EligibilityOracle old(cases[i]);
    EXPECT_EQ(usv_mpc::input_eligibility(cases[i]), old.can_solve());
  }
  EXPECT_TRUE(usv_mpc::input_eligibility(c).first);
  v = c; v.now_s = std::nextafter(20.0, 21.0);
  EXPECT_EQ(usv_mpc::input_eligibility(v).second, "odom_timeout");
}

TEST(P1SharedInputCore, F5OdomFiniteQuaternionAdmissionAndCompositionMatch)
{
  const std::array<double, 5> original{2.0, 3.0, 4.0, 0.5, 0.3};
  std::vector<std::array<double, 4>> quats{{0, 0, 0, 1}, {0, 0, 1, 0},
    {0, 0, 0.7071067811865476, 0.7071067811865476}, {0, 0, 0, 0},
    {0, 0, 0, 0.000001}, {0, 0, 0, 0.0000009}, {0, 0, 1.4, 1.4},
    {std::numeric_limits<double>::infinity(), 0, 0, 1},
    {0, std::numeric_limits<double>::quiet_NaN(), 0, 1},
    {1e200, 0, 0, 1}};
  std::vector<std::array<double, 5>> samples{original};
  for (size_t j = 0; j < original.size(); ++j) {
    auto bad = original; bad[j] = std::numeric_limits<double>::quiet_NaN();
    samples.push_back(bad);
    bad[j] = std::numeric_limits<double>::infinity(); samples.push_back(bad);
  }
  for (const auto & sample : samples) {
    for (const auto & q : quats) {
      const bool accepted = usv_mpc::f5_admit_odom(sample, q);
      EXPECT_EQ(usv_mpc::admit_odom(sample, q), accepted);
      if (accepted) {
        const auto expected = usv_mpc::f5_compose_odom(sample, q);
        const auto actual = usv_mpc::compose_odom(sample, q);
        EXPECT_TRUE(actual.isApprox(expected, 0.0));
        EXPECT_DOUBLE_EQ(actual[3], sample[2]);
        EXPECT_DOUBLE_EQ(actual[4], sample[3]);
      }
    }
  }
}

TEST(P1SharedInputCore, ImuLastProcessedOverwriteAndOdomRestorationMatchF5Math)
{
  const std::array<double, 5> a{2, 3, 4, 0.5, 0.3};
  const std::array<double, 4> q{0, 0, 0.7071067811865476, 0.7071067811865476};
  auto state = usv_mpc::compose_odom(a, q);
  auto expected = usv_mpc::f5_compose_odom(a, q);
  ASSERT_TRUE(usv_mpc::admit_imu(-0.7));
  usv_mpc::compose_imu(state, -0.7);
  expected[5] = -0.7;
  EXPECT_TRUE(state.isApprox(expected, 0.0));
  EXPECT_DOUBLE_EQ(state[3], 4.0); EXPECT_DOUBLE_EQ(state[4], 0.5);
  EXPECT_FALSE(usv_mpc::admit_imu(std::numeric_limits<double>::quiet_NaN()));
  EXPECT_FALSE(usv_mpc::admit_imu(std::numeric_limits<double>::infinity()));
  state = usv_mpc::compose_odom(a, q);
  EXPECT_TRUE(state.isApprox(usv_mpc::f5_compose_odom(a, q), 0.0));
  EXPECT_DOUBLE_EQ(state[5], 0.3);
}

TEST(P1SharedInputCore, F5VrxScaleAndIntersectedClampMatch)
{
  for (double scale : {0.5, 1.0, 2.0}) {
    for (double bound : {10.0, 25.0, 100.0}) {
      for (double left : {-100.0, -25.0, -8.0, 0.0, 25.0, 100.0}) {
        const Eigen::Vector2d command(left, -left + 1.0);
        const auto expected = usv_mpc::f5_map_vrx(command, scale, -25.0, 25.0, bound);
        const auto actual = usv_mpc::map_vrx(command, scale, -25.0, 25.0, bound);
        EXPECT_TRUE(actual.isApprox(expected, 0.0));
        // The legacy wrapper passes the already-intersected limits.
        const auto wrapped = usv_mpc::map_vrx(command, scale,
          std::max(-25.0, -bound), std::min(25.0, bound), bound);
        EXPECT_TRUE(wrapped.isApprox(expected, 0.0));
      }
    }
  }
}

TEST(P1SharedInputCore, FuturePublisherPropagationAndReferenceReanchorHaveAnalyticOracle)
{
  Vector6d state; state << 0.1, 0.0, 0.0, 0.8, 0.0, 0.0;
  const auto current = state;
  const int64_t from = 10000000000LL, target = from + 200000000;
  ASSERT_TRUE(usv_mpc::propagate_publisher_nominal(state, from, target,
    Eigen::Vector2d(1.0, 1.0), {}, analytic_hydro()));
  // mass=2, no damping, symmetric thrust 2 N -> acceleration exactly 1 m/s2.
  EXPECT_NEAR(state[0], 0.28, 1e-12); EXPECT_NEAR(state[3], 1.0, 1e-12);
  EXPECT_NEAR(state[1], 0.0, 1e-12); EXPECT_NEAR(state[2], 0.0, 1e-12);
  auto input = straight();
  ReferenceMetadata now_meta, future_meta;
  const auto now_ref = usv_mpc::build_frozen_reference(current, input, 20, 0.2, 2, 0.6, &now_meta);
  const auto future_ref = usv_mpc::build_frozen_reference(state, input, 20, 0.2, 2, 0.6, &future_meta);
  EXPECT_EQ(now_meta.nearest_index, 0); EXPECT_EQ(now_meta.start_index, 2);
  EXPECT_DOUBLE_EQ(now_meta.profile_t0, 1.25);
  EXPECT_EQ(future_meta.nearest_index, 1); EXPECT_EQ(future_meta.start_index, 3);
  EXPECT_DOUBLE_EQ(future_meta.profile_t0, 1.875);
  for (int k = 0; k <= 20; ++k) {
    EXPECT_NEAR(future_ref(0, k), 1.5 + 0.16 * k, 1e-12);
    EXPECT_DOUBLE_EQ(future_ref(3, k), 0.8);
    EXPECT_DOUBLE_EQ(future_ref(4, k), 0.0);
  }
  EXPECT_FALSE(future_ref.isApprox(now_ref, 0.0));
  EXPECT_NEAR(now_ref(0, 1), 1.16, 1e-12);
  EXPECT_DOUBLE_EQ(future_ref(0, 0), 1.5);
  EXPECT_EQ(future_meta.path_received_sequence, input.path_sequence);
  EXPECT_EQ(future_meta.profile_received_sequence, input.profile_sequence);
}

TEST(P1SharedInputCore, FuturePiecewisePublisherHistoryHonorsFromAndTargetBoundaries)
{
  auto h = analytic_hydro();
  Vector6d state; state << 0.0, 0.0, 0.0, 0.8, 0.0, 0.0;
  const int64_t from = 5000000000LL, target = from + 200000000;
  const std::vector<usv_mpc::HeldInputEvent> history{
    {from, 0, 0.0}, {from, 1, 0.0},
    {from + 100000000, 0, 1.0}, {from + 100000000, 1, 1.0},
    {target, 0, 25.0}, {target, 1, 25.0}};
  ASSERT_TRUE(usv_mpc::propagate_publisher_nominal(state, from, target,
    Eigen::Vector2d(99.0, 99.0), history, h));
  EXPECT_NEAR(state[0], 0.165, 1e-12); EXPECT_NEAR(state[3], 0.9, 1e-12);
  EXPECT_NEAR(state[1], 0.0, 1e-12); EXPECT_NEAR(state[2], 0.0, 1e-12);
}

TEST(P1SharedInputCore, MixedRateNominalPropagationPreservesBodyVelocitySemantics)
{
  // Isotropic undamped mass has constant inertial velocity. A separately
  // accepted IMU yaw rate rotates body u/v; it is not a second twist rotation.
  Vector6d state; state << 0.0, 0.0, 0.0, 0.8, 0.0, 0.5;
  ASSERT_TRUE(usv_mpc::propagate_publisher_nominal(state, 0, 200000000,
    Eigen::Vector2d::Zero(), {}, analytic_hydro()));
  EXPECT_NEAR(state[0], 0.16, 1e-7); EXPECT_NEAR(state[1], 0.0, 1e-7);
  EXPECT_NEAR(state[2], 0.1, 1e-12);
  EXPECT_NEAR(state[3], 0.8 * std::cos(0.1), 1e-7);
  EXPECT_NEAR(state[4], -0.8 * std::sin(0.1), 1e-7);
  EXPECT_DOUBLE_EQ(state[5], 0.5);
}

TEST(P1SharedInputCore, FuturePropagationRejectsInvalidTargetStateAndChannel)
{
  const auto h = analytic_hydro();
  const auto initial = Vector6d::Zero().eval();
  auto state = initial;
  EXPECT_FALSE(usv_mpc::propagate_publisher_nominal(state, 10, 9,
    Eigen::Vector2d::Zero(), {}, h));
  state = initial;
  EXPECT_FALSE(usv_mpc::propagate_publisher_nominal(state, 0, 1000000001,
    Eigen::Vector2d::Zero(), {}, h));
  state = initial; state[3] = std::numeric_limits<double>::quiet_NaN();
  EXPECT_FALSE(usv_mpc::propagate_publisher_nominal(state, 0, 200000000,
    Eigen::Vector2d::Zero(), {}, h));
  state = initial;
  EXPECT_FALSE(usv_mpc::propagate_publisher_nominal(state, 0, 200000000,
    Eigen::Vector2d::Zero(), {{1, 2, 0.0}}, h));
}
}  // namespace
