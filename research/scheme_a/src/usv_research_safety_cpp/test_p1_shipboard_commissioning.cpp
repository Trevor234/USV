// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// 实船调试服务接管的确定性反证。全部 ROS-free，时间由注入的整数单调纳秒推进。
// 这些 fixture 是**测试证据**，不是现场证据。
#include <gtest/gtest.h>

#include <fstream>
#include <string>

#include "p1_full_contract.hpp"
#include "p1_shipboard_commissioning.hpp"
#include "p1_shipboard_dry_run.hpp"

namespace {

using Json = nlohmann::json;

std::string fixture_dir() {
  const std::string file = __FILE__;
  const auto slash = file.find_last_of('/');
  return slash == std::string::npos ? std::string(".") : file.substr(0, slash);
}

Json read_json(const std::string & name) {
  std::ifstream in(fixture_dir() + "/" + name);
  if (!in) throw std::runtime_error("fixture missing: " + name);
  return Json::parse(std::string(std::istreambuf_iterator<char>(in), {}));
}

Json commissioning_contract() { return read_json("model/contract_shipboard_commissioning.json"); }
Json dry_run_contract() { return read_json("model/contract_shipboard_dry_run.json"); }

constexpr std::int64_t kSecond = 1000000000LL;

// 一份"一切都对"的基线，各用例只破坏其中一个维度。
struct Fixture {
  p1_shipboard::Monitor monitor;
  std::int64_t now = 1000 * kSecond;

  explicit Fixture(std::int64_t start = 1000 * kSecond) : now(start) {
    monitor.arm_start(start);
    p1_shipboard::StateFacts s;
    s.seen = true;
    s.count = 1;
    s.receipt_ns = start;
    s.connected = true;
    s.armed = false;
    s.mode = "HOLD";
    monitor.on_state(s);
    p1_shipboard::InputFacts imu;
    imu.seen = true;
    imu.count = 1;
    imu.receipt_ns = start;
    imu.source_stamp_ns = 5000;
    imu.frame = "base_link";
    imu.has_finite = true;
    imu.finite = true;
    imu.resource_valid = true;
    monitor.on_input("imu", imu);
    p1_shipboard::CapabilityFacts c;
    c.seen = true;
    c.receipt_ns = start;
    c.lease_last_ns = start;
    c.model_runtime_ready = true;
    c.worker_instance = "worker-1";
    monitor.on_capability(c);
    monitor.set_worker_capability_valid(true);
    p1_shipboard::WorkerFacts w;
    w.pid = 4242;
    w.instance = "worker-1";
    w.model_runtime_ready = true;
    monitor.on_worker(w);
  }
  // 让所有"接收年龄"随注入时钟一起前进，保持"刚收到"的语义。
  void advance(std::int64_t delta) {
    now += delta;
    auto s = monitor.state();
    s.receipt_ns = now;
    monitor.on_state(s);
    auto imu = monitor.input("imu");
    imu.receipt_ns = now;
    monitor.on_input("imu", imu);
    auto c = monitor.capability();
    c.receipt_ns = now;
    c.lease_last_ns = now;
    monitor.on_capability(c);
  }
};

}  // namespace

// ---------------------------------------------------------------- 合同 profile
TEST(ShipboardCommissioningContract, AcceptsOnlyTheCommissioningProfile) {
  const auto c = commissioning_contract();
  EXPECT_EQ(p1::validate_contract_fields(c), p1::ContractProfile::ShipboardCommissioning);
  EXPECT_NO_THROW(p1::validate_contract_mode(c, "commissioning"));
  // 每个非 commissioning 模式都必须被拒绝：合同不能"顺便"变成可执行。
  for (const char * mode : {"no_output", "shadow", "execute", "controlled_sim", "production"})
    EXPECT_THROW(p1::validate_contract_mode(c, mode), std::runtime_error) << mode;
}

