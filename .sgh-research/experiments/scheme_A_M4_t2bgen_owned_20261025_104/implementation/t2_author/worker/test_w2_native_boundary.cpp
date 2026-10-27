// SPDX-License-Identifier: MIT
//
// Targeted checks for the W2 native-boundary decision, per the wiring plan §6.2:
//   * a normal (unarmed) profile keeps the original path;
//   * only the registered Job+ordinal is held;
//   * the last guard separates "released" from "still inside the Job deadline";
//   * an expired boundary never reaches the call;
//   * the single-use property holds.
//
// No ROS, no solver, no pipe: the gate is driven by a scripted reader so each
// disposition is reproducible.
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

#include <gtest/gtest.h>

#include "w2_native_boundary.hpp"

namespace {

using w2_gate::Gate;
using w2_gate::Identity;
using w2_gate::Outcome;
using w2_wire::Boundary;
using w2_wire::BoundaryConfig;
using w2_wire::Disposition;

constexpr int64_t kJobId = 7;
constexpr uint32_t kOrdinal = 3;

/// A reader that hands back one complete release frame (or nothing).
class FrameReader final : public w2_gate::Reader {
 public:
  FrameReader(Identity id, bool deliver, int64_t advance_per_read)
  : id_(id), deliver_(deliver), advance_(advance_per_read) {}

  long read_some(uint8_t * buf, size_t n, int64_t, int64_t * elapsed) override {
    if (!deliver_) {
      if (elapsed) *elapsed = advance_;
      clock_ += advance_;
      return -1;
    }
    uint8_t frame[w2_gate::kFrameBytes];
    w2_gate::encode_release(frame, id_);
    const size_t take = std::min(n, w2_gate::kFrameBytes);
    std::memcpy(buf, frame, take);
    if (elapsed) *elapsed = advance_;
    clock_ += advance_;
    return long(take);
  }

  int64_t clock_ = 0;

 private:
  Identity id_;
  bool deliver_;
  int64_t advance_;
};

/// One boundary plus the gate and reader behind it.
struct Fixture {
  Fixture(bool deliver, int64_t wait_budget, int64_t job_deadline,
          int64_t advance_per_read = 0)
  : reader(identity(), deliver, advance_per_read),
    gate(&reader, identity(), wait_budget) {
    cfg.job_id = kJobId;
    cfg.ordinal = kOrdinal;
    cfg.job_deadline_ns = job_deadline;
    cfg.wait_budget_ns = wait_budget;
    boundary = Boundary(&gate, cfg, [this] { return reader.clock_; });
    boundary.set_clock([this] { return reader.clock_; });
  }

  static Identity identity() {
    return Identity{/*run_seq=*/1, /*job_id=*/uint64_t(kJobId),
                    /*ordinal=*/kOrdinal, /*nonce=*/0x42};
  }

  FrameReader reader;
  Gate gate;
  BoundaryConfig cfg;
  Boundary boundary;
};

}

TEST(W2Boundary, UnarmedProfileIsAllowedAndReportsItself) {
  // The normal profile registers no gate. The original path must be unchanged
  // and the record must say so rather than pretending a boundary was checked.
  Boundary b;
  EXPECT_FALSE(b.armed());
  EXPECT_TRUE(b.enter(kOrdinal, kJobId, {}));
  EXPECT_EQ(b.record().disposition, Disposition::kNotArmed);
  EXPECT_FALSE(b.record().gate_configured);
}

TEST(W2Boundary, RegisteredCallWithTimelyReleaseIsAllowed) {
  // Release arrives immediately and the Job is still inside its deadline.
  Fixture f(/*deliver=*/true, /*wait_budget=*/1000000, /*job_deadline=*/10000000);
  EXPECT_TRUE(f.boundary.enter(kOrdinal, kJobId, {}));
  const auto & r = f.boundary.record();
  EXPECT_EQ(r.disposition, Disposition::kAllowed);
  EXPECT_TRUE(r.released);
  EXPECT_TRUE(r.gate_configured);
  EXPECT_LE(r.past_deadline_ns, 0);
  // The call has not been taken yet; only mark_native_entered may set this.
  EXPECT_FALSE(r.actual_native_invoked);
}

TEST(W2Boundary, ReleasedButPastTheJobDeadlineIsExpiredNotAllowed) {
  // The gate window is generous; the Job deadline is not. This is the case the
  // plan calls out: a verified release is not an execution grant.
  Fixture f(/*deliver=*/true, /*wait_budget=*/1000000, /*job_deadline=*/-1);
  EXPECT_FALSE(f.boundary.enter(kOrdinal, kJobId, {}));
  const auto & r = f.boundary.record();
  EXPECT_EQ(r.disposition, Disposition::kExpired);
  EXPECT_TRUE(r.released);           // the release really was verified
  EXPECT_GT(r.past_deadline_ns, 0);  // and the Job really was late
  EXPECT_FALSE(r.actual_native_invoked);
}

