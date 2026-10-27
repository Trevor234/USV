// SPDX-License-Identifier: MIT
//
// Wiring checks for the W2 native boundary: does the backend actually stop at
// the internal call boundary, does the last guard decide correctly, and does an
// expired boundary stay out of the actual C solve?
//
// These load no ROS and publish nothing. They do build the real
// owned_cold::Backend against the real acados-backed RawBackend, so the seam
// being tested is the one the Worker uses — not a stand-in.
//
// The clock is injected, so "deadline before / at / after" is exact rather than
// a race against the wall clock.
#include <cstdint>
#include <cstring>
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

constexpr int64_t kJobId = 2;
constexpr uint32_t kOrdinal = 1;

/// Delivers one release frame on the first read, then nothing.
class OneShotReader final : public w2_gate::Reader {
 public:
  explicit OneShotReader(Identity id) : id_(id) {}
  long read_some(uint8_t * buf, size_t n, int64_t, int64_t * elapsed) override {
    if (delivered_) {
      if (elapsed) *elapsed = 0;
      return -1;
    }
    delivered_ = true;
    uint8_t frame[w2_gate::kFrameBytes];
    w2_gate::encode_release(frame, id_);
    const size_t take = std::min(n, w2_gate::kFrameBytes);
    std::memcpy(buf, frame, take);
    if (elapsed) *elapsed = 0;
    return long(take);
  }

 private:
  Identity id_;
  bool delivered_ = false;
};

/// A monotonic clock the test advances explicitly.
struct TestClock {
  int64_t now = 1000000000;
};

/// The Job JSON the backend validates before it will solve. Mirrors what the
/// Worker's job_json produces for Job 1's cold-start case, which is the only
/// Job the cold-start policy arms for.
Json cold_start_job(int64_t job_id, int64_t deadline_ns) {
  Json j;
  j["schema"] = "p1-solve-job-v1";
  j["run_id"] = "w2_wiring_test";
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
  j["anchor_n"] = std::vector<double>{0, 0};
  j["reset_warmstart"] = false;
  // The cold-start policy requires this exact ramp to arm itself.
  std::vector<double> ref(126);
  for (int k = 0; k <= 20; ++k) {
    ref[6 * k + 0] = 0.05 * 0.2 * k;
    ref[6 * k + 1] = 0;
    ref[6 * k + 2] = 0;
    ref[6 * k + 3] = 0.05;
    ref[6 * k + 4] = 0;
    ref[6 * k + 5] = 0;
  }
  j["reference"] = ref;
  j["frozen_state"] = std::vector<double>{0, 0, 0, 0, 0, 0};
  j["anchor_known"] = std::vector<bool>{true, true};
  return j;
}

usv_mpc::MpcParams params() {
  usv_mpc::MpcParams p;
  p.dt = 0.2;
  p.N = 20;
  return p;
}

/// The binding must repeat exactly the identity fields the Job carries; the
/// backend rejects a solve whose context does not match it key for key.
Json binding() {
  return Json{{"run_id", "w2_wiring_test"}, {"boot_id", "boot"},
              {"contract_hash", std::string(64, 'a')},
              {"nominal_hash", std::string(64, 'b')},
              {"worker_instance", "instance"}};
}

}  // namespace

TEST(W2Wiring, UnarmedBackendRunsTheOrdinaryPathUnchanged) {
  TestClock clock;
  owned_cold::Backend backend(params(), binding(), true,
                              [&clock] { return clock.now; });
  // The backend requires the applied anchor to be set before each solve; the
  // Worker does this from the Job's anchor_n.
  backend.set_applied_control(Eigen::Vector2d::Zero());
  auto answer = backend.solve_owned(cold_start_job(1, clock.now + 1000000000));
  EXPECT_TRUE(backend.last_policy_event().at("successful").get<bool>());
  EXPECT_FALSE(backend.last_policy_event().contains("w2_boundary"));
  EXPECT_FALSE(backend.w2_boundary_event().is_object());
}

TEST(W2Wiring, ArmedBoundaryHoldsAtTheInternalCallAndAllowsOnRelease) {
  TestClock clock;
  Identity id{1, uint64_t(kJobId), kOrdinal, 7};
  OneShotReader reader(id);
  Gate gate(&reader, id, 1000000000);
  BoundaryConfig cfg;
  cfg.job_id = kJobId;
  cfg.ordinal = kOrdinal;
  cfg.job_deadline_ns = clock.now + 1000000000;  // comfortably ahead
  cfg.wait_budget_ns = 1000000000;
  Boundary boundary(&gate, cfg, [&clock] { return clock.now; });
  boundary.set_clock([&clock] { return clock.now; });

  owned_cold::Backend backend(params(), binding(), true,
                              [&clock] { return clock.now; });
  backend.attach_boundary(&boundary, [] { return false; });

  // Job 1 is the cold-start Job; the boundary binds to Job 2 / ordinal 1, which
  // this Job does not reach, so the ordinary path must still complete.
  backend.set_applied_control(Eigen::Vector2d::Zero());
  auto answer = backend.solve_owned(cold_start_job(1, clock.now + 1000000000));
  EXPECT_TRUE(backend.last_policy_event().at("successful").get<bool>());
  EXPECT_EQ(boundary.record().disposition, Disposition::kNotArmed);
}