TEST(ShipboardCommissioningContract, ExecuteIsStillLockedByB5M4) {
  const auto c = commissioning_contract();
  // 铁律：require 版对任何非 commissioning 模式都抛，且 execute 的原文保留。
  try {
    p1::require_runtime_contract_mode(c, "execute");
    FAIL() << "execute must be rejected";
  } catch (const std::runtime_error & error) {
    const std::string text = error.what();
    EXPECT_NE(text.find("profile/mode mismatch"), std::string::npos) << text;
  }
  // 用 Frozen 合同验证 B5/M4 原文仍在：execute_qualified=true 也必须被挡住。
  auto frozen = p1::candidate_baseline();
  frozen["schema"] = "p1-execution-contract-v3";
  frozen["qualification"] = "execution_frozen";
  frozen["execute_qualified"] = true;
  frozen["parameters_are_diagnostic_only"] = false;
  frozen["pending_final_calibration"] = Json::array();
  frozen["freeze_evidence_sha256"] = std::string(64, 'a');
  frozen["fault_injection_enabled"] = false;
  // v3 的字段集合**不含** diagnostic_contract_revision：带上它就是未知字段。
  frozen.erase("diagnostic_contract_revision");
  frozen["execution_contract_revision"] = 1;
  frozen["resource_contract_revision"] = 1;
  frozen["supported_parameter_profile"] = p1::contract_parameter_profile;
  EXPECT_EQ(p1::validate_contract_fields(frozen), p1::ContractProfile::Frozen);
  EXPECT_THROW(p1::require_runtime_contract_mode(frozen, "execute"), std::runtime_error);
  try {
    p1::require_runtime_contract_mode(frozen, "execute");
  } catch (const std::runtime_error & error) {
    EXPECT_NE(std::string(error.what()).find("B5/M4"), std::string::npos) << error.what();
  }
}

TEST(ShipboardCommissioningContract, RejectsFieldAndFlagTampering) {
  // 缺字段
  { auto c = commissioning_contract(); c.erase("worker_failure_policy");
    EXPECT_THROW(p1::validate_contract_fields(c), std::runtime_error); }
  // 未知字段
  { auto c = commissioning_contract(); c["output_topics"] = Json::object();
    EXPECT_THROW(p1::validate_contract_fields(c), std::runtime_error); }
  // 资格位被改
  { auto c = commissioning_contract(); c["execute_qualified"] = true;
    EXPECT_THROW(p1::validate_contract_fields(c), std::runtime_error); }
  { auto c = commissioning_contract(); c["parameters_are_diagnostic_only"] = false;
    EXPECT_THROW(p1::validate_contract_fields(c), std::runtime_error); }
  { auto c = commissioning_contract(); c["fault_injection_enabled"] = true;
    EXPECT_THROW(p1::validate_contract_fields(c), std::runtime_error); }
  // qualification 被改
  { auto c = commissioning_contract(); c["qualification"] = "execution_frozen";
    EXPECT_THROW(p1::validate_contract_fields(c), std::runtime_error); }
  // 输入话题被改（不许现场把 state 换到别处）
  { auto c = commissioning_contract(); c["input_topics"]["state"] = "/other/state";
    EXPECT_THROW(p1::validate_contract_fields(c), std::runtime_error); }
  // 类型错
  { auto c = commissioning_contract(); c["N"] = 20.5;
    EXPECT_THROW(p1::validate_contract_fields(c), std::runtime_error); }
  // 固定参数被改（参数只是诊断用，不能变成"调好的控制器"）
  { auto c = commissioning_contract(); c["Q"][0] = 1.0;
    EXPECT_THROW(p1::validate_contract_fields(c), std::runtime_error); }
  // 重复键必须由 parse_unique_contract 拒绝
  { const std::string text = "{\"schema\":\"p1-shipboard-commissioning-v1\",\"schema\":\"x\"}";
    EXPECT_THROW(p1::parse_unique_contract(text), std::runtime_error); }
}

// ------------------------------------------------------------ 有限状态机
TEST(ShipboardCommissioningMonitor, ReachesReadyWithoutOdomPathOrProfile) {
  Fixture f;
  f.monitor.evaluate(f.now, 0);
  EXPECT_TRUE(f.monitor.ready()) << f.monitor.failure();
  EXPECT_TRUE(f.monitor.failure().empty());
  // 真实缺失必须如实 not_observed，而不是补一个零值锚点。
  EXPECT_FALSE(f.monitor.input("odom").seen);
  const auto status = f.monitor.status_json(f.now, 1, Json::object());
  EXPECT_FALSE(status["control_inputs_verified"].get<bool>());
  EXPECT_FALSE(status["closed_loop_verified"].get<bool>());
  EXPECT_FALSE(status["physical_output_enabled"].get<bool>());
  EXPECT_EQ(status["jobs_submitted"].get<int>(), 0);
  EXPECT_FALSE(status["anchor_known"].get<bool>());
  EXPECT_EQ(status["inputs"]["odom"]["count"].get<std::uint64_t>(), 0U);
  EXPECT_TRUE(status["inputs"]["odom"]["seen"].get<bool>() == false);
  EXPECT_TRUE(status["inputs"]["odom"]["source_stamp_ns"].is_null());
  EXPECT_TRUE(status["inputs"]["odom"]["receipt_age_ns"].is_null());
  // 未见 state 的 fcu 三键必须是 null，不能是 false。
  auto unaware = f.monitor.status_json(f.now, 2, Json::object());
  EXPECT_TRUE(unaware["fcu"]["connected"].get<bool>() == true);
}

