// SPDX-License-Identifier: MIT
//
// Backend-boundary tests that actually hit the registered boundary.
//
// The previous suite's "success" test bound the gate to Job 2 but only ran
// Job 1, so it exercised the non-matching path and would still pass with the
// whole wiring block deleted. These tests drive the *target* Job and ordinal
// through owned_cold::Backend::solve_owned, and the runner mutates the wiring
// block away to prove they notice.
#include <cstdint>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

#include <gtest/gtest.h>
#include <nlohmann/json.hpp>

#include "owned_cold_backend.hpp"
#include "w2_native_boundary.hpp"

// Test-only link adapters. The real preparation and C solve still execute;
// only the controlled stop/clock transition or return status is injected.
namespace w2_test_probe {
std::function<void()> preparation;
unsigned calls = 0;
int forced_status = 0;
struct Scope {
  explicit Scope(std::function<void()> fn = {}) {
    preparation = std::move(fn); calls = 0; forced_status = 0;
  }
  ~Scope() { preparation = {}; forced_status = 0; }
};
}
extern "C" int __real_usv_dyn_nmpc_acados_update_params(
    usv_dyn_nmpc_solver_capsule *, int, double *, int);
extern "C" int __wrap_usv_dyn_nmpc_acados_update_params(
    usv_dyn_nmpc_solver_capsule *capsule, int stage, double *values, int count) {
  const int status = __real_usv_dyn_nmpc_acados_update_params(capsule, stage, values, count);
  auto action = std::move(w2_test_probe::preparation);
  w2_test_probe::preparation = {};
  if (action) action();
  return status;
}
extern "C" int __real_usv_dyn_nmpc_acados_solve(usv_dyn_nmpc_solver_capsule *);
extern "C" int __wrap_usv_dyn_nmpc_acados_solve(usv_dyn_nmpc_solver_capsule *capsule) {
  ++w2_test_probe::calls;
  const int actual = __real_usv_dyn_nmpc_acados_solve(capsule);
  return w2_test_probe::forced_status ? w2_test_probe::forced_status : actual;
}

namespace {

using Json = nlohmann::json;
using w2_gate::Gate;
using w2_gate::Identity;
using w2_wire::Boundary;
using w2_wire::BoundaryConfig;
using w2_wire::Disposition;

constexpr int64_t kTargetJob = 1;   // the cold-start Job: the only one armed
constexpr uint32_t kTargetOrdinal = 1;
constexpr int64_t kStartNs = 1000000000;

/// Delivers one frame when asked, and can advance a shared clock as it does.
class ControlledReader final : public w2_gate::Reader {
 public:
  ControlledReader(Identity id, int64_t * clock, int64_t advance_ns)
  : id_(id), clock_(clock), advance_(advance_ns) {}

  long read_some(uint8_t * buf, size_t n, int64_t, int64_t * elapsed) override {
    if (delivered_) {
      if (elapsed) *elapsed = advance_;
      if (clock_) *clock_ += advance_;
      return -1;
    }
    delivered_ = true;
    uint8_t frame[w2_gate::kFrameBytes];
    w2_gate::encode_release(frame, id_);
    const size_t take = std::min(n, w2_gate::kFrameBytes);
    std::memcpy(buf, frame, take);
    // Advancing here is what makes the release "arrive late": the gate sees a
    // frame, but the clock has crossed the Job deadline while it waited.
    if (clock_) *clock_ += advance_;
    if (elapsed) *elapsed = advance_;
    return long(take);
  }

