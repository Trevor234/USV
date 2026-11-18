// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// 实船物理执行桥接（shipboard_execute, B5/M4）的 ROS-free 核心状态机、
// RC PWM 连续性锚点协调器与故障保护逻辑。
//
// 复用原则：
//   * 复用 p1_dry_run::DryRunCoordinator 进行实机导航门禁与多轴校验；
//   * 复用 usv_mpc::thrust_to_rc_actuation 进行 [TL, TR] -> CH1/CH3 PWM 映射与
//     有效推力（effective_thrust）反算，杜绝在多处重写映射公式。
#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "p1_shipboard_commissioning.hpp"
#include "p1_shipboard_dry_run.hpp"
#include "usv_nmpc/utils.hpp"

namespace p1_execute {

using Json = nlohmann::json;

enum class ExecuteState {
  Starting,
  Standby,
  Active,
  FaultFailsafe,
  TerminalFailed,
};

enum class OutputDirective {
  None,
  Release,
  NeutralPwm,
  ThrustPwm,
};

struct ExecuteLimits {
  p1_dry_run::DryRunLimits nav{};
  usv_mpc::RcActuationConfig rc{};
  int steering_channel = 0;
  int throttle_channel = 2;
  std::int64_t startup_ns = 30000000000LL;
  std::int64_t state_age_ns = 2000000000LL;
  std::int64_t path_age_ns = 5000000000LL;
  std::int64_t capability_age_ns = 1000000000LL;
  std::int64_t neutral_hold_ns_before_release = 400000000LL;
  int solver_hold_threshold = 5;
  bool startup_hold_safe_required = true;
  bool water_execution_allowed = false;
  std::vector<std::string> allowed_fcu_modes{"MANUAL"};
};

inline ExecuteLimits execute_limits_from_contract(const Json & c) {
  ExecuteLimits out;
  out.nav = p1_dry_run::limits_from_contract(c);
  out.state_age_ns = c.at("state_age_ns").get<std::int64_t>();
  out.path_age_ns = c.at("path_age_ns").get<std::int64_t>();
  out.capability_age_ns = c.at("worker_capability_receipt_timeout_ns").get<std::int64_t>();
  out.neutral_hold_ns_before_release = c.at("neutral_hold_ns_before_release").get<std::int64_t>();
  out.solver_hold_threshold = c.at("solver_hold_threshold").get<int>();
  out.startup_hold_safe_required = c.at("startup_hold_safe_required").get<bool>();
  out.water_execution_allowed = c.at("water_execution_allowed").get<bool>();
  out.allowed_fcu_modes = c.at("allowed_fcu_modes").get<std::vector<std::string>>();

  const auto & rc = c.at("rc_actuation");
  out.steering_channel = rc.at("steering_channel").get<int>();
  out.throttle_channel = rc.at("throttle_channel").get<int>();
  out.rc.thrust_min = out.nav.command_min_n;
  out.rc.thrust_max = out.nav.command_max_n;
  out.rc.pwm_min = rc.at("pwm_min").get<int>();
  out.rc.pwm_center = rc.at("pwm_center").get<int>();
  out.rc.pwm_max = rc.at("pwm_max").get<int>();
  out.rc.steering_sign = rc.at("steering_sign").get<double>();
  out.rc.throttle_sign = rc.at("throttle_sign").get<double>();
  out.rc.steering_gain = rc.at("steering_gain").get<double>();
  out.rc.throttle_gain = rc.at("throttle_gain").get<double>();
  return out;
}

struct ActuationAction {
  OutputDirective directive = OutputDirective::None;
  int steering_pwm = 0;
  int throttle_pwm = 0;
  bool request_fcu_hold = false;
  bool hold_flag = false;
  std::uint64_t epoch = 0;
  std::array<double, 2> commanded_n{0.0, 0.0};
  std::array<double, 2> effective_n{0.0, 0.0};
  std::string control_source;
  std::string reason;
};

struct TickOutcome {
  bool emit_action = false;
  ActuationAction action{};
  bool submit_job = false;
  bool reset_warmstart = false;
  std::uint64_t job_epoch = 0;
  std::string block_reason;
  bool terminal_exit = false;
  int exit_code = 0;
};

struct CandidateResult {
  bool accepted = false;
  std::string reason;
  std::int64_t solve_latency_ns = -1;
  bool emit_action = false;
  ActuationAction action{};
};

/// 实船执行协同与安全门控状态机（纯 C++，所有时刻由调用方注入）。
class ShipboardExecuteCoordinator {
 public:
  ShipboardExecuteCoordinator() = default;
  explicit ShipboardExecuteCoordinator(const ExecuteLimits & limits)
      : limits_(limits), dry_(limits.nav) {}