TEST(ShipboardCommissioningMonitor, UnseenFcuReportsNulls) {
  p1_shipboard::Monitor m;
  m.arm_start(0 + 1000 * kSecond);
  const auto status = m.status_json(1000 * kSecond, 1, Json::object());
  EXPECT_FALSE(status["fcu"]["seen"].get<bool>());
  EXPECT_TRUE(status["fcu"]["connected"].is_null());
  EXPECT_TRUE(status["fcu"]["armed"].is_null());
  EXPECT_TRUE(status["fcu"]["mode"].is_null());
}

TEST(ShipboardCommissioningMonitor, ReadyTransitionsAreTerminalAndDoNotRecover) {
  // armed
  { Fixture f; f.advance(kSecond / 10);
    auto s = f.monitor.state(); s.armed = true; s.receipt_ns = f.now; f.monitor.on_state(s);
    f.monitor.evaluate(f.now, 0);
    EXPECT_EQ(f.monitor.failure(), "commissioning_armed");
    // 恢复安全值也不再复活：同一 run 不自动恢复。
    s.armed = false; f.monitor.on_state(s); f.monitor.evaluate(f.now, 0);
    EXPECT_EQ(f.monitor.failure(), "commissioning_armed");
    EXPECT_EQ(f.monitor.phase(), std::string("failed")); }
  // 非 HOLD
  { Fixture f; f.monitor.evaluate(f.now, 0); ASSERT_TRUE(f.monitor.ready());
    auto s = f.monitor.state(); s.mode = "GUIDED"; f.monitor.on_state(s);
    f.monitor.evaluate(f.now, 0);
    EXPECT_EQ(f.monitor.failure(), "commissioning_wrong_mode"); }
  // 断链
  { Fixture f; f.monitor.evaluate(f.now, 0); ASSERT_TRUE(f.monitor.ready());
    auto s = f.monitor.state(); s.connected = false; f.monitor.on_state(s);
    f.monitor.evaluate(f.now, 0);
    EXPECT_EQ(f.monitor.failure(), "commissioning_state_disconnected"); }
  // state 2s 超龄
  { Fixture f; f.monitor.evaluate(f.now, 0); ASSERT_TRUE(f.monitor.ready());
    const auto stale = f.now;
    auto imu = f.monitor.input("imu"); imu.receipt_ns = stale + 2 * kSecond; f.monitor.on_input("imu", imu);
    auto cap = f.monitor.capability(); cap.receipt_ns = stale; cap.lease_last_ns = stale + 2 * kSecond;
    f.monitor.on_capability(cap);
    f.monitor.evaluate(stale + 2 * kSecond + 1, 0);
    EXPECT_EQ(f.monitor.failure(), "commissioning_state_timeout"); }
  // IMU 1s 超龄
  { Fixture f; f.monitor.evaluate(f.now, 0); ASSERT_TRUE(f.monitor.ready());
    f.advance(500 * 1000000LL);
    auto imu = f.monitor.input("imu"); imu.receipt_ns = f.now - 2 * kSecond; f.monitor.on_input("imu", imu);
    f.monitor.evaluate(f.now, 0);
    EXPECT_EQ(f.monitor.failure(), "commissioning_imu_timeout"); }
  // capability 600ms 超龄
  { Fixture f; f.monitor.evaluate(f.now, 0); ASSERT_TRUE(f.monitor.ready());
    f.advance(700 * 1000000LL);
    auto cap = f.monitor.capability(); cap.lease_last_ns = f.now - 700 * 1000000LL;
    f.monitor.on_capability(cap);
    f.monitor.evaluate(f.now, 0);
    EXPECT_EQ(f.monitor.failure(), "commissioning_worker_timeout"); }
  // worker 退出
  { Fixture f; f.monitor.evaluate(f.now, 0); ASSERT_TRUE(f.monitor.ready());
    auto w = f.monitor.worker(); w.exited = true; f.monitor.on_worker(w);
    f.monitor.evaluate(f.now, 0);
    EXPECT_EQ(f.monitor.failure(), "commissioning_worker_exit"); }
}