 private:
  Identity id_;
  int64_t * clock_;
  int64_t advance_;
  bool delivered_ = false;
};

/// A Job that satisfies the cold-start policy so the target Job really arms.
Json target_job(int64_t job_id, int64_t deadline_ns) {
  Json j;
  j["schema"] = "p1-solve-job-v1";
  j["run_id"] = "w2_backend_test";
  j["boot_id"] = "boot";
  j["contract_hash"] = std::string(64, 'a');
  j["nominal_hash"] = std::string(64, 'b');
  j["worker_instance"] = "instance";
  j["config_generation"] = 1;
  j["model_generation"] = 1;
  j["task_generation"] = 1;
  j["schedule_generation"] = 1;
  j["clock_epoch"] = 0;
  j["job_id"] = job_id;
  j["N"] = 20;
  j["dt"] = 0.2;
  j["deadline_ns"] = deadline_ns;
  j["target_state"] = std::vector<double>{0, 0, 0, 0, 0, 0};
  j["frozen_state"] = std::vector<double>{0, 0, 0, 0, 0, 0};
  j["anchor_n"] = std::vector<double>{0, 0};
  j["anchor_known"] = std::vector<bool>{true, true};
  j["reset_warmstart"] = false;
  std::vector<double> ref(126);
  for (int k = 0; k <= 20; ++k) {
    ref[6 * k + 0] = 0.05 * 0.2 * k;
    ref[6 * k + 3] = 0.05;
  }
  j["reference"] = ref;
  return j;
}

usv_mpc::MpcParams params() {
  usv_mpc::MpcParams p;
  p.dt = 0.2;
  p.N = 20;
  return p;
}

Json binding() {
  return Json{{"run_id", "w2_backend_test"}, {"boot_id", "boot"},
              {"contract_hash", std::string(64, 'a')},
              {"nominal_hash", std::string(64, 'b')},
              {"worker_instance", "instance"}};
}

/// One armed boundary plus the clock it shares with the backend.
struct Armed {
  Armed(int64_t deadline_ns, int64_t advance_ns, int64_t budget_ns = 1000000000)
  : reader(identity(), &clock, advance_ns), gate(&reader, identity(), budget_ns) {
    cfg.job_id = kTargetJob;
    cfg.ordinal = kTargetOrdinal;
    cfg.job_deadline_ns = deadline_ns;
    cfg.wait_budget_ns = budget_ns;
    boundary = Boundary(&gate, cfg, [this] { return clock; });
    boundary.set_clock([this] { return clock; });
    boundary.set_current_job(kTargetJob);
    backend = std::make_unique<owned_cold::Backend>(
        params(), binding(), true, [this] { return clock; });
    backend->attach_boundary(&boundary, [] { return false; });
  }

  static Identity identity() {
    return Identity{1, uint64_t(kTargetJob), kTargetOrdinal, 0x77};
  }

  int64_t clock = kStartNs;
  ControlledReader reader;
  Gate gate;
  BoundaryConfig cfg;
  Boundary boundary;
  std::unique_ptr<owned_cold::Backend> backend;
};

}  // namespace

TEST(W2Backend, TimelyReleaseOnTheTargetBoundaryEntersTheNativeCall) {
  // Target Job, target ordinal, release inside the deadline: the call must
  // actually happen, and both the Boundary and the policy JSON must say so.
  Armed a(/*deadline=*/kStartNs + 1000000000, /*advance=*/1000000);
  a.backend->set_applied_control(Eigen::Vector2d::Zero());
  EXPECT_NO_THROW(a.backend->solve_owned(target_job(kTargetJob, a.cfg.job_deadline_ns)));

  const auto &rec = a.boundary.record();
  EXPECT_EQ(rec.disposition, Disposition::kAllowed);
  EXPECT_TRUE(rec.actual_native_invoked);
  EXPECT_EQ(rec.ordinal_at_call, kTargetOrdinal);
  // The policy snapshot must agree with the Boundary: the snapshot is taken
  // after the boundary finishes updating, not before.
  const auto policy = a.backend->w2_boundary_event();
  EXPECT_TRUE(policy.at("actual_native_invoked").get<bool>());
  EXPECT_EQ(policy.at("disposition").get<std::string>(), "allowed");
}

TEST(W2Backend, ReleaseAfterTheJobDeadlineNeverStartsTheNativeCall) {
  // Initial guard passes (clock starts well before the deadline); the reader
  // then advances past it while the gate waits. The release is verified, the
  // boundary expires, and the target Job's native entries stay at zero.
  const int64_t deadline = kStartNs + 150000000;
  Armed a(deadline, /*advance=*/200000000);  // advances 200 ms inside the wait
  a.backend->set_applied_control(Eigen::Vector2d::Zero());
  EXPECT_THROW(a.backend->solve_owned(target_job(kTargetJob, deadline)),
               std::runtime_error);

  const auto &rec = a.boundary.record();
  EXPECT_EQ(rec.disposition, Disposition::kExpired);
  EXPECT_TRUE(rec.released);              // the frame really arrived
  EXPECT_GT(rec.past_deadline_ns, 0);     // and the Job really was late
  EXPECT_FALSE(rec.actual_native_invoked);  // the C call never started
  const auto policy = a.backend->last_policy_event();
  EXPECT_EQ(policy.at("backend_entries_started").get<unsigned>(), 0u);
  EXPECT_EQ(policy.at("backend_entries_completed").get<unsigned>(), 0u);
  EXPECT_TRUE(a.backend->terminal());
}

