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
