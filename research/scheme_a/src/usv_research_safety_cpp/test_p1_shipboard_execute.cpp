// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// Phase C1/C2 ROS-free deterministic tests for p1-shipboard-execute-v1 and
// ShipboardExecuteCoordinator (B5/M4 PWM actuation bridge, preemption, failsafe).
#include <gtest/gtest.h>

#include <cmath>
#include <fstream>
#include <string>

#include "p1_full_contract.hpp"
#include "p1_shipboard_execute.hpp"

namespace {

using Json = nlohmann::json;

constexpr std::int64_t kSec = 1000000000LL;
constexpr std::int64_t kMs = 1000000LL;

std::string fixture_dir() {
  const std::string file = __FILE__;
  const auto slash = file.find_last_of('/');
  return slash == std::string::npos ? std::string(".") : file.substr(0, slash);
}

Json execute_contract() {
  std::ifstream in(fixture_dir() + "/model/contract_shipboard_execute.json");
  if (!in) throw std::runtime_error("missing contract_shipboard_execute.json");
  return Json::parse(std::string(std::istreambuf_iterator<char>(in), {}));
}

struct ExecFixture {
  p1_execute::ShipboardExecuteCoordinator coord;
  std::int64_t now = 5000 * kSec;

  explicit ExecFixture()
      : coord(p1_execute::execute_limits_from_contract(execute_contract())) {
    coord.arm(now);
    p1_shipboard::CapabilityFacts cap;
    cap.seen = true;
    cap.receipt_ns = now;
    cap.lease_last_ns = now;
    cap.model_runtime_ready = true;
    cap.worker_instance = "worker-exec-1";
    coord.on_capability(cap);
    coord.set_worker_capability_valid(true);

    p1_shipboard::WorkerFacts wf;
    wf.pid = 4242;
    wf.instance = "worker-exec-1";
    wf.model_runtime_ready = true;
    coord.on_worker(wf);

    push_state(true, false, "HOLD", now);
    push_nav(now);
  }

  void push_state(bool connected, bool armed, const std::string & mode, std::int64_t t) {
    p1_shipboard::StateFacts s;
    s.seen = true;
    s.count = ++state_seq_;
    s.receipt_ns = t;
    s.connected = connected;
    s.armed = armed;
    s.mode = mode;
    last_action_ = coord.on_state(s, t);
  }

  void push_nav(std::int64_t t) {
    p1_dry_run::OdomFacts od;
    od.seen = true; od.valid = true; od.finite = true;
    od.pose_frame = "map"; od.child_frame = "base_link";
    od.seq = ++nav_seq_; od.receipt_ns = t; od.stamp_ns = 1790000000000000000LL + t;
    od.state = {1.0, 2.0, 0.2, 0.5, 0.0, 0.05};
    coord.on_odom(od);

    p1_dry_run::ImuFacts im;
    im.seen = true; im.valid = true; im.finite = true;
    im.frame = "base_link"; im.seq = nav_seq_; im.receipt_ns = t; im.stamp_ns = od.stamp_ns;
    im.r = 0.05;
    coord.on_imu(im);

    p1_dry_run::PathFacts pf;
    pf.seen = true; pf.resource_valid = true; pf.frame = "map";
    pf.seq = nav_seq_; pf.receipt_ns = t; pf.stamp_ns = od.stamp_ns; pf.points = 12;
    coord.on_path(pf);

    p1_dry_run::ProfileFacts prf;
    prf.seen = true; prf.resource_valid = true;
    prf.seq = nav_seq_; prf.receipt_ns = t; prf.stamp_ns = od.stamp_ns;
    prf.rows = 12; prf.stamp_ok = true;
    prf.path_profile_sync_ok = true;
    coord.on_profile(prf);
  }

  void keep_alive(std::int64_t t) {
    now = t;
    p1_shipboard::CapabilityFacts cap;
    cap.seen = true; cap.receipt_ns = t; cap.lease_last_ns = t;
    cap.model_runtime_ready = true; cap.worker_instance = "worker-exec-1";
    coord.on_capability(cap);
    coord.set_worker_capability_valid(true);
    push_nav(t);
  }