  void arm(std::int64_t now_ns) {
    start_ns_ = now_ns > 0 ? now_ns : 1LL;
    dry_.arm(start_ns_);
  }

  const ExecuteLimits & limits() const { return limits_; }
  p1_dry_run::DryRunCoordinator & dry_run() { return dry_; }
  const p1_dry_run::DryRunCoordinator & dry_run() const { return dry_; }

  ExecuteState exec_state() const { return exec_state_; }
  std::string phase_string() const {
    if (exec_state_ == ExecuteState::Starting) return "starting";
    if (exec_state_ == ExecuteState::TerminalFailed) return "failed";
    return "ready";
  }
  bool ready() const { return phase_string() == "ready"; }
  bool active() const { return exec_state_ == ExecuteState::Active; }
  bool terminal_failed() const { return exec_state_ == ExecuteState::TerminalFailed; }
  const std::string & failure_reason() const { return terminal_failure_reason_; }
  const std::string & standby_reason() const { return standby_reason_; }
  std::uint64_t control_epoch() const { return control_epoch_; }
  const std::array<double, 2> & continuity_anchor_n() const { return continuity_anchor_n_; }
  int consecutive_solver_failures() const { return consecutive_solver_failures_; }
  std::uint64_t preemptions_total() const { return preemptions_total_; }
  std::uint64_t failsafes_total() const { return failsafes_total_; }
  std::uint64_t actuation_count() const { return actuation_count_; }

  void on_odom(const p1_dry_run::OdomFacts & f) { dry_.on_odom(f); }
  void on_imu(const p1_dry_run::ImuFacts & f) { dry_.on_imu(f); }
  void on_path(const p1_dry_run::PathFacts & f) {
    dry_.on_path(f);
    if (f.seen) last_path_receipt_ns_ = f.receipt_ns;
  }
  void on_profile(const p1_dry_run::ProfileFacts & f) { dry_.on_profile(f); }
  void set_profile_sync(bool ok, const std::string & reason) {
    dry_.set_profile_sync(ok, reason);
  }
  void on_capability(const p1_shipboard::CapabilityFacts & f) { capability_ = f; }
  void set_worker_capability_valid(bool valid) { capability_valid_ = valid; }
  void on_worker(const p1_shipboard::WorkerFacts & f) { worker_ = f; }
  void record_job_submitted() { dry_.record_job_submitted(); }

  /// FCU 状态变更入口：一旦失去 MANUAL 或上锁，即刻在回调内产生 ≤5ms 抢占释放动作。
  ActuationAction on_state(const p1_shipboard::StateFacts & f, std::int64_t now_ns) {
    state_ = f;
    ActuationAction act;
    const bool operator_disarmed_or_mode_exit = !f.armed || !is_allowed_mode(f.mode);
    const bool disconnected = !f.connected;

    if (exec_state_ == ExecuteState::Active) {
      if (operator_disarmed_or_mode_exit) {
        ++preemptions_total_;
        return transition_to_standby_release(
            !f.armed ? "disarmed" : ("wrong_mode:" + f.mode), "preempt_release");
      }
      if (disconnected) {
        // 链路断掉但上一状态仍是 armed+MANUAL：立即中性归零 + 触发故障保护（而非放手失管）
        return enter_failsafe("state_disconnected", /*terminal=*/false, now_ns);
      }
    } else if (exec_state_ == ExecuteState::FaultFailsafe) {
      if (operator_disarmed_or_mode_exit) {
        require_mode_exit_or_disarm_ = false;
        neutral_hold_completed_ = true;
        act.directive = OutputDirective::Release;
        act.control_source = "failsafe_hold_confirmed_release";
        act.reason = fault_reason_;
        act.epoch = control_epoch_;
        last_steering_pwm_ = 0;
        last_throttle_pwm_ = 0;
        if (!terminal_fault_) {
          exec_state_ = ExecuteState::Standby;
          fault_reason_.clear();
          standby_reason_ = !f.armed ? "disarmed" : ("wrong_mode:" + f.mode);
        }
        return act;
      }
    }
    return act;
  }