TEST(W2Boundary, ReleaseAtExactlyTheDeadlineIsAllowed) {
  // The guard is `>` not `>=`: an instant equal to the deadline is still inside
  // it. Pinning this keeps the boundary from drifting by one comparison.
  Fixture f(/*deliver=*/true, /*wait_budget=*/1000000, /*job_deadline=*/0);
  EXPECT_TRUE(f.boundary.enter(kOrdinal, kJobId, {}));
  EXPECT_EQ(f.boundary.record().disposition, Disposition::kAllowed);
}

TEST(W2Boundary, WaitWindowExhaustionIsWaitFailedAndNeverCalls) {
  // Nothing is ever written; the gate's own window expires. This must not be
  // confused with the Job deadline.
  Fixture f(/*deliver=*/false, /*wait_budget=*/2000000, /*job_deadline=*/100000000,
            /*advance_per_read=*/50000000);
  EXPECT_FALSE(f.boundary.enter(kOrdinal, kJobId, {}));
  const auto & r = f.boundary.record();
  EXPECT_EQ(r.disposition, Disposition::kWaitFailed);
  EXPECT_FALSE(r.released);
  EXPECT_FALSE(r.actual_native_invoked);
  EXPECT_STREQ(r.gate_outcome, "timeout");
}

TEST(W2Boundary, StopDuringTheWaitIsStoppedAndNeverCalls) {
  // The reader never delivers and advances the clock by a full slice per read,
  // so the wait stays alive; the predicate flips after the gate has already
  // asked once, which is the "stop lands mid-wait" case.
  Fixture f(/*deliver=*/false, /*wait_budget=*/500000000, /*job_deadline=*/1000000000,
            /*advance_per_read=*/1000000);
  int calls = 0;
  EXPECT_FALSE(f.boundary.enter(kOrdinal, kJobId, [&] {
    ++calls;
    return calls >= 2;  // the second evaluation, i.e. after one read
  }));
  EXPECT_GE(calls, 2);
  EXPECT_EQ(f.boundary.record().disposition, Disposition::kStopped);
  EXPECT_FALSE(f.boundary.record().actual_native_invoked);
}

TEST(W2Boundary, StopSetBeforeTheGateStartsIsStopped) {
  Fixture f(/*deliver=*/true, /*wait_budget=*/1000000, /*job_deadline=*/10000000);
  EXPECT_FALSE(f.boundary.enter(kOrdinal, kJobId, [] { return true; }));
  EXPECT_EQ(f.boundary.record().disposition, Disposition::kStopped);
}

TEST(W2Boundary, StopRaisedBetweenTheGatesFinalCheckAndTheGuardIsHonoured) {
  // The v2 Gate checks the predicate once more after assembly. It cannot
  // exclude a stop that another thread sets *between* that check and the
  // boundary's next load, so the boundary's own post-release check is a real,
  // reachable guard — not dead defense in depth.
  //
  // This predicate answers false for the gate's checks and true on the
  // boundary's later load. That is exactly the interleaving of a concurrent
  // stop; no fake Gate is needed.
  auto frame_bytes = [&] {
    std::vector<uint8_t> f(w2_gate::kFrameBytes);
    w2_gate::encode_release(f.data(), Fixture::identity());
    return f;
  }();
  struct FrameOnce final : w2_gate::Reader {
    const std::vector<uint8_t> & bytes;
    FrameOnce(const std::vector<uint8_t> & b) : bytes(b) {}
    long read_some(uint8_t * buf, size_t n, int64_t, int64_t * e) override {
      const size_t take = std::min(n, bytes.size());
      std::memcpy(buf, bytes.data(), take);
      if (e) *e = 1;
      return long(take);
    }
  } reader(frame_bytes);
  Gate gate(&reader, Fixture::identity(), 1000000);
  BoundaryConfig cfg;
  cfg.job_id = kJobId;
  cfg.ordinal = kOrdinal;
  cfg.job_deadline_ns = 10000000;
  cfg.wait_budget_ns = 1000000;
  int64_t now = 0;
  Boundary boundary(&gate, cfg, [&now] { return now; });
  boundary.set_clock([&now] { return now; });

  int loads = 0;
  EXPECT_FALSE(boundary.enter(kOrdinal, kJobId, [&] {
    // The Gate polls this at the loop head, before the read, and once more
    // after assembly; the boundary then loads it again. Answering true from the
    // fourth load onwards targets the boundary's guard specifically.
    ++loads;
    return loads >= 4;
  }));
  const auto & r = boundary.record();
  EXPECT_EQ(r.disposition, Disposition::kStopped);
  // The gate handed back a valid release: that is the window this guard
  // covers, so `released` is true even though the call is refused.
  // `stop_at_release` records the first post-wait load, which is the gate's own
  // final check; the stop lands one load later, so that field stays false by
  // construction. Asserting it true would be asserting the wrong load.
  EXPECT_TRUE(r.released);
  EXPECT_FALSE(r.actual_native_invoked);
  EXPECT_GE(loads, 4);
}


