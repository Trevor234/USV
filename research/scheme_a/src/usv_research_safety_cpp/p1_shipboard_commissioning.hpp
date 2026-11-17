// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// 实船调试服务接管的有限状态与输入元数据。
//
// 本文件是 **ROS-free** 的：所有 ROS 消息在 regulator.cpp 里被压成下面的原始
// 标量/字符串再喂进来，因此状态机可以用注入的整数单调时钟做确定性反证，
// 不需要 DDS、串口或飞控。
//
// 它证明的是"服务接管 + 真实输入被观测"，**不是** 执行资格：
// physical_output_enabled / control_inputs_verified / closed_loop_verified 恒为
// false，且没有任何代码路径可以在这里把它们写成 true。
#pragma once

#include <cstdint>
#include <limits>
#include <map>
#include <string>
#include <vector>
#include <nlohmann/json.hpp>

namespace p1_shipboard {

using Json = nlohmann::json;

inline constexpr const char * status_schema = "p1-shipboard-commissioning-status-v1";
inline constexpr const char * supervisor_schema = "p1-shipboard-supervisor-v1";

// 终端原因：都是"停在原地并说清楚"，没有一条能做自动恢复。
inline constexpr const char * reason_startup_timeout = "commissioning_startup_timeout";
inline constexpr const char * reason_state_timeout = "commissioning_state_timeout";
inline constexpr const char * reason_imu_timeout = "commissioning_imu_timeout";
inline constexpr const char * reason_worker_timeout = "commissioning_worker_timeout";
inline constexpr const char * reason_worker_exit = "commissioning_worker_exit";
inline constexpr const char * reason_state_disconnected = "commissioning_state_disconnected";
inline constexpr const char * reason_armed = "commissioning_armed";
inline constexpr const char * reason_wrong_mode = "commissioning_wrong_mode";
inline constexpr const char * reason_log_failed = "commissioning_log_failed";
inline constexpr const char * reason_worker_identity_changed = "commissioning_worker_identity_changed";
inline constexpr const char * reason_authorisation_expired = "commissioning_authorisation_expired";

// 有限期的现场边界。全部是合同常量或本计划明确写死的服务级阈值。
struct Limits {
  std::int64_t startup_ns = 30000000000LL;     // 30s 启动门
  std::int64_t state_age_ns = 2000000000LL;    // 就绪后 state 接收年龄
  std::int64_t imu_age_ns = 1000000000LL;      // 就绪后 IMU 接收年龄
  std::int64_t capability_age_ns = 600000000LL;  // 继承的 capability lease 上限
  std::int64_t authorisation_grace_ns = 0;     // 0 = 未绑定声明到期时刻
};

// 单路输入的事实。字段名与 status JSON 的 inputs.<key> 一一对应。
struct InputFacts {
  bool seen = false;
  std::uint64_t count = 0;
  std::int64_t receipt_ns = 0;      // CLOCK_MONOTONIC 接收时刻；0 = 从未见
  std::int64_t source_stamp_ns = 0; // 消息头时间戳原样；0 = 不存在/不可解析
  std::string frame;                // 消息实际字段，不臆造
  std::string child_frame;          // 无该字段即为空
  bool truncated = false;           // 超过 128 字节被截断
  bool has_finite = false;          // 本路是否做了有限性检查
  bool finite = false;
  bool resource_valid = false;      // 复用资源检查的结果，不等于"控制可用"
};

// capability 包被压成的原始事实。identity 由 regulator 侧比较后传入。
struct CapabilityFacts {
  bool seen = false;
  std::int64_t receipt_ns = 0;
  std::int64_t lease_last_ns = 0;
  bool model_runtime_ready = false;
  bool fault_injection_enabled = false;
  bool fatal = false;
  std::uint32_t completed_jobs = 0;
  std::uint64_t active_job = 0;
  std::uint32_t pending_count = 0;
  std::string worker_instance;
};

// worker 进程身份事实：只由 proc/pidfd 实测得来。
struct WorkerFacts {
  std::int64_t pid = 0;
  std::string instance;
  bool model_runtime_ready = false;
  bool exited = false;
};

struct StateFacts {
  bool seen = false;
  std::uint64_t count = 0;
  std::int64_t receipt_ns = 0;
  bool connected = false;
  bool armed = false;
  std::string mode;
};

// 纯状态机。所有时间都由调用者以整数单调纳秒注入。
class Monitor {
 public:
  Monitor() = default;
  explicit Monitor(const Limits & limits) : limits_(limits) {}