  /// 操作员请求停机：若当前有活动执行或未退出的 failsafe，立即下发 1500 中位并请求 HOLD。
  ActuationAction request_operator_stop(std::int64_t now_ns) {
    stop_requested_ = true;
    if (exec_state_ == ExecuteState::Active ||
        (state_.seen && state_.connected && state_.armed && is_allowed_mode(state_.mode))) {
      return enter_failsafe("operator_stop", /*terminal=*/true, now_ns);
    }
    ActuationAction act;
    act.directive = OutputDirective::Release;
    act.control_source = "shutdown_release";
    act.reason = "operator_stop";
    act.epoch = control_epoch_;
    last_steering_pwm_ = 0;
    last_throttle_pwm_ = 0;
    return act;
  }

  /// 5Hz 控制环步进。
  TickOutcome step_tick(std::int64_t now_ns) {
    TickOutcome out;
    if (exec_state_ == ExecuteState::TerminalFailed) {
      out.terminal_exit = true;
      out.exit_code = 2;
      return out;
    }

    // 1) 运行中 Worker / 租约硬健康检查
    if (worker_.exited) {
      out.action = enter_failsafe(p1_shipboard::reason_worker_exit, /*terminal=*/true, now_ns);
      out.emit_action = (out.action.directive != OutputDirective::None);
      if (!neutral_pending(now_ns)) {
        exec_state_ = ExecuteState::TerminalFailed;
        out.terminal_exit = true;
        out.exit_code = 2;
      }
      return out;
    }
    if (exec_state_ != ExecuteState::Starting && !worker_capability_ok(now_ns)) {
      out.action = enter_failsafe(p1_shipboard::reason_worker_timeout, /*terminal=*/true, now_ns);
      out.emit_action = (out.action.directive != OutputDirective::None);
      if (!neutral_pending(now_ns)) {
        exec_state_ = ExecuteState::TerminalFailed;
        out.terminal_exit = true;
        out.exit_code = 2;
      }
      return out;
    }

    // 2) Failsafe 状态推进：非致命故障保持 1500 中位直到 FCU 脱离 MANUAL/上锁；
    //    致命故障/停机最多等待 neutral_hold_ns_before_release 后释放通道并收尾。
    if (exec_state_ == ExecuteState::FaultFailsafe) {
      if (terminal_fault_ && !neutral_pending(now_ns)) {
        if (!neutral_hold_completed_) {
          neutral_hold_completed_ = true;
          out.emit_action = true;
          out.action.directive = OutputDirective::Release;
          out.action.control_source = "failsafe_timeout_release";
          out.action.reason = fault_reason_;
          out.action.epoch = control_epoch_;
          last_steering_pwm_ = 0;
          last_throttle_pwm_ = 0;
        }
        exec_state_ = ExecuteState::TerminalFailed;
        out.terminal_exit = true;
        out.exit_code = 2;
        return out;
      }
      if (!terminal_fault_) {
        if (!require_mode_exit_or_disarm_) {
          exec_state_ = ExecuteState::Standby;
          fault_reason_.clear();
        } else {
          // FCU 仍在 MANUAL 且未退出：持续稳住 1500 中位并补发 HOLD，绝不放空 RC
          out.emit_action = true;
          out.action.directive = OutputDirective::NeutralPwm;
          out.action.steering_pwm = limits_.rc.pwm_center;
          out.action.throttle_pwm = limits_.rc.pwm_center;
          out.action.request_fcu_hold = true;
          out.action.hold_flag = true;
          out.action.epoch = control_epoch_;
          out.action.control_source = "failsafe_neutral_hold";
          out.action.reason = fault_reason_;
        }
      }
      return out;
    }

    // 3) Starting 启动门禁（30s 内凑齐 state connected + capability + IMU + 安全初态）
    if (exec_state_ == ExecuteState::Starting) {
      const auto & imu = dry_.imu();
      const bool imu_ok = imu.seen && imu.finite && imu.valid &&
                          (now_ns - imu.receipt_ns <= limits_.nav.imu_age_ns);
      const bool fcu_conn = state_.seen && state_.connected;
      const bool fcu_safe = !limits_.startup_hold_safe_required ||
                            !state_.armed || !is_allowed_mode(state_.mode);
      if (fcu_conn && worker_capability_ok(now_ns) && imu_ok && fcu_safe) {
        exec_state_ = ExecuteState::Standby;
        standby_reason_ = standby_reason_locked(now_ns);
        out.block_reason = standby_reason_;
        return out;
      }
      if (start_ns_ != 0 && now_ns - start_ns_ > limits_.startup_ns) {
        std::string fail_why = p1_shipboard::reason_imu_timeout;
        if (!fcu_conn) fail_why = p1_shipboard::reason_state_timeout;
        else if (!fcu_safe) fail_why = p1_shipboard::reason_armed;
        else if (!worker_capability_ok(now_ns)) fail_why = p1_shipboard::reason_worker_timeout;
        terminal_failure_reason_ = fail_why;
        exec_state_ = ExecuteState::TerminalFailed;
        out.terminal_exit = true;
        out.exit_code = 2;
        return out;
      }
      standby_reason_ = !fcu_conn ? "waiting_fcu"
                                   : (!fcu_safe ? "waiting_safe_initial_fcu"
                                                : (!imu_ok ? "waiting_imu" : "waiting_worker"));
      out.block_reason = standby_reason_;
      return out;
    }

    // 4) 就绪后的 FCU 链路上游超时检测
    if (!state_.seen || !state_.connected || (now_ns - state_.receipt_ns > limits_.state_age_ns)) {
      const std::string why = !state_.connected ? p1_shipboard::reason_state_disconnected
                                                : p1_shipboard::reason_state_timeout;
      if (exec_state_ == ExecuteState::Active ||
          (state_.seen && state_.armed && is_allowed_mode(state_.mode))) {
        out.action = enter_failsafe(why, /*terminal=*/true, now_ns);
        out.emit_action = (out.action.directive != OutputDirective::None);
        if (!neutral_pending(now_ns)) {
          exec_state_ = ExecuteState::TerminalFailed;
          out.terminal_exit = true;
          out.exit_code = 2;
        }
        return out;
      }
      // 待机期 FCU 断连同样视作基础设施故障收尾
      terminal_failure_reason_ = why;
      exec_state_ = ExecuteState::TerminalFailed;
      out.terminal_exit = true;
      out.exit_code = 2;
      return out;
    }

    const bool mode_executable = state_.armed && is_allowed_mode(state_.mode);
    const std::string gate = execution_nav_gate(now_ns);

    if (exec_state_ == ExecuteState::Active) {
      if (!mode_executable) {
        ++preemptions_total_;
        out.emit_action = true;
        out.action = transition_to_standby_release(
            !state_.armed ? "disarmed" : ("wrong_mode:" + state_.mode), "preempt_release");
        out.block_reason = standby_reason_;
        return out;
      }
      if (gate != "ready") {
        // 已解锁且仍在 MANUAL 期间导航丢流 -> 立即 1500 中位 + HOLD 保护
        out.emit_action = true;
        out.action = enter_failsafe(gate, /*terminal=*/false, now_ns);
        out.block_reason = gate;
        return out;
      }
      out.submit_job = true;
      out.reset_warmstart = reset_warmstart_next_;
      reset_warmstart_next_ = false;
      out.job_epoch = control_epoch_;
      return out;
    }

    // Standby 状态：等待进入 Active
    if (mode_executable && gate == "ready" && !require_mode_exit_or_disarm_ && !stop_requested_) {
      exec_state_ = ExecuteState::Active;
      ++control_epoch_;
      continuity_anchor_n_ = {0.0, 0.0};
      last_commanded_n_ = {0.0, 0.0};
      consecutive_solver_failures_ = 0;
      fault_reason_.clear();
      standby_reason_.clear();
      out.submit_job = true;
      out.reset_warmstart = true;
      out.job_epoch = control_epoch_;
      return out;
    }

    standby_reason_ = standby_reason_locked(now_ns);
    out.block_reason = standby_reason_;
    return out;
  }