  p1_dry_run::CandidateFacts make_candidate(
      std::uint64_t job_id, std::uint64_t tick, std::int64_t t,
      std::array<double, 2> thrust, bool success = true) {
    p1_dry_run::CandidateFacts cf;
    cf.job_id = job_id;
    cf.tick = tick;
    cf.worker_instance = "worker-exec-1";
    cf.expected_worker_instance = "worker-exec-1";
    cf.backend = "acados";
    cf.echo_matched = true;
    cf.solver_invoked = true;
    cf.success = success;
    cf.prediction_available = success;
    cf.finite = true;
    cf.backend_ms = 1.4;
    cf.first_control = thrust;
    cf.initial_control_matches = true;
    cf.initial_state_matches = true;
    cf.freeze_steady_ns = t;
    cf.worker_receive_ns = t + 100000;
    cf.solve_start_ns = t + 200000;
    cf.solve_end_ns = t + 1600000;
    cf.deadline_steady_ns = t + 150000000LL;
    cf.receive_ns = t + 2000000;
    return cf;
  }

  std::uint64_t state_seq_ = 0;
  std::uint64_t nav_seq_ = 0;
  p1_execute::ActuationAction last_action_{};
};

}  // namespace

TEST(ShipboardExecuteContract, BenchValidatesAndRejectsTamperingAndLocksWaterRelease) {
  const auto c = execute_contract();
  EXPECT_EQ(p1::validate_contract_fields(c), p1::ContractProfile::ShipboardExecute);
  EXPECT_NO_THROW(p1::validate_contract_mode(c, "shipboard_execute"));
  EXPECT_NO_THROW(p1::require_runtime_contract_mode(c, "shipboard_execute"));
  EXPECT_FALSE(p1::physical_execute_release_enabled);
  EXPECT_FALSE(p1::shipboard_water_execute_release_enabled);

  for (const char * other : {"no_output", "shadow", "execute", "commissioning", "shipboard_dry_run"}) {
    EXPECT_THROW(p1::validate_contract_mode(c, other), std::runtime_error) << other;
  }

  // Water-frozen shipboard execute must remain rejected by runtime gate until C3 human audit.
  {
    auto frozen = c;
    frozen["qualification"] = "shipboard_execution_frozen";
    frozen["execute_qualified"] = true;
    frozen["bench_execution_allowed"] = false;
    frozen["water_execution_allowed"] = true;
    frozen["propellers_removed_required"] = false;
    frozen["parameters_are_diagnostic_only"] = false;
    frozen["freeze_evidence_sha256"] = std::string(64, 'a');
    EXPECT_EQ(p1::validate_contract_fields(frozen), p1::ContractProfile::ShipboardExecute);
    EXPECT_THROW(p1::require_runtime_contract_mode(frozen, "shipboard_execute"), std::runtime_error);
  }

  // Tampering checks
  { auto bad = c; bad["allowed_fcu_modes"] = Json::array({"GUIDED"});
    EXPECT_THROW(p1::validate_contract_fields(bad), std::runtime_error); }
  { auto bad = c; bad["rc_actuation"]["throttle_channel"] = 0;  // collides with steering
    EXPECT_THROW(p1::validate_contract_fields(bad), std::runtime_error); }
  { auto bad = c; bad["rc_actuation"]["steering_gain"] = 0.0;
    EXPECT_THROW(p1::validate_contract_fields(bad), std::runtime_error); }
  { auto bad = c; bad["rc_actuation"]["steering_sign"] = 0.5;
    EXPECT_THROW(p1::validate_contract_fields(bad), std::runtime_error); }
  { auto bad = c; bad["propellers_removed_required"] = false;
    EXPECT_THROW(p1::validate_contract_fields(bad), std::runtime_error); }
  { auto bad = c; bad["water_execution_allowed"] = true;
    EXPECT_THROW(p1::validate_contract_fields(bad), std::runtime_error); }
  { auto bad = c; bad["Q"][0] = 5.0;
    EXPECT_THROW(p1::validate_contract_fields(bad), std::runtime_error); }
}