  // 4 个真实输入 + capability + FCU state 的更新入口。
  void on_input(const std::string & key, const InputFacts & facts) {
    if (key == "state") return;  // state 走 on_state，语义不同
    inputs_[key] = facts;
  }
  void on_state(const StateFacts & facts) { state_ = facts; }
  void on_capability(const CapabilityFacts & facts) { capability_ = facts; }
  void on_worker(const WorkerFacts & facts) { worker_ = facts; }
  void set_worker_capability_valid(bool valid) { capability_valid_ = valid; }

  // 声明到期时刻（UTC 纳秒，CLOCK_REALTIME）；0 表示不绑定。
  void set_authorisation_deadline_ns(std::int64_t utc_ns) { authorisation_deadline_ns_ = utc_ns; }

  // 首次收到真实 state 的时刻由调用方在 on_state 之前设置，用于 30s 门。
  void arm_start(std::int64_t now_ns) { start_ns_ = now_ns; }

  bool started() const { return start_ns_ != 0; }
  bool failed() const { return !failure_.empty(); }
  const std::string & failure() const { return failure_; }
  const std::string & phase() const { return phase_; }
  bool ready() const { return phase_ == "ready"; }

  // 每个采样点调用一次：推进非终态→ready，或者在任一越界时落地终端原因。
  // 一旦进入 failed 就冻结（不在同一 run 内自动恢复）。
  void evaluate(std::int64_t now_ns, std::int64_t realtime_ns) {
    if (failed()) return;
    if (worker_.exited) return fail(reason_worker_exit);
    if (state_.seen) {
      if (state_.armed) return fail(reason_armed);
      // Startup-only tolerance for MAVROS unresolved transient strings (empty before link,
      // "CMODE(...)" before autopilot capability/mode mapping completes). Must still be "HOLD"
      // to reach ready(), and any non-"HOLD" mode after ready() fails immediately.
      const bool unresolved_startup_mode =
          !ready() && (!state_.connected || state_.mode.empty() || state_.mode.rfind("CMODE(", 0) == 0);
      if (state_.connected && !unresolved_startup_mode && state_.mode != "HOLD") {
        return fail(reason_wrong_mode);
      }
    }
    if (!ready()) {
      // 启动门：30s 内必须凑齐 capability 就绪 + FCU 安全态 + 新鲜 IMU。
      if (start_ns_ != 0 && now_ns - start_ns_ > limits_.startup_ns) {
        if (!state_.seen || !state_.connected) return fail(reason_state_timeout);
        if (state_.mode != "HOLD") return fail(reason_wrong_mode);
        if (!capability_ok(now_ns)) return fail(reason_worker_timeout);
        return fail(reason_imu_timeout);
      }
      const bool fcu_ok = state_.seen && state_.connected && !state_.armed && state_.mode == "HOLD";
      if (fcu_ok && capability_ok(now_ns) && imu_fresh(now_ns)) phase_ = "ready";
      else if (!phase_started_) { phase_ = "starting"; phase_started_ = true; }
      return;
    }
    // 就绪后的持续门。
    if (!state_.seen) return fail(reason_state_timeout);
    if (!state_.connected) return fail(reason_state_disconnected);
    if (now_ns - state_.receipt_ns > limits_.state_age_ns) return fail(reason_state_timeout);
    if (!imu_fresh(now_ns)) return fail(reason_imu_timeout);
    if (!capability_ok(now_ns)) return fail(reason_worker_timeout);
    if (authorisation_deadline_ns_ != 0 && realtime_ns >= authorisation_deadline_ns_)
      return fail(reason_authorisation_expired);
  }

  // 只读快照，用于 1Hz status 与离线判据。
  Json status_json(std::int64_t now_ns, std::uint64_t seq, const Json & header) const {
    Json out = Json::object();
    out["schema"] = status_schema;
    for (auto it = header.begin(); it != header.end(); ++it) out[it.key()] = it.value();
    out["mode"] = "commissioning";
    out["seq"] = seq;
    out["at_ns"] = now_ns;
    out["phase"] = phase_.empty() ? std::string("starting") : phase_;
    out["failure_reason"] = failure_;
    // 三把锁：常量，任何状态机分支都不会把它们写成 true。
    out["physical_output_enabled"] = false;
    out["jobs_submitted"] = 0;
    out["anchor_known"] = false;
    out["control_inputs_verified"] = false;
    out["closed_loop_verified"] = false;
    out["worker"] = worker_json(now_ns);
    out["fcu"] = fcu_json();
    Json inputs = Json::object();
    for (const auto & key : keys()) inputs[key] = input_json(key, now_ns);
    out["inputs"] = inputs;
    return out;
  }