TEST(ShipboardCommissioningMonitor, StartupTimeoutNamesTheMissingPiece) {
  // 什么都没有：state 缺失优先报 state 超时。
  { p1_shipboard::Monitor m; m.arm_start(0 + 1000 * kSecond);
    m.evaluate(1000 * kSecond + 31 * kSecond, 0);
    EXPECT_EQ(m.failure(), "commissioning_state_timeout"); }
  // state 正常但 capability 未就绪。
  { p1_shipboard::Monitor m; m.arm_start(1000 * kSecond);
    p1_shipboard::StateFacts s; s.seen = true; s.count = 1; s.receipt_ns = 1000 * kSecond;
    s.connected = true; s.armed = false; s.mode = "HOLD"; m.on_state(s);
    m.evaluate(1000 * kSecond + 31 * kSecond, 0);
    EXPECT_EQ(m.failure(), "commissioning_worker_timeout"); }
  // state + capability 都好，只剩 IMU。
  { p1_shipboard::Monitor m; m.arm_start(1000 * kSecond);
    p1_shipboard::StateFacts s; s.seen = true; s.count = 1; s.receipt_ns = 1000 * kSecond;
    s.connected = true; s.armed = false; s.mode = "HOLD"; m.on_state(s);
    p1_shipboard::CapabilityFacts c; c.seen = true; c.receipt_ns = 1000 * kSecond;
    // lease 必须"当时仍新鲜"，否则先报 capability 超时才是正确行为。
    c.lease_last_ns = 1000 * kSecond + 31 * kSecond; c.model_runtime_ready = true;
    m.on_capability(c);
    m.set_worker_capability_valid(true);
    m.evaluate(1000 * kSecond + 31 * kSecond, 0);
    EXPECT_EQ(m.failure(), "commissioning_imu_timeout"); }
  // armed 在启动阶段就立刻终端，不等满 30s。
  { p1_shipboard::Monitor m; m.arm_start(1000 * kSecond);
    p1_shipboard::StateFacts s; s.seen = true; s.count = 1; s.receipt_ns = 1000 * kSecond;
    s.connected = true; s.armed = true; s.mode = "HOLD"; m.on_state(s);
    m.evaluate(1000 * kSecond + 1, 0);
    EXPECT_EQ(m.failure(), "commissioning_armed"); }
  // 启动阶段 MAVROS 尚未连通 FCU 时会先发布 connected=false, mode=""：不得误判为 wrong_mode，
  // 连通且 HOLD 后正常就绪；若 30s 仍未连通则报 commissioning_state_timeout。
  { p1_shipboard::Monitor m; m.arm_start(1000 * kSecond);
    p1_shipboard::StateFacts s; s.seen = true; s.count = 1; s.receipt_ns = 1000 * kSecond;
    s.connected = false; s.armed = false; s.mode = ""; m.on_state(s);
    p1_shipboard::InputFacts imu; imu.seen = true; imu.count = 1; imu.receipt_ns = 1000 * kSecond;
    imu.has_finite = true; imu.finite = true; imu.resource_valid = true;
    m.on_input("imu", imu);
    p1_shipboard::CapabilityFacts c; c.seen = true; c.receipt_ns = 1000 * kSecond;
    c.lease_last_ns = 1000 * kSecond + 5 * kSecond; c.model_runtime_ready = true;
    m.on_capability(c); m.set_worker_capability_valid(true);
    m.evaluate(1000 * kSecond + 2 * kSecond, 0);
    EXPECT_TRUE(m.failure().empty()) << m.failure();
    EXPECT_EQ(m.phase(), "starting");
    s.connected = true; s.mode = "HOLD"; s.receipt_ns = 1000 * kSecond + 5 * kSecond;
    imu.receipt_ns = 1000 * kSecond + 5 * kSecond;
    m.on_state(s);
    m.on_input("imu", imu);
    m.evaluate(1000 * kSecond + 5 * kSecond, 0);
    EXPECT_TRUE(m.ready()) << m.failure();
    EXPECT_TRUE(m.failure().empty()); }
  { p1_shipboard::Monitor m; m.arm_start(1000 * kSecond);
    p1_shipboard::StateFacts s; s.seen = true; s.count = 1; s.receipt_ns = 1000 * kSecond;
    s.connected = false; s.armed = false; s.mode = ""; m.on_state(s);
    m.evaluate(1000 * kSecond + 31 * kSecond, 0);
    EXPECT_EQ(m.failure(), "commissioning_state_timeout"); }
  // 启动阶段若已连通且 mode 非 HOLD，仍必须立刻失败。
  { p1_shipboard::Monitor m; m.arm_start(1000 * kSecond);
    p1_shipboard::StateFacts s; s.seen = true; s.count = 1; s.receipt_ns = 1000 * kSecond;
    s.connected = true; s.armed = false; s.mode = "MANUAL"; m.on_state(s);
    m.evaluate(1000 * kSecond + 1, 0);
    EXPECT_EQ(m.failure(), "commissioning_wrong_mode"); }
  // 启动阶段 ArduPilot/MAVROS 刚连上时可能短暂发布 connected=true, mode="CMODE(4)"：
  // 启动窗内放行等待解析为 HOLD；若 30s 仍停在 CMODE(4) 则按 wrong_mode 失败。
  { p1_shipboard::Monitor m; m.arm_start(1000 * kSecond);
    p1_shipboard::StateFacts s; s.seen = true; s.count = 1; s.receipt_ns = 1000 * kSecond + 2 * kSecond;
    s.connected = true; s.armed = false; s.mode = "CMODE(4)"; m.on_state(s);
    p1_shipboard::InputFacts imu; imu.seen = true; imu.count = 1; imu.receipt_ns = 1000 * kSecond + 2 * kSecond;
    imu.has_finite = true; imu.finite = true; imu.resource_valid = true;
    m.on_input("imu", imu);
    p1_shipboard::CapabilityFacts c; c.seen = true; c.receipt_ns = 1000 * kSecond + 2 * kSecond;
    c.lease_last_ns = 1000 * kSecond + 4 * kSecond; c.model_runtime_ready = true;
    m.on_capability(c); m.set_worker_capability_valid(true);
    m.evaluate(1000 * kSecond + 2 * kSecond, 0);
    EXPECT_TRUE(m.failure().empty()) << m.failure();
    EXPECT_FALSE(m.ready());
    s.mode = "HOLD"; s.receipt_ns = 1000 * kSecond + 3 * kSecond;
    imu.receipt_ns = 1000 * kSecond + 3 * kSecond;
    m.on_state(s); m.on_input("imu", imu);
    m.evaluate(1000 * kSecond + 3 * kSecond, 0);
    EXPECT_TRUE(m.ready()) << m.failure();
    // ready 之后若再出现 CMODE(...) 也必须立刻判错。
    s.mode = "CMODE(4)"; m.on_state(s);
    m.evaluate(1000 * kSecond + 4 * kSecond, 0);
    EXPECT_EQ(m.failure(), "commissioning_wrong_mode"); }
  { p1_shipboard::Monitor m; m.arm_start(1000 * kSecond);
    p1_shipboard::StateFacts s; s.seen = true; s.count = 1; s.receipt_ns = 1000 * kSecond;
    s.connected = true; s.armed = false; s.mode = "CMODE(4)"; m.on_state(s);
    m.evaluate(1000 * kSecond + 31 * kSecond, 0);
    EXPECT_EQ(m.failure(), "commissioning_wrong_mode"); }
}