TEST(ShipboardExecuteCoordinator, StartupRequiresSafeInitialPoseBeforeReady) {
  p1_execute::ShipboardExecuteCoordinator coord(
      p1_execute::execute_limits_from_contract(execute_contract()));
  const std::int64_t t0 = 1000 * kSec;
  coord.arm(t0);

  p1_shipboard::CapabilityFacts cap;
  cap.seen = true; cap.receipt_ns = t0; cap.lease_last_ns = t0;
  cap.model_runtime_ready = true; cap.worker_instance = "w1";
  coord.on_capability(cap); coord.set_worker_capability_valid(true);
  p1_dry_run::ImuFacts im;
  im.seen = true; im.valid = true; im.finite = true;
  im.frame = "base_link"; im.seq = 1; im.receipt_ns = t0; im.r = 0.0;
  coord.on_imu(im);

  p1_shipboard::StateFacts armed_manual;
  armed_manual.seen = true; armed_manual.count = 1; armed_manual.receipt_ns = t0;
  armed_manual.connected = true; armed_manual.armed = true; armed_manual.mode = "MANUAL";
  coord.on_state(armed_manual, t0);

  const auto blocked = coord.step_tick(t0);
  EXPECT_FALSE(coord.ready());
  EXPECT_FALSE(blocked.submit_job);
  EXPECT_EQ(blocked.block_reason, "waiting_safe_initial_fcu");

  armed_manual.armed = false;
  armed_manual.mode = "HOLD";
  armed_manual.count = 2;
  coord.on_state(armed_manual, t0 + 100 * kMs);
  coord.step_tick(t0 + 100 * kMs);
  EXPECT_TRUE(coord.ready());
  EXPECT_EQ(coord.exec_state(), p1_execute::ExecuteState::Standby);
}