TEST(W2Backend, ReleaseExactlyAtTheDeadlineIsStillAllowed) {
  // The guard is `>`, so landing exactly on the deadline is still inside it.
  // Pin it through the real backend, not only through Boundary.
  const int64_t deadline = kStartNs + 150000000;
  Armed a(deadline, /*advance=*/150000000);  // arrives exactly at the deadline
  a.backend->set_applied_control(Eigen::Vector2d::Zero());
  EXPECT_NO_THROW(a.backend->solve_owned(target_job(kTargetJob, deadline)));
  EXPECT_EQ(a.boundary.record().disposition, Disposition::kAllowed);
  EXPECT_TRUE(a.boundary.record().actual_native_invoked);
}

TEST(W2Backend, StopRaisedDuringPreparationBlocksTheNativeCall) {
  // D4: the final guard must run after preparation and immediately before the
  // real C entry. A stop that arrives *after* the boundary released but during
  // RawBackend preparation must still keep the call from starting; a guard that
  // only checked at the boundary would miss it.
  const int64_t deadline = kStartNs + 1000000000;
  Armed a(deadline, /*advance=*/1000000);
  bool stop = false;
  a.backend->attach_boundary(&a.boundary, [&] { return stop; });
  w2_test_probe::Scope probe([&] { stop = true; a.clock += 2000000; });
  a.backend->set_applied_control(Eigen::Vector2d::Zero());
  EXPECT_THROW(a.backend->solve_owned(target_job(kTargetJob, deadline)),
               std::runtime_error);
  EXPECT_EQ(a.boundary.record().disposition, Disposition::kStopped);
  EXPECT_TRUE(a.boundary.record().released);
  EXPECT_EQ(w2_test_probe::calls, 0u);
  EXPECT_FALSE(a.boundary.record().actual_native_invoked);
  EXPECT_EQ(a.backend->last_policy_event().at("backend_entries_completed")
                .get<unsigned>(), 0u);
}

TEST(W2Backend, DeadlineCrossedDuringPreparationBlocksTheNativeCall) {
  // Same window, expiry instead of stop: the guard must use the clock *at the
  // real entry*, not the value captured when the boundary was released.
  const int64_t deadline = kStartNs + 1000000000;
  Armed a(deadline, /*advance=*/1000000);
  w2_test_probe::Scope probe([&] { a.clock = deadline + 1; });
  a.backend->set_applied_control(Eigen::Vector2d::Zero());
  EXPECT_THROW(a.backend->solve_owned(target_job(kTargetJob, deadline)),
               std::runtime_error);
  EXPECT_EQ(a.boundary.record().disposition, Disposition::kExpired);
  EXPECT_TRUE(a.boundary.record().released);
  EXPECT_EQ(w2_test_probe::calls, 0u);
  EXPECT_FALSE(a.boundary.record().actual_native_invoked);
  EXPECT_EQ(a.backend->last_policy_event().at("backend_entries_completed")
                .get<unsigned>(), 0u);
}

TEST(W2Backend, ANonTargetJobStillObeysStopAndDeadline) {
  // E3: `matches` gates only the extra release wait. A Job that is not the
  // registered target must still respect its own stop state and its original
  // deadline — otherwise a stopped or expired run keeps solving other Jobs.
  const int64_t deadline = kStartNs + 1000000000;
  Armed a(deadline, /*advance=*/1000000);
  bool stop = false;
  a.backend->attach_boundary(&a.boundary, [&] { return stop; });
  w2_test_probe::Scope probe([&] { stop = true; });
  a.backend->set_applied_control(Eigen::Vector2d::Zero());
  // Job 2 is not the armed target (Job 1 / ordinal 1).
  // The deadline check that rejects this sits before the solve's try block, so
  // the backend is not marked terminal; the observable fact is the refusal
  // itself, which is what "never entered C" means here.
  EXPECT_THROW(a.backend->solve_owned(target_job(2, deadline)), std::runtime_error);
  EXPECT_EQ(w2_test_probe::calls, 0u);
}