  const InputFacts & input(const std::string & key) const {
    static const InputFacts empty{};
    const auto it = inputs_.find(key);
    return it == inputs_.end() ? empty : it->second;
  }
  const StateFacts & state() const { return state_; }
  const CapabilityFacts & capability() const { return capability_; }
  const WorkerFacts & worker() const { return worker_; }
  static const std::vector<std::string> & keys() {
    static const std::vector<std::string> value{"state", "odom", "imu", "path", "profile"};
    return value;
  }

 private:
  void fail(const char * reason) {
    if (failure_.empty()) {
      failure_ = reason;
      phase_ = "failed";
    }
  }
  bool capability_ok(std::int64_t now_ns) const {
    if (!capability_.seen || !capability_valid_) return false;
    if (capability_.fatal) return false;
    if (!capability_.model_runtime_ready) return false;
    if (now_ns <= 0 || capability_.lease_last_ns <= 0) return false;
    return now_ns - capability_.lease_last_ns <= limits_.capability_age_ns;
  }
  bool imu_fresh(std::int64_t now_ns) const {
    const auto & imu = input("imu");
    if (!imu.seen || !imu.finite) return false;
    return now_ns - imu.receipt_ns <= limits_.imu_age_ns;
  }
  Json input_json(const std::string & key, std::int64_t now_ns) const {
    if (key == "state") {
      Json s = Json::object();
      s["seen"] = state_.seen;
      s["count"] = state_.count;
      s["receipt_age_ns"] = state_.seen ? Json(now_ns - state_.receipt_ns) : Json(nullptr);
      s["source_stamp_ns"] = nullptr;
      s["frame"] = nullptr;
      s["child_frame"] = nullptr;
      s["truncated"] = false;
      s["finite"] = nullptr;
      s["resource_valid"] = nullptr;
      return s;
    }
    const auto & f = input(key);
    Json s = Json::object();
    s["seen"] = f.seen;
    s["count"] = f.count;
    s["receipt_age_ns"] = f.seen ? Json(now_ns - f.receipt_ns) : Json(nullptr);
    // 未见输入一律 null：填 0 会被读成"时刻在原点"，是伪造的锚点。
    s["source_stamp_ns"] = f.source_stamp_ns > 0 ? Json(f.source_stamp_ns) : Json(nullptr);
    s["frame"] = f.seen && !f.frame.empty() ? Json(f.frame) : Json(nullptr);
    s["child_frame"] = f.seen && !f.child_frame.empty() ? Json(f.child_frame) : Json(nullptr);
    s["truncated"] = f.truncated;
    // path/profile 在本模式不做几何/时序准入：finite 明写 null，不冒充已验证。
    s["finite"] = f.has_finite ? Json(f.finite) : Json(nullptr);
    s["resource_valid"] = f.resource_valid;
    return s;
  }
  Json worker_json(std::int64_t now_ns) const {
    Json w = Json::object();
    w["pid"] = worker_.pid;
    w["instance"] = worker_.instance;
    w["model_runtime_ready"] = worker_.model_runtime_ready && capability_.model_runtime_ready;
    w["capability_age_ns"] = capability_.seen ? Json(now_ns - capability_.receipt_ns) : Json(nullptr);
    w["completed_jobs"] = capability_.completed_jobs;
    w["active_job"] = capability_.active_job;
    w["pending_count"] = capability_.pending_count;
    return w;
  }
  Json fcu_json() const {
    Json f = Json::object();
    f["seen"] = state_.seen;
    f["connected"] = state_.seen ? Json(state_.connected) : Json(nullptr);
    f["armed"] = state_.seen ? Json(state_.armed) : Json(nullptr);
    f["mode"] = state_.seen ? Json(state_.mode) : Json(nullptr);
    return f;
  }

  Limits limits_{};
  std::map<std::string, InputFacts> inputs_{};
  StateFacts state_{};
  CapabilityFacts capability_{};
  WorkerFacts worker_{};
  bool capability_valid_ = false;
  std::int64_t start_ns_ = 0;
  std::int64_t authorisation_deadline_ns_ = 0;
  bool phase_started_ = false;
  std::string phase_{};
  std::string failure_{};
};

}  // namespace p1_shipboard