TEST(ShipboardExecuteCoordinator, ActuationWritesBackQuantizedEffectiveThrustAndEnforcesPreemption) {
  ExecFixture f;
  // Transition Starting -> Standby
  auto t_res = f.coord.step_tick(f.now);
  EXPECT_TRUE(f.coord.ready());
  EXPECT_EQ(f.coord.exec_state(), p1_execute::ExecuteState::Standby);
  EXPECT_FALSE(t_res.submit_job);

  // Switch FCU to armed + MANUAL -> Standby transitions to Active and requests initial reset_warmstart
  f.keep_alive(f.now + 200 * kMs);
  f.push_state(true, true, "MANUAL", f.now);
  t_res = f.coord.step_tick(f.now);
  EXPECT_EQ(f.coord.exec_state(), p1_execute::ExecuteState::Active);
  EXPECT_TRUE(t_res.submit_job);
  EXPECT_TRUE(t_res.reset_warmstart);
  const auto epoch1 = t_res.job_epoch;
  EXPECT_EQ(epoch1, f.coord.control_epoch());

  // Valid candidate [10.0, 14.0] N from anchor [0, 0] -> delta <= 16 N
  const Eigen::Vector2d thrust(10.0, 14.0);
  const auto expected_rc = usv_mpc::thrust_to_rc_actuation(thrust, f.coord.limits().rc);
  const auto cf1 = f.make_candidate(1, 1, f.now, {10.0, 14.0});
  const auto act1 = f.coord.evaluate_and_actuate(cf1, epoch1, f.now + 5 * kMs);
  EXPECT_TRUE(act1.accepted);
  EXPECT_TRUE(act1.emit_action);
  EXPECT_EQ(act1.action.directive, p1_execute::OutputDirective::ThrustPwm);
  EXPECT_EQ(act1.action.steering_pwm, expected_rc.steering_pwm);
  EXPECT_EQ(act1.action.throttle_pwm, expected_rc.throttle_pwm);
  // Effective thrust back-calculation must match integer PWM exactly
  EXPECT_NEAR(f.coord.continuity_anchor_n()[0], expected_rc.effective_thrust(0), 1e-9);
  EXPECT_NEAR(f.coord.continuity_anchor_n()[1], expected_rc.effective_thrust(1), 1e-9);

  // Candidate exceeding rate limit > 16 N relative to effective_thrust must be rejected
  const auto bad_jump = f.make_candidate(2, 2, f.now + 200 * kMs, {-20.0, -20.0});
  const auto rej = f.coord.evaluate_and_actuate(bad_jump, epoch1, f.now + 205 * kMs);
  EXPECT_FALSE(rej.accepted);
  EXPECT_EQ(rej.reason, "rate_limit_exceeded");
  EXPECT_EQ(f.coord.consecutive_solver_failures(), 1);
  EXPECT_EQ(rej.action.control_source, "ramp_zero_single_miss");

  // Immediate mode switch MANUAL -> HOLD in state callback must preempt and drop stale epoch candidates
  f.push_state(true, true, "HOLD", f.now + 220 * kMs);
  EXPECT_EQ(f.last_action_.directive, p1_execute::OutputDirective::Release);
  EXPECT_EQ(f.last_action_.steering_pwm, 0);
  EXPECT_EQ(f.last_action_.throttle_pwm, 0);
  EXPECT_EQ(f.coord.exec_state(), p1_execute::ExecuteState::Standby);
  EXPECT_NE(f.coord.control_epoch(), epoch1);
  EXPECT_DOUBLE_EQ(f.coord.continuity_anchor_n()[0], 0.0);
  EXPECT_DOUBLE_EQ(f.coord.continuity_anchor_n()[1], 0.0);

  // Stale in-flight candidate from epoch1 must be discarded safely
  const auto stale_cf = f.make_candidate(3, 3, f.now + 225 * kMs, {12.0, 12.0});
  const auto stale_res = f.coord.evaluate_and_actuate(stale_cf, epoch1, f.now + 230 * kMs);
  EXPECT_FALSE(stale_res.accepted);
  EXPECT_EQ(stale_res.reason, "stale_epoch_or_not_active");
  EXPECT_FALSE(stale_res.emit_action);
}

TEST(ShipboardExecuteCoordinator, FaultFailsafeEmitsNeutralThenHoldAndReleasesOnModeExit) {
  ExecFixture f;
  f.coord.step_tick(f.now);  // Ready / Standby
  f.keep_alive(f.now + 200 * kMs);
  f.push_state(true, true, "MANUAL", f.now);
  const auto active_tick = f.coord.step_tick(f.now);
  ASSERT_TRUE(active_tick.submit_job);

  // Advance > 1.0s keeping capability, state, imu, path fresh while starving only odom -> odom_stale
  f.now += 1200 * kMs;
  p1_shipboard::CapabilityFacts fresh_cap;
  fresh_cap.seen = true; fresh_cap.receipt_ns = f.now; fresh_cap.lease_last_ns = f.now;
  fresh_cap.model_runtime_ready = true; fresh_cap.worker_instance = "worker-exec-1";
  f.coord.on_capability(fresh_cap);
  p1_dry_run::ImuFacts fresh_im;
  fresh_im.seen = true; fresh_im.valid = true; fresh_im.finite = true;
  fresh_im.frame = "base_link"; fresh_im.seq = 99; fresh_im.receipt_ns = f.now; fresh_im.r = 0.01;
  f.coord.on_imu(fresh_im);
  p1_dry_run::PathFacts fresh_pf;
  fresh_pf.seen = true; fresh_pf.resource_valid = true; fresh_pf.frame = "map";
  fresh_pf.seq = 99; fresh_pf.receipt_ns = f.now; fresh_pf.points = 12;
  f.coord.on_path(fresh_pf);
  p1_shipboard::StateFacts fresh_manual;
  fresh_manual.seen = true; fresh_manual.count = 99; fresh_manual.receipt_ns = f.now;
  fresh_manual.connected = true; fresh_manual.armed = true; fresh_manual.mode = "MANUAL";
  f.coord.on_state(fresh_manual, f.now);
  const auto fault_tick = f.coord.step_tick(f.now);
  EXPECT_EQ(fault_tick.action.reason, "odom_stale");
  EXPECT_EQ(f.coord.exec_state(), p1_execute::ExecuteState::FaultFailsafe);
  EXPECT_TRUE(fault_tick.emit_action);
  EXPECT_EQ(fault_tick.action.directive, p1_execute::OutputDirective::NeutralPwm);
  EXPECT_EQ(fault_tick.action.steering_pwm, 1500);
  EXPECT_EQ(fault_tick.action.throttle_pwm, 1500);
  EXPECT_TRUE(fault_tick.action.request_fcu_hold);

  const auto mpc_st = f.coord.mpc_status_json();
  EXPECT_EQ(mpc_st["state"].get<std::string>(), "HOLD");
  EXPECT_TRUE(mpc_st["hold"].get<bool>());
  EXPECT_GE(mpc_st["fail_count"].get<int>(), 5);

  // FCU switches to HOLD -> release override cleanly and unblock Standby
  f.push_state(true, true, "HOLD", f.now + 50 * kMs);
  EXPECT_EQ(f.last_action_.directive, p1_execute::OutputDirective::Release);
  EXPECT_EQ(f.coord.exec_state(), p1_execute::ExecuteState::Standby);
}