TEST(W2Backend, ANonTargetJobStillObeysItsOwnDeadline) {
  // A Job that is not the registered target still must not enter C past its own
  // deadline. The clock is already past it when the solve starts, which is the
  // "arrived late" case rather than a preparation-window race.
  const int64_t deadline = kStartNs + 1000000000;
  Armed a(deadline, /*advance=*/1000000);
  w2_test_probe::Scope probe([&] { a.clock = deadline + 1; });
  a.backend->set_applied_control(Eigen::Vector2d::Zero());
  // The deadline check that rejects this sits before the solve's try block, so
  // the backend is not marked terminal; the observable fact is the refusal
  // itself, which is what "never entered C" means here.
  EXPECT_THROW(a.backend->solve_owned(target_job(2, deadline)), std::runtime_error);
  EXPECT_EQ(w2_test_probe::calls, 0u);
}

TEST(W2Backend, ARefusedGuardStillPublishesTheBoundaryFact) {
  // E4: when the final guard refuses after preparation, the observer never ran
  // and step never returned, so the catch is the only place that can publish the
  // disposition. Without it the policy would omit w2_boundary entirely and a
  // downstream reader would have to infer "not called" from a missing field.
  const int64_t deadline = kStartNs + 1000000000;
  Armed a(deadline, /*advance=*/1000000);
  bool stop = false;
  // Re-attach so the guard reads the flag rather than the fixture's constant
  // `false` predicate.
  a.backend->attach_boundary(&a.boundary, [&] { return stop; });
  w2_test_probe::Scope probe([&] { stop = true; a.clock += 2000000; });
  a.backend->set_applied_control(Eigen::Vector2d::Zero());
  EXPECT_THROW(a.backend->solve_owned(target_job(kTargetJob, deadline)),
               std::runtime_error);
  const auto policy = a.backend->last_policy_event();
  ASSERT_TRUE(policy.contains("w2_boundary"))
      << "a refused guard must still publish the boundary disposition";
  EXPECT_EQ(policy.at("w2_boundary").at("disposition").get<std::string>(), "stopped");
  EXPECT_FALSE(policy.at("w2_boundary").at("actual_native_invoked").get<bool>());
  EXPECT_FALSE(policy.at("w2_actual_C_call_started").get<bool>());
  EXPECT_EQ(policy.at("backend_entries_completed").get<unsigned>(), 0u);
  // 64/§5.3: the refusal must refresh the record, not just flip the label.
  // A stale `guard_ns` from the gate's decision would misstate when the call
  // was actually blocked.
  const auto & rec = a.boundary.record();
  EXPECT_TRUE(rec.released);
  EXPECT_EQ(rec.guard_ns, a.clock);
  EXPECT_EQ(rec.past_deadline_ns, rec.guard_ns - deadline);
  EXPECT_LT(rec.past_deadline_ns, 0) << "stop before expiry is still stopped";
  EXPECT_EQ(w2_test_probe::calls, 0u);
}

TEST(W2Backend, TargetExpiryDuringPreparationRefreshesTheRecord) {
  // Same window, expiry rather than stop: the record must not stay `allowed`.
  const int64_t deadline = kStartNs + 1000000000;
  Armed a(deadline, /*advance=*/1000000);
  w2_test_probe::Scope probe([&] { a.clock = deadline + 5000000; });
  a.backend->set_applied_control(Eigen::Vector2d::Zero());
  EXPECT_THROW(a.backend->solve_owned(target_job(kTargetJob, deadline)),
               std::runtime_error);
  const auto & rec = a.boundary.record();
  EXPECT_EQ(rec.disposition, Disposition::kExpired)
      << "a stale `allowed` record behind a refused call misstates the run";
  EXPECT_GT(rec.past_deadline_ns, 0);
  EXPECT_FALSE(rec.actual_native_invoked);
  const auto policy = a.backend->last_policy_event();
  ASSERT_TRUE(policy.contains("w2_boundary"));
  EXPECT_EQ(policy.at("w2_boundary").at("disposition").get<std::string>(), "expired");
  EXPECT_EQ(policy.at("backend_entries_completed").get<unsigned>(), 0u);
  EXPECT_TRUE(rec.released);
  EXPECT_EQ(rec.guard_ns, a.clock);
  EXPECT_EQ(w2_test_probe::calls, 0u);
}