TEST(ShipboardCommissioningMonitor, AuthorisationExpiryClosesTheRun) {
  Fixture f;
  f.monitor.set_authorisation_deadline_ns(1234);
  f.monitor.evaluate(f.now, 1233);
  EXPECT_TRUE(f.monitor.failure().empty());
  f.monitor.evaluate(f.now, 1234);
  EXPECT_EQ(f.monitor.failure(), "commissioning_authorisation_expired");
}

TEST(ShipboardCommissioningMonitor, StatusShapeMatchesTheDeclaredSchema) {
  Fixture f;
  f.monitor.evaluate(f.now, 0);
  const auto status = f.monitor.status_json(f.now, 7, Json{{"run_id", "r"}, {"boot_id", "b"},
                                                            {"host_boot_id", "h"},
                                                            {"contract_hash", "c"},
                                                            {"plan_sha256", "p"}});
  EXPECT_EQ(status["schema"].get<std::string>(), "p1-shipboard-commissioning-status-v1");
  EXPECT_EQ(status["seq"].get<std::uint64_t>(), 7U);
  EXPECT_EQ(status["mode"].get<std::string>(), "commissioning");
  EXPECT_TRUE(status["failure_reason"].get<std::string>().empty());
  for (const char * key : {"run_id", "boot_id", "host_boot_id", "contract_hash", "plan_sha256",
                           "phase", "at_ns", "worker", "fcu", "inputs"})
    EXPECT_TRUE(status.contains(key)) << key;
  for (const char * key : {"pid", "instance", "model_runtime_ready", "capability_age_ns",
                           "completed_jobs", "active_job", "pending_count"})
    EXPECT_TRUE(status["worker"].contains(key)) << key;
  for (const char * key : {"seen", "count", "receipt_age_ns", "source_stamp_ns", "frame",
                           "child_frame", "truncated", "finite", "resource_valid"})
    EXPECT_TRUE(status["inputs"]["imu"].contains(key)) << key;
  for (const char * key : {"state", "odom", "imu", "path", "profile"})
    EXPECT_TRUE(status["inputs"].contains(key)) << key;
  // 本模式永远不声称闭环/物理资格。
  EXPECT_FALSE(status["closed_loop_verified"].get<bool>());
  EXPECT_FALSE(status["physical_output_enabled"].get<bool>());
}