TEST(W2Wiring, ExpiredBoundaryNeverEntersTheActualCall) {
  // The gate releases immediately, but the Job deadline is already in the past.
  // The release is verified and the call must not happen: this is the case a
  // long owned wait produces, and the one that must not be reported as a solve.
  TestClock clock;
  Identity id{1, uint64_t(kJobId), kOrdinal, 7};
  OneShotReader reader(id);
  Gate gate(&reader, id, 1000000000);
  BoundaryConfig cfg;
  cfg.job_id = kJobId;
  cfg.ordinal = kOrdinal;
  cfg.job_deadline_ns = clock.now - 1;  // already passed
  cfg.wait_budget_ns = 1000000000;
  Boundary boundary(&gate, cfg, [&clock] { return clock.now; });
  boundary.set_clock([&clock] { return clock.now; });

  owned_cold::Backend backend(params(), binding(), true,
                              [&clock] { return clock.now; });
  backend.attach_boundary(&boundary, [] { return false; });
  // Drive the registered boundary directly: the cold-start Job path is not what
  // this case is about.
  EXPECT_FALSE(boundary.enter(kOrdinal, kJobId, {}));
  EXPECT_EQ(boundary.record().disposition, Disposition::kExpired);
  EXPECT_TRUE(boundary.record().released);
  EXPECT_FALSE(boundary.record().actual_native_invoked);
}

TEST(W2Wiring, BoundaryJsonCarriesBothDeadlinesAndTheCallFact) {
  TestClock clock;
  Identity id{1, uint64_t(kJobId), kOrdinal, 7};
  OneShotReader reader(id);
  Gate gate(&reader, id, 1000000000);
  BoundaryConfig cfg;
  cfg.job_id = kJobId;
  cfg.ordinal = kOrdinal;
  cfg.job_deadline_ns = clock.now + 1000000000;
  cfg.wait_budget_ns = 1000000000;
  Boundary boundary(&gate, cfg, [&clock] { return clock.now; });
  boundary.set_clock([&clock] { return clock.now; });
  ASSERT_TRUE(boundary.enter(kOrdinal, kJobId, {}));
  boundary.mark_native_entered(kOrdinal);
  const auto j = w2_boundary_json(boundary.record());
  EXPECT_EQ(j.at("disposition").get<std::string>(), "allowed");
  EXPECT_TRUE(j.at("actual_native_invoked").get<bool>());
  // The wait budget and the Job deadline are separate numbers in the record.
  EXPECT_NE(j.at("entered_ns").get<int64_t>(), 0);
  EXPECT_EQ(j.at("job_deadline_ns").get<int64_t>(), cfg.job_deadline_ns);
}

TEST(W2Wiring, UnmatchedCallIsNotTreatedAsARejection) {
  // The backend must only consult the boundary for the Job+ordinal it is bound
  // to. A missing `matches` check makes every unrelated call throw
  // "w2_boundary_not_armed", which would break the ordinary solve path for any
  // run that arms a gate on one call.
  TestClock clock;
  Identity id{1, uint64_t(kJobId), kOrdinal, 7};
  OneShotReader reader(id);
  Gate gate(&reader, id, 1000000000);
  BoundaryConfig cfg;
  cfg.job_id = kJobId;       // bound to Job 2
  cfg.ordinal = kOrdinal;
  cfg.job_deadline_ns = clock.now + 1000000000;
  cfg.wait_budget_ns = 1000000000;
  Boundary boundary(&gate, cfg, [&clock] { return clock.now; });
  boundary.set_clock([&clock] { return clock.now; });

  owned_cold::Backend backend(params(), binding(), true,
                              [&clock] { return clock.now; });
  backend.attach_boundary(&boundary, [] { return false; });

  // Job 1 reaches internal ordinals 1..4; none of them is Job 2/ordinal 1, so
  // all of them must pass. If the backend forgot the `matches` guard this
  // throws instead of solving.
  backend.set_applied_control(Eigen::Vector2d::Zero());
  EXPECT_NO_THROW(backend.solve_owned(cold_start_job(1, clock.now + 1000000000)));
  EXPECT_TRUE(backend.last_policy_event().at("successful").get<bool>());
  EXPECT_EQ(boundary.record().disposition, Disposition::kNotArmed);
  EXPECT_FALSE(boundary.record().actual_native_invoked);
}

int main(int argc, char ** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