  /// 接收并检验 SolverCandidate，然后产出整数 PWM 与反算有效推力锚点，或在失步/连败时回落/保护。
  CandidateResult evaluate_and_actuate(
      const p1_dry_run::CandidateFacts & cand,
      std::uint64_t cand_epoch,
      std::int64_t now_ns) {
    CandidateResult res;
    if (exec_state_ != ExecuteState::Active || cand_epoch != control_epoch_) {
      res.reason = "stale_epoch_or_not_active";
      return res;
    }
    const auto chk = p1_dry_run::validate_candidate_with_anchor(
        cand, limits_.nav, continuity_anchor_n_);
    last_backend_ms_ = cand.backend_ms;
    last_solve_latency_ns_ = chk.solve_latency_ns;

    if (chk.accepted) {
      Eigen::Vector2d thrust_vec(chk.clamped_control[0], chk.clamped_control[1]);
      const usv_mpc::RcActuationResult mapped =
          usv_mpc::thrust_to_rc_actuation(thrust_vec, limits_.rc);
      continuity_anchor_n_ = {mapped.effective_thrust(0), mapped.effective_thrust(1)};
      last_commanded_n_ = chk.clamped_control;
      last_steering_pwm_ = mapped.steering_pwm;
      last_throttle_pwm_ = mapped.throttle_pwm;
      consecutive_solver_failures_ = 0;
      ++actuation_count_;

      res.accepted = true;
      res.solve_latency_ns = chk.solve_latency_ns;
      res.emit_action = true;
      res.action.directive = OutputDirective::ThrustPwm;
      res.action.steering_pwm = mapped.steering_pwm;
      res.action.throttle_pwm = mapped.throttle_pwm;
      res.action.epoch = control_epoch_;
      res.action.commanded_n = last_commanded_n_;
      res.action.effective_n = continuity_anchor_n_;
      res.action.control_source = "candidate";
      return res;
    }

    ++consecutive_solver_failures_;
    last_solve_error_ = chk.reason;
    res.accepted = false;
    res.reason = chk.reason;
    res.solve_latency_ns = chk.solve_latency_ns;

    if (consecutive_solver_failures_ >= limits_.solver_hold_threshold) {
      res.emit_action = true;
      res.action = enter_failsafe("solver_failure_threshold:" + chk.reason, /*terminal=*/false, now_ns);
      return res;
    }

    // 未达失败阈值：按速率边界受控向零推力坡降，并按整数 PWM 反算锚点保证下一拍 ΔT 一致
    const double max_step = limits_.nav.rho_n_s * (limits_.nav.tick_period_ns / 1e9);
    std::array<double, 2> ramped{};
    for (int i = 0; i < 2; ++i) {
      const double cur = continuity_anchor_n_[static_cast<std::size_t>(i)];
      if (std::abs(cur) <= max_step) ramped[static_cast<std::size_t>(i)] = 0.0;
      else ramped[static_cast<std::size_t>(i)] = cur > 0.0 ? cur - max_step : cur + max_step;
    }
    const usv_mpc::RcActuationResult mapped = usv_mpc::thrust_to_rc_actuation(
        Eigen::Vector2d(ramped[0], ramped[1]), limits_.rc);
    continuity_anchor_n_ = {mapped.effective_thrust(0), mapped.effective_thrust(1)};
    last_commanded_n_ = ramped;
    last_steering_pwm_ = mapped.steering_pwm;
    last_throttle_pwm_ = mapped.throttle_pwm;

    res.emit_action = true;
    res.action.directive = OutputDirective::ThrustPwm;
    res.action.steering_pwm = mapped.steering_pwm;
    res.action.throttle_pwm = mapped.throttle_pwm;
    res.action.epoch = control_epoch_;
    res.action.commanded_n = last_commanded_n_;
    res.action.effective_n = continuity_anchor_n_;
    res.action.control_source = "ramp_zero_single_miss";
    res.action.reason = chk.reason;
    return res;
  }