TEST(ShipboardDryRunContract, AcceptsOnlyDryRunModeAndRejectsTampering) {
  const auto c = dry_run_contract();
  EXPECT_EQ(p1::validate_contract_fields(c), p1::ContractProfile::ShipboardDryRun);
  EXPECT_NO_THROW(p1::validate_contract_mode(c, "shipboard_dry_run"));
  EXPECT_NO_THROW(p1::require_runtime_contract_mode(c, "shipboard_dry_run"));
  for (const char * mode : {"commissioning", "no_output", "shadow", "execute", "controlled_sim"})
    EXPECT_THROW(p1::validate_contract_mode(c, mode), std::runtime_error) << mode;

  { auto bad = c; bad["execute_qualified"] = true;
    EXPECT_THROW(p1::validate_contract_fields(bad), std::runtime_error); }
  { auto bad = c; bad["parameters_are_diagnostic_only"] = false;
    EXPECT_THROW(p1::validate_contract_fields(bad), std::runtime_error); }
  { auto bad = c; bad["fault_injection_enabled"] = true;
    EXPECT_THROW(p1::validate_contract_fields(bad), std::runtime_error); }
  { auto bad = c; bad["output_topics"] = Json{{"left", "/wamv/thrusters/left/thrust"}};
    EXPECT_THROW(p1::validate_contract_fields(bad), std::runtime_error); }
  { auto bad = c; bad["expected_child_frame"] = "wamv/base_link";
    EXPECT_THROW(p1::validate_contract_fields(bad), std::runtime_error); }
  { auto bad = c; bad["worker_capability_receipt_timeout_ns"] = 50000000LL;
    EXPECT_THROW(p1::validate_contract_fields(bad), std::runtime_error); }
  { auto bad = c; bad["Q"][0] = 999.0;
    EXPECT_THROW(p1::validate_contract_fields(bad), std::runtime_error); }
}