TEST(ShipboardExecuteCoordinator, ConsecutiveSolverFailuresTriggerHoldAndStopDrainsNeutral) {
  ExecFixture f;
  f.coord.step_tick(f.now);
  f.keep_alive(f.now + 200 * kMs);
  f.push_state(true, true, "MANUAL", f.now);
  const auto tick = f.coord.step_tick(f.now);
  ASSERT_TRUE(tick.submit_job);

  for (int i = 1; i <= 4; ++i) {
    auto bad = f.make_candidate(i, i, f.now + i * 200 * kMs, {5.0, 5.0}, false);
    const auto r = f.coord.evaluate_and_actuate(bad, tick.job_epoch, f.now + i * 200 * kMs + 5 * kMs);
    EXPECT_FALSE(r.accepted);
    EXPECT_EQ(f.coord.exec_state(), p1_execute::ExecuteState::Active);
  }
  auto fifth = f.make_candidate(5, 5, f.now + 1000 * kMs, {5.0, 5.0}, false);
  const auto esc = f.coord.evaluate_and_actuate(fifth, tick.job_epoch, f.now + 1005 * kMs);
  EXPECT_EQ(f.coord.exec_state(), p1_execute::ExecuteState::FaultFailsafe);
  EXPECT_EQ(esc.action.directive, p1_execute::OutputDirective::NeutralPwm);
  EXPECT_TRUE(esc.action.request_fcu_hold);

  // Terminal worker exit during stop drains neutral_hold_ns_before_release then releases
  ExecFixture f2;
  f2.coord.step_tick(f2.now);
  f2.keep_alive(f2.now + 200 * kMs);
  f2.push_state(true, true, "MANUAL", f2.now);
  f2.coord.step_tick(f2.now);
  const auto stop_act = f2.coord.request_operator_stop(f2.now);
  EXPECT_EQ(stop_act.directive, p1_execute::OutputDirective::NeutralPwm);
  EXPECT_TRUE(stop_act.request_fcu_hold);
  const auto mid = f2.coord.step_tick(f2.now + 100 * kMs);
  EXPECT_FALSE(mid.terminal_exit);
  const auto done = f2.coord.step_tick(f2.now + 450 * kMs);
  EXPECT_TRUE(done.terminal_exit);
  EXPECT_TRUE(done.emit_action);
  EXPECT_EQ(done.action.directive, p1_execute::OutputDirective::Release);
}