  /// 生成与 mode_manager_node 完全兼容的 /mpc/status JSON 载荷。
  Json mpc_status_json() const {
    Json j = Json::object();
    const bool is_hold = (exec_state_ == ExecuteState::FaultFailsafe ||
                          exec_state_ == ExecuteState::TerminalFailed);
    j["state"] = exec_state_ == ExecuteState::Active ? "ACTIVE"
                                                     : (is_hold ? "HOLD" : "STANDBY");
    j["success"] = (exec_state_ == ExecuteState::Active && consecutive_solver_failures_ == 0);
    j["fail_count"] = is_hold ? std::max(consecutive_solver_failures_, limits_.solver_hold_threshold)
                              : consecutive_solver_failures_;
    j["solve_time_ms"] = last_backend_ms_;
    j["hold"] = is_hold;
    j["control_mode"] = "dynamic";
    j["backend"] = "acados";
    j["allowed_fcu_modes"] = limits_.allowed_fcu_modes;
    j["armed"] = state_.seen ? Json(state_.armed) : Json(false);
    j["fcu_mode"] = state_.seen ? Json(state_.mode) : Json("");
    j["tl_n"] = continuity_anchor_n_[0];
    j["tr_n"] = continuity_anchor_n_[1];
    j["tl_cmd_n"] = last_commanded_n_[0];
    j["tr_cmd_n"] = last_commanded_n_[1];
    j["steering_pwm"] = last_steering_pwm_;
    j["throttle_pwm"] = last_throttle_pwm_;
    j["actuation_anchor_source"] = "rc_override_quantized_eff";
    j["anchor_modeled"] = true;
    j["hardware_receipt_verified"] = false;
    j["standby_reason"] = exec_state_ == ExecuteState::Active
                              ? std::string()
                              : (!fault_reason_.empty() ? fault_reason_ : standby_reason_);
    if (!last_solve_error_.empty() && consecutive_solver_failures_ > 0) {
      j["error"] = last_solve_error_;
    }
    return j;
  }