TEST(ShipboardDryRunCoordinator, NavGateAndCandidateChecksHoldPhysicalLocksFalse) {
  const auto c = dry_run_contract();
  p1_dry_run::DryRunCoordinator coord(p1_dry_run::limits_from_contract(c));
  const std::int64_t t0 = 2000 * kSecond;
  coord.arm(t0);
  EXPECT_EQ(coord.nav_gate(t0), "waiting_odom");

  p1_dry_run::OdomFacts od;
  od.seen = true; od.valid = true; od.finite = true;
  od.pose_frame = "map"; od.child_frame = "base_link";
  od.seq = 1; od.receipt_ns = t0; od.stamp_ns = 1790000000000000000LL;
  od.state = {1.0, 2.0, 0.3, 0.5, 0.0, 0.1};
  coord.on_odom(od);
  EXPECT_EQ(coord.nav_gate(t0), "waiting_imu");

  p1_dry_run::ImuFacts im;
  im.seen = true; im.valid = true; im.finite = true;
  im.frame = "base_link"; im.seq = 1; im.receipt_ns = t0; im.stamp_ns = od.stamp_ns;
  im.r = 0.25;
  coord.on_imu(im);
  EXPECT_EQ(coord.nav_gate(t0), "waiting_path");

  p1_dry_run::PathFacts pf;
  pf.seen = true; pf.resource_valid = true; pf.frame = "map"; pf.seq = 1;
  pf.receipt_ns = t0; pf.stamp_ns = od.stamp_ns; pf.points = 10;
  coord.on_path(pf);
  EXPECT_EQ(coord.nav_gate(t0), "waiting_profile");

  p1_dry_run::ProfileFacts prf;
  prf.seen = true; prf.resource_valid = true; prf.seq = 1;
  prf.receipt_ns = t0; prf.stamp_ns = od.stamp_ns; prf.rows = 10;
  prf.stamp_ok = true; prf.path_profile_sync_ok = false; prf.sync_reason = "skew";
  coord.on_profile(prf);
  EXPECT_EQ(coord.nav_gate(t0), "profile_sync_mismatch");

  coord.set_profile_sync(true, "");
  EXPECT_EQ(coord.nav_gate(t0), "ready");
  EXPECT_DOUBLE_EQ(coord.composed_state()[5], 0.25);

  // Stale odom blocks without asserting hardware ready.
  EXPECT_EQ(coord.nav_gate(t0 + c["odom_age_ns"].get<std::int64_t>() + 1), "odom_stale");

  // Valid candidate updates internal nominal continuity while keeping hardware locks false.
  p1_dry_run::CandidateFacts cf;
  cf.job_id = 1; cf.tick = 1;
  cf.worker_instance = "w1"; cf.expected_worker_instance = "w1"; cf.backend = "acados";
  cf.echo_matched = true; cf.success = true; cf.prediction_available = true; cf.solver_invoked = true;
  cf.finite = true; cf.backend_ms = 1.2; cf.first_control = {10.0, 10.0};
  cf.initial_control_matches = true; cf.initial_state_matches = true;
  cf.freeze_steady_ns = t0; cf.worker_receive_ns = t0 + 100000;
  cf.solve_start_ns = t0 + 200000; cf.solve_end_ns = t0 + 1500000;
  cf.deadline_steady_ns = t0 + 150000000LL; cf.receive_ns = t0 + 2000000;
  const auto ok_out = coord.evaluate_candidate(cf);
  EXPECT_TRUE(ok_out.accepted) << ok_out.reason;
  EXPECT_DOUBLE_EQ(coord.nominal_continuity_n()[0], 10.0);

  // Rate jump > 16 N / 0.2s (= 80 N/s) must be rejected without corrupting nominal continuity.
  auto bad_rate = cf; bad_rate.job_id = 2; bad_rate.first_control = {-10.0, -10.0};
  const auto rate_out = coord.evaluate_candidate(bad_rate);
  EXPECT_FALSE(rate_out.accepted);
  EXPECT_EQ(rate_out.reason, "rate_limit_exceeded");
  EXPECT_DOUBLE_EQ(coord.nominal_continuity_n()[0], 10.0);

  // Deadline exceeded must be rejected.
  auto bad_deadline = cf; bad_deadline.job_id = 3; bad_deadline.first_control = {12.0, 12.0};
  bad_deadline.solve_end_ns = bad_deadline.deadline_steady_ns + 1;
  bad_deadline.receive_ns = bad_deadline.solve_end_ns + 1000;
  const auto late_out = coord.evaluate_candidate(bad_deadline);
  EXPECT_FALSE(late_out.accepted);
  EXPECT_EQ(late_out.reason, "deadline_exceeded");

  const auto st = coord.status_json(t0);
  EXPECT_EQ(st["candidates_accepted"].get<int>(), 1);
  EXPECT_EQ(st["candidates_rejected"].get<int>(), 2);
  EXPECT_FALSE(st["physical_output_enabled"].get<bool>());
  EXPECT_FALSE(st["closed_loop_verified"].get<bool>());
  EXPECT_FALSE(st["control_inputs_verified"].get<bool>());
  EXPECT_FALSE(st["anchor_known"].get<bool>());
}