TEST(W2Boundary, AnotherJobWithTheSameOrdinalIsNotHeld) {
  // The hook carries only an ordinal, so a boundary keyed on the ordinal alone
  // would hold the first call of every Job. This pins the Job comparison.
  Fixture f(/*deliver=*/false, /*wait_budget=*/1000000, /*job_deadline=*/10000000);
  EXPECT_FALSE(f.boundary.matches(kOrdinal, kJobId + 1));
  EXPECT_TRUE(f.boundary.matches(kOrdinal, kJobId));
  // And an unrelated Job must pass straight through without waiting.
  EXPECT_TRUE(f.boundary.enter(kOrdinal, kJobId + 1, {}));
  EXPECT_EQ(f.boundary.record().disposition, Disposition::kNotArmed);
}

TEST(W2Boundary, AnotherOrdinalIsNotHeld) {
  // The hook only carries an ordinal. Binding on the ordinal alone would pause
  // the first call of every Job; binding on Job+ordinal lets other calls pass.
  Fixture f(/*deliver=*/false, /*wait_budget=*/1000000, /*job_deadline=*/10000000);
  EXPECT_TRUE(f.boundary.enter(kOrdinal + 1, kJobId, {}));
  // Passing through an unrelated call must not mark the boundary done.
  EXPECT_EQ(f.boundary.record().disposition, Disposition::kNotArmed);
}

TEST(W2Boundary, AnotherJobIsNotHeld) {
  Fixture f(/*deliver=*/false, /*wait_budget=*/1000000, /*job_deadline=*/10000000);
  EXPECT_TRUE(f.boundary.enter(kOrdinal, kJobId + 1, {}));
  EXPECT_EQ(f.boundary.record().disposition, Disposition::kNotArmed);
}

TEST(W2Boundary, OnlyOneCallIsEverHeld) {
  // Single-use: after the registered call has been resolved, a later call does
  // not wait again. Without this a retry could consume a second release.
  Fixture f(/*deliver=*/true, /*wait_budget=*/1000000, /*job_deadline=*/10000000);
  ASSERT_TRUE(f.boundary.enter(kOrdinal, kJobId, {}));
  const auto first = f.boundary.record();
  EXPECT_TRUE(f.boundary.enter(kOrdinal, kJobId, {}));  // returns the cached yes
  EXPECT_EQ(f.boundary.record().entered_ns, first.entered_ns);
}

TEST(W2Boundary, NativeEntryIsRecordedOnlyWhenMarked) {
  Fixture f(/*deliver=*/true, /*wait_budget=*/1000000, /*job_deadline=*/10000000);
  ASSERT_TRUE(f.boundary.enter(kOrdinal, kJobId, {}));
  EXPECT_FALSE(f.boundary.record().actual_native_invoked);
  f.boundary.mark_native_entered(kOrdinal);
  EXPECT_TRUE(f.boundary.record().actual_native_invoked);
  EXPECT_EQ(f.boundary.record().ordinal_at_call, kOrdinal);
}

TEST(W2Boundary, RecordIsSerialisableWithEveryDecisionField) {
  Fixture f(/*deliver=*/true, /*wait_budget=*/1000000, /*job_deadline=*/-1);
  f.boundary.enter(kOrdinal, kJobId, {});
  const auto j = w2_boundary_json(f.boundary.record());
  for (const char * key : {"disposition", "gate_outcome", "released",
                           "released_ns", "job_deadline_ns", "guard_ns",
                           "past_deadline_ns", "actual_native_invoked"}) {
    EXPECT_TRUE(j.contains(key)) << key;
  }
  EXPECT_EQ(j.at("disposition").get<std::string>(), "expired");
  EXPECT_FALSE(j.at("actual_native_invoked").get<bool>());
}

TEST(W2Boundary, EveryDispositionHasADistinctName) {
  const Disposition all[] = {Disposition::kNotArmed, Disposition::kAllowed,
                             Disposition::kExpired, Disposition::kStopped,
                             Disposition::kWaitFailed};
  std::vector<std::string> names;
  for (auto d : all) names.emplace_back(w2_wire::disposition_name(d));
  for (size_t i = 0; i < names.size(); ++i) {
    for (size_t k = i + 1; k < names.size(); ++k) {
      EXPECT_NE(names[i], names[k]);
    }
  }
}

int main(int argc, char ** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