  Json status_snapshot(std::int64_t now_ns) const {
    Json out = dry_.status_json(now_ns);
    out["exec_state"] = state_name(exec_state_);
    out["control_epoch"] = control_epoch_;
    out["continuity_anchor_n"] = continuity_anchor_n_;
    out["last_commanded_n"] = last_commanded_n_;
    out["steering_pwm"] = last_steering_pwm_;
    out["throttle_pwm"] = last_throttle_pwm_;
    out["consecutive_solver_failures"] = consecutive_solver_failures_;
    out["preemptions_total"] = preemptions_total_;
    out["failsafes_total"] = failsafes_total_;
    out["actuation_count"] = actuation_count_;
    out["standby_reason"] = standby_reason_;
    out["fault_reason"] = fault_reason_;
    out["physical_output_enabled"] = (actuation_count_ > 0 || exec_state_ == ExecuteState::Active);
    out["water_execution_allowed"] = limits_.water_execution_allowed;
    out["anchor_source"] = "rc_override_quantized_eff";
    out["anchor_modeled"] = true;
    out["hardware_receipt_verified"] = false;
    return out;
  }

  static const char * state_name(ExecuteState s) {
    switch (s) {
      case ExecuteState::Starting: return "starting";
      case ExecuteState::Standby: return "standby";
      case ExecuteState::Active: return "active";
      case ExecuteState::FaultFailsafe: return "fault_failsafe";
      case ExecuteState::TerminalFailed: return "terminal_failed";
    }
    return "unknown";
  }

 private:
  bool is_allowed_mode(const std::string & mode) const {
    return std::find(limits_.allowed_fcu_modes.begin(), limits_.allowed_fcu_modes.end(), mode) !=
           limits_.allowed_fcu_modes.end();
  }

  bool worker_capability_ok(std::int64_t now_ns) const {
    if (!capability_.seen || !capability_valid_) return false;
    if (capability_.fatal || !capability_.model_runtime_ready) return false;
    if (now_ns <= 0 || capability_.lease_last_ns <= 0) return false;
    return now_ns - capability_.lease_last_ns <= limits_.capability_age_ns;
  }

  std::string execution_nav_gate(std::int64_t now_ns) const {
    const std::string base = dry_.nav_gate(now_ns);
    if (base != "ready") return base;
    if (last_path_receipt_ns_ <= 0 || (now_ns - last_path_receipt_ns_ > limits_.path_age_ns)) {
      return "path_stale";
    }
    return "ready";
  }

  std::string standby_reason_locked(std::int64_t now_ns) const {
    if (require_mode_exit_or_disarm_) return "fault_latched_wait_exit_manual:" + fault_reason_;
    if (!state_.seen || !state_.connected) return "waiting_fcu";
    if (!state_.armed) return "disarmed";
    if (!is_allowed_mode(state_.mode)) return "wrong_mode:" + state_.mode;
    return execution_nav_gate(now_ns);
  }