TEST(W2Backend, ActualCFailureRetainsEntryFact) {
  Armed a(kStartNs + 1000000000, 1000000);
  w2_test_probe::Scope probe;
  w2_test_probe::forced_status = 55;
  a.backend->set_applied_control(Eigen::Vector2d::Zero());
  EXPECT_THROW(a.backend->solve_owned(target_job(kTargetJob, a.cfg.job_deadline_ns)),
               std::runtime_error);
  EXPECT_EQ(w2_test_probe::calls, 1u);
  EXPECT_TRUE(a.boundary.record().actual_native_invoked);
  EXPECT_TRUE(a.backend->last_policy_event().at("w2_boundary").at("actual_native_invoked").get<bool>());
  EXPECT_EQ(a.backend->last_policy_event().at("actual_C_solve_calls_this_job"), 1u);
  EXPECT_TRUE(a.backend->terminal());
}

TEST(W2Backend, StopWhileHeldKeepsTheTargetJobOutOfTheNativeCall) {
  const int64_t deadline = kStartNs + 1000000000;
  Armed a(deadline, /*advance=*/1000000);
  bool stop = true;
  a.backend->attach_boundary(&a.boundary, [&] { return stop; });
  a.backend->set_applied_control(Eigen::Vector2d::Zero());
  EXPECT_THROW(a.backend->solve_owned(target_job(kTargetJob, deadline)),
               std::runtime_error);
  EXPECT_EQ(a.boundary.record().disposition, Disposition::kStopped);
  EXPECT_FALSE(a.boundary.record().actual_native_invoked);
}

TEST(W2Backend, TheExistingBeforeCallHookStillRunsAndCanBlockTheSolve) {
  // The original component seam must not be dropped. A hook that throws has to
  // prevent the solve, and a hook that returns must be observed.
  int seen = 0;
  owned_cold::Backend backend(params(), binding(), true,
                              [] { return int64_t(kStartNs); },
                              [&seen](unsigned) { ++seen; });
  backend.set_applied_control(Eigen::Vector2d::Zero());
  EXPECT_NO_THROW(backend.solve_owned(target_job(kTargetJob, kStartNs + 1000000000)));
  EXPECT_GE(seen, 1);

  int calls = 0;
  owned_cold::Backend throwing(params(), binding(), true,
                               [] { return int64_t(kStartNs); },
                               [&calls](unsigned) {
                                 ++calls;
                                 throw std::runtime_error("hook refused");
                               });
  throwing.set_applied_control(Eigen::Vector2d::Zero());
  EXPECT_THROW(throwing.solve_owned(target_job(kTargetJob, kStartNs + 1000000000)),
               std::runtime_error);
  EXPECT_EQ(calls, 1);
  EXPECT_EQ(throwing.last_policy_event().at("backend_entries_started").get<unsigned>(),
            0u);
}

TEST(W2Backend, NonMatchingCallIsNotTreatedAsARejection) {
  // A gate armed on Job 1 must not disturb any other Job. This is the name the
  // earlier suite should have used: it exercises the non-matching path only.
  Armed a(kStartNs + 1000000000, /*advance=*/1000000);
  a.backend->set_applied_control(Eigen::Vector2d::Zero());
  // Job 2 closes the cold-start policy out, so it runs the ordinary path.
  EXPECT_NO_THROW(a.backend->solve_owned(target_job(2, kStartNs + 2000000000)));
  EXPECT_EQ(a.boundary.record().disposition, Disposition::kNotArmed);
  EXPECT_FALSE(a.boundary.record().actual_native_invoked);
}

int main(int argc, char ** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