  bool neutral_pending(std::int64_t now_ns) const {
    if (neutral_hold_completed_) return false;
    return (now_ns - failsafe_entered_ns_) < limits_.neutral_hold_ns_before_release;
  }

  ActuationAction transition_to_standby_release(
      const std::string & reason, const char * source) {
    exec_state_ = ExecuteState::Standby;
    ++control_epoch_;
    continuity_anchor_n_ = {0.0, 0.0};
    last_commanded_n_ = {0.0, 0.0};
    last_steering_pwm_ = 0;
    last_throttle_pwm_ = 0;
    consecutive_solver_failures_ = 0;
    standby_reason_ = reason;
    ActuationAction act;
    act.directive = OutputDirective::Release;
    act.control_source = source;
    act.reason = reason;
    act.epoch = control_epoch_;
    return act;
  }

  ActuationAction enter_failsafe(const std::string & reason, bool terminal, std::int64_t now_ns) {
    const bool already_failsafe =
        (exec_state_ == ExecuteState::FaultFailsafe || exec_state_ == ExecuteState::TerminalFailed);
    if (fault_reason_.empty()) fault_reason_ = reason;
    if (terminal && terminal_failure_reason_.empty()) terminal_failure_reason_ = reason;
    terminal_fault_ = terminal_fault_ || terminal;
    if (already_failsafe) {
      ActuationAction noop;
      noop.epoch = control_epoch_;
      noop.hold_flag = true;
      noop.reason = fault_reason_;
      return noop;
    }
    ++failsafes_total_;
    ++control_epoch_;
    continuity_anchor_n_ = {0.0, 0.0};
    last_commanded_n_ = {0.0, 0.0};
    consecutive_solver_failures_ = 0;
    exec_state_ = ExecuteState::FaultFailsafe;
    failsafe_entered_ns_ = now_ns;
    const bool need_hold_window =
        state_.seen && state_.connected && state_.armed && is_allowed_mode(state_.mode);
    require_mode_exit_or_disarm_ = need_hold_window;
    neutral_hold_completed_ = !need_hold_window;
    ActuationAction act;
    if (!neutral_hold_completed_) {
      act.directive = OutputDirective::NeutralPwm;
      act.steering_pwm = limits_.rc.pwm_center;
      act.throttle_pwm = limits_.rc.pwm_center;
      act.request_fcu_hold = true;
      act.control_source = "failsafe_neutral_hold";
    } else {
      act.directive = OutputDirective::Release;
      act.control_source = "failsafe_release";
    }
    act.hold_flag = true;
    act.epoch = control_epoch_;
    act.reason = fault_reason_;
    last_steering_pwm_ = act.steering_pwm;
    last_throttle_pwm_ = act.throttle_pwm;
    return act;
  }

  ExecuteLimits limits_{};
  p1_dry_run::DryRunCoordinator dry_{};
  p1_shipboard::StateFacts state_{};
  p1_shipboard::CapabilityFacts capability_{};
  p1_shipboard::WorkerFacts worker_{};
  bool capability_valid_ = false;
  std::int64_t start_ns_ = 0;
  std::int64_t last_path_receipt_ns_ = 0;

  ExecuteState exec_state_ = ExecuteState::Starting;
  std::uint64_t control_epoch_ = 0;
  std::array<double, 2> continuity_anchor_n_{0.0, 0.0};
  std::array<double, 2> last_commanded_n_{0.0, 0.0};
  int last_steering_pwm_ = 0;
  int last_throttle_pwm_ = 0;
  int consecutive_solver_failures_ = 0;
  double last_backend_ms_ = 0.0;
  std::int64_t last_solve_latency_ns_ = -1;
  std::string last_solve_error_;

  bool reset_warmstart_next_ = true;
  bool require_mode_exit_or_disarm_ = false;
  bool terminal_fault_ = false;
  bool neutral_hold_completed_ = false;
  bool stop_requested_ = false;
  std::int64_t failsafe_entered_ns_ = 0;
  std::string standby_reason_ = "starting";
  std::string fault_reason_;
  std::string terminal_failure_reason_;

  std::uint64_t preemptions_total_ = 0;
  std::uint64_t failsafes_total_ = 0;
  std::uint64_t actuation_count_ = 0;
};

}  // namespace p1_execute
