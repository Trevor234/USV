// SPDX-License-Identifier: MIT
//
// Component tests for the W2 release gate. No ROS, no pipe, no threads: the
// gate's state machine is exercised through a scripted Reader so every terminal
// outcome is reproducible and each one is distinguishable from the others.
//
// What these tests are for is narrower than "W2 passed". They show the gate
// refuses malformed, mistargeted, duplicated and truncated releases, and that
// it reports EOF and timeout differently. Whether the process actually holds at
// the native boundary, and whether the release is the *only* way past it, is
// owned by the owned run, not by this file.
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include <gtest/gtest.h>

#include "w2_release_gate.hpp"

namespace {

using w2_gate::Gate;
using w2_gate::Identity;
using w2_gate::Outcome;
using w2_gate::kFrameBytes;

/// A Reader that replays a scripted sequence of read results.
///
/// Each step is either bytes to deliver, EOF, or a timeout. The steps are
/// consumed in order, so a test can build "half a frame, then EOF" exactly.
class ScriptedReader final : public w2_gate::Reader {
 public:
  struct Step {
    std::vector<uint8_t> bytes;  // empty + eof=false + timeout=false => timeout
    bool eof = false;
    bool timeout = false;
    int64_t elapsed_ns = 0;
  };

  explicit ScriptedReader(std::vector<Step> steps) : steps_(std::move(steps)) {}

  /// Advance this clock by each step's reported elapsed time. The gate anchors
  /// an absolute deadline, so a scripted reader that reports elapsed time
  /// without moving the clock would loop instead of reaching the deadline.
  void attach_clock(int64_t * clock) { clock_ = clock; }

  long read_some(uint8_t * buf, size_t n, int64_t timeout_ns,
                 int64_t * elapsed_ns) override {
    (void)timeout_ns;  // the script, not a clock, decides when a step ends
    if (cursor_ >= steps_.size()) {
      // Running past the script is itself a bug in the test or the gate.
      ADD_FAILURE() << "gate read past the end of the scripted sequence";
      *elapsed_ns = 0;
      return 0;
    }
    const Step & s = steps_[cursor_++];
    if (clock_) *clock_ += s.elapsed_ns;
    if (s.eof) {
      *elapsed_ns = s.elapsed_ns;
      return 0;
    }
    if (s.timeout) {
      *elapsed_ns = s.elapsed_ns;
      return -1;
    }
    const size_t take = std::min(n, s.bytes.size());
    std::memcpy(buf, s.bytes.data(), take);
    *elapsed_ns = s.elapsed_ns;
    // If a step carries more bytes than requested, keep the rest for the next
    // read so the gate's partial-frame handling is what is under test.
    if (take < s.bytes.size()) {
      steps_[cursor_ - 1].bytes.erase(
          steps_[cursor_ - 1].bytes.begin(),
          steps_[cursor_ - 1].bytes.begin() + long(take));
      --cursor_;
    }
    return long(take);
  }

 private:
  std::vector<Step> steps_;
  size_t cursor_ = 0;
  int64_t * clock_ = nullptr;
};

Identity want() {
  return Identity{/*run_seq=*/7, /*job_id=*/3, /*ordinal=*/2, /*nonce=*/0xabcdu};
}

std::vector<uint8_t> frame_for(const Identity & id) {
  uint8_t buf[kFrameBytes];
  w2_gate::encode_release(buf, id);
  return std::vector<uint8_t>(buf, buf + kFrameBytes);
}

std::vector<ScriptedReader::Step> deliver(std::vector<uint8_t> bytes) {
  ScriptedReader::Step s;
  s.bytes = std::move(bytes);
  return {s};
}

/// A shared virtual clock the scripted reader advances by the elapsed time it
/// reports. The gate anchors an absolute deadline, so a scripted reader that
/// never advances time would loop forever instead of reaching its deadline.
struct VirtualClock {
  int64_t now = 0;
};

Gate make_gate(ScriptedReader & reader, Identity id, int64_t timeout_ns = 2000000000,
               VirtualClock * clock = nullptr) {
  Gate g(&reader, id, timeout_ns);
  if (clock) {
    reader.attach_clock(&clock->now);
    g.set_clock([clock] { return clock->now; });
  }
  return g;
}

}  // namespace

TEST(W2ReleaseGate, AcceptsExactlyOneWellFormedMatchingRelease) {
  ScriptedReader r(deliver(frame_for(want())));
  Gate g = make_gate(r, want());
  EXPECT_EQ(g.wait(), Outcome::kReleased);
  EXPECT_TRUE(g.released());
  // The outcome is terminal: a second wait cannot consume another release.
  EXPECT_EQ(g.wait(), Outcome::kReleased);
}

TEST(W2ReleaseGate, UnconfiguredGateReportsItselfRatherThanBlocking) {
  Gate g;
  EXPECT_FALSE(g.configured());
  EXPECT_EQ(g.wait(), Outcome::kNotConfigured);
}

TEST(W2ReleaseGate, NonPositiveTimeoutIsAFrameFault) {
  ScriptedReader r(deliver(frame_for(want())));
  Gate g = make_gate(r, want(), 0);
  EXPECT_EQ(g.wait(), Outcome::kBadFrame);
}

TEST(W2ReleaseGate, ReleaseForAnotherJobIsIdentityMismatch) {
  Identity other = want();
  other.job_id = want().job_id + 1;
  ScriptedReader r(deliver(frame_for(other)));
  Gate g = make_gate(r, want());
  EXPECT_EQ(g.wait(), Outcome::kIdentityMismatch);
  EXPECT_FALSE(g.released());
}

TEST(W2ReleaseGate, ReleaseForAnotherOrdinalIsIdentityMismatch) {
  // The point of binding the ordinal: a release aimed at call 1 must not open
  // call 2, or one pause would let every later Job through.
  Identity other = want();
  other.ordinal = 1;
  ScriptedReader r(deliver(frame_for(other)));
  Gate g = make_gate(r, want());
  EXPECT_EQ(g.wait(), Outcome::kIdentityMismatch);
}

TEST(W2ReleaseGate, ReleaseForAnotherRunSequenceIsIdentityMismatch) {
  Identity other = want();
  other.run_seq = want().run_seq + 1;
  ScriptedReader r(deliver(frame_for(other)));
  Gate g = make_gate(r, want());
  EXPECT_EQ(g.wait(), Outcome::kIdentityMismatch);
}

TEST(W2ReleaseGate, WrongNonceIsIdentityMismatch) {
  Identity other = want();
  other.nonce = want().nonce ^ 1u;
  ScriptedReader r(deliver(frame_for(other)));
  Gate g = make_gate(r, want());
  EXPECT_EQ(g.wait(), Outcome::kIdentityMismatch);
}

TEST(W2ReleaseGate, CorruptedPayloadIsBadCrcNotIdentityMismatch) {
  // Flipping a payload bit must be reported as corruption, never as "a release
  // for a different Job", so the evidence does not blame the Driver.
  auto frame = frame_for(want());
  frame[17] ^= 0x01;  // inside job_id
  ScriptedReader r(deliver(frame));
  Gate g = make_gate(r, want());
  EXPECT_EQ(g.wait(), Outcome::kBadCrc);
}

TEST(W2ReleaseGate, WrongMagicIsBadFrame) {
  auto frame = frame_for(want());
  frame[0] ^= 0xff;
  ScriptedReader r(deliver(frame));
  Gate g = make_gate(r, want());
  EXPECT_EQ(g.wait(), Outcome::kBadFrame);
}

TEST(W2ReleaseGate, UnknownVersionIsBadFrame) {
  uint8_t buf[kFrameBytes];
  w2_gate::encode_release(buf, want());
  w2_gate::put_u16(buf + 4, 2);
  w2_gate::put_u32(buf + 40, w2_gate::crc32(buf, 40));
  ScriptedReader r(deliver(std::vector<uint8_t>(buf, buf + kFrameBytes)));
  Gate g = make_gate(r, want());
  EXPECT_EQ(g.wait(), Outcome::kBadFrame);
}

TEST(W2ReleaseGate, NonZeroReservedFieldIsBadFrame) {
  uint8_t buf[kFrameBytes];
  w2_gate::encode_release(buf, want());
  w2_gate::put_u16(buf + 6, 0x1234);  // reserved
  w2_gate::put_u32(buf + 40, w2_gate::crc32(buf, 40));
  ScriptedReader r(deliver(std::vector<uint8_t>(buf, buf + kFrameBytes)));
  Gate g = make_gate(r, want());
  EXPECT_EQ(g.wait(), Outcome::kBadFrame);
}

TEST(W2ReleaseGate, DuplicateReleaseSequenceIsBadFrame) {
  // A frame claiming release sequence 2 is not a second release the gate could
  // honour; it is malformed under a single-use protocol.
  uint8_t buf[kFrameBytes];
  w2_gate::encode_release(buf, want());
  w2_gate::put_u64(buf + 32, 2);
  w2_gate::put_u32(buf + 40, w2_gate::crc32(buf, 40));
  ScriptedReader r(deliver(std::vector<uint8_t>(buf, buf + kFrameBytes)));
  Gate g = make_gate(r, want());
  EXPECT_EQ(g.wait(), Outcome::kBadFrame);
}

TEST(W2ReleaseGate, EofWithNoBytesIsEof) {
  ScriptedReader::Step eof;
  eof.eof = true;
  ScriptedReader r({eof});
  Gate g = make_gate(r, want());
  EXPECT_EQ(g.wait(), Outcome::kEof);
}

TEST(W2ReleaseGate, TimeoutWithNoBytesIsTimeout) {
  // The gate anchors an absolute deadline, so the scripted reader must advance
  // the same clock it reports against; otherwise the loop has no end.
  VirtualClock vc;
  ScriptedReader::Step to;
  to.timeout = true;
  to.elapsed_ns = 2000000000;
  ScriptedReader r({to});
  Gate g = make_gate(r, want(), 2000000000, &vc);
  EXPECT_EQ(g.wait(), Outcome::kTimeout);
}

TEST(W2ReleaseGate, HalfAFrameThenEofIsPartialFrame) {
  auto frame = frame_for(want());
  std::vector<uint8_t> head(frame.begin(), frame.begin() + 17);
  ScriptedReader::Step part;
  part.bytes = head;
  ScriptedReader::Step eof;
  eof.eof = true;
  ScriptedReader r({part, eof});
  Gate g = make_gate(r, want());
  EXPECT_EQ(g.wait(), Outcome::kPartialFrame);
}

TEST(W2ReleaseGate, HalfAFrameThenTimeoutIsPartialFrame) {
  // Distinguishes "the Driver died mid-frame" from "the Driver never wrote".
  auto frame = frame_for(want());
  std::vector<uint8_t> head(frame.begin(), frame.begin() + 39);
  VirtualClock vc;
  ScriptedReader::Step part;
  part.bytes = head;
  part.elapsed_ns = 1000;
  ScriptedReader::Step to;
  to.timeout = true;
  to.elapsed_ns = 2999999000;
  ScriptedReader r({part, to});
  Gate g = make_gate(r, want(), 2000000000, &vc);
  EXPECT_EQ(g.wait(), Outcome::kPartialFrame);
}

TEST(W2ReleaseGate, StopAlreadySetBeforeWaitingWinsOverTheRelease) {
  // A stop must not be convertible into a release: the gate checks the stop
  // predicate before every read.
  auto frame = frame_for(want());
  ScriptedReader::Step part;
  part.bytes.assign(frame.begin(), frame.begin() + 8);
  ScriptedReader::Step rest;
  rest.bytes.assign(frame.begin() + 8, frame.end());
  ScriptedReader r({part, rest});
  Gate g = make_gate(r, want());
  EXPECT_EQ(g.wait([] { return true; }), Outcome::kStopRequested);
  EXPECT_FALSE(g.released());
}

TEST(W2ReleaseGate, StopRaisedDuringTheReadWinsOverTheCompleteFrame) {
  // The defect this pins: a stop that lands while the bytes are in flight used
  // to be ignored, because the loop exited on a complete frame without asking
  // again. A frame arriving does not overrule the caller's stop.
  auto frame = frame_for(want());
  ScriptedReader::Step whole;
  whole.bytes = frame;
  ScriptedReader r({whole});

  bool stop = false;
  // The reader returns the complete frame; the predicate flips to true by the
  // time the gate re-checks it after assembly.
  struct FlippingReader final : w2_gate::Reader {
    const std::vector<uint8_t> & bytes;
    bool * flag;
    FlippingReader(const std::vector<uint8_t> & b, bool * f) : bytes(b), flag(f) {}
    long read_some(uint8_t * buf, size_t n, int64_t, int64_t * e) override {
      const size_t take = std::min(n, bytes.size());
      std::memcpy(buf, bytes.data(), take);
      *flag = true;  // the stop arrives while/just after the read completes
      if (e) *e = 1000;
      return long(take);
    }
  } flipping(frame, &stop);

  Gate g(&flipping, want(), 2000000000);
  EXPECT_EQ(g.wait([&] { return stop; }), Outcome::kStopRequested);
  EXPECT_FALSE(g.released());
}

TEST(W2ReleaseGate, CompleteFrameArrivingAfterTheDeadlineIsNotReleased) {
  // A complete, well-formed frame that lands after the window closed is a late
  // release, not a valid one. The OS may still hand us the bytes; reporting them
  // as released would make the bounded-wait evidence untrue.
  auto frame = frame_for(want());

  // A controllable clock: the gate computes its deadline from t=0, and every
  // later reading jumps past it, as an over-budget reader would.
  int64_t now = 0;
  Gate g(nullptr, want(), 1000000);  // 1 ms budget
  g.set_clock([&] { return now; });

  struct LateReader final : w2_gate::Reader {
    const std::vector<uint8_t> & bytes;
    int64_t * clock;
    LateReader(const std::vector<uint8_t> & b, int64_t * c) : bytes(b), clock(c) {}
    long read_some(uint8_t * buf, size_t n, int64_t, int64_t * e) override {
      const size_t take = std::min(n, bytes.size());
      std::memcpy(buf, bytes.data(), take);
      *clock = 5000000;  // 5 ms: well past the 1 ms deadline
      if (e) *e = 5000000;
      return long(take);
    }
  } late(frame, &now);

  Gate g2(&late, want(), 1000000);
  g2.set_clock([&] { return now; });
  EXPECT_NE(g2.wait(), Outcome::kReleased);
  EXPECT_FALSE(g2.released());
}

TEST(W2ReleaseGate, StopPredicateIsCalledRepeatedlyWhileNothingArrives) {
  // Waiting is sliced so a stop can be observed even when the Driver never
  // writes. Calling the predicate only once (before the first read) would leave
  // a 2 s wait unable to notice a stop signalled 100 ms in.
  struct SilentReader final : w2_gate::Reader {
    long read_some(uint8_t *, size_t, int64_t, int64_t * e) override {
      if (e) *e = 50000000;  // report a full slice so the clock advances
      return -1;             // nothing available
    }
  } silent;

  int calls = 0;
  Gate g(&silent, want(), 2000000000);  // 2 s, far longer than one slice
  const Outcome got = g.wait([&] { ++calls; return calls >= 3; });
  EXPECT_EQ(got, Outcome::kStopRequested);
  EXPECT_GE(calls, 3);
}

TEST(W2ReleaseGate, FrameSplitAcrossReadsIsAssembled) {
  // The gate must not assume the frame arrives in one read: a pipe write can be
  // split, and treating each read as a frame would reject a valid release.
  auto frame = frame_for(want());
  ScriptedReader::Step a;
  a.bytes.assign(frame.begin(), frame.begin() + 9);
  ScriptedReader::Step b;
  b.bytes.assign(frame.begin() + 9, frame.begin() + 25);
  ScriptedReader::Step c;
  c.bytes.assign(frame.begin() + 25, frame.end());
  ScriptedReader r({a, b, c});
  Gate g = make_gate(r, want());
  EXPECT_EQ(g.wait(), Outcome::kReleased);
}

TEST(W2ReleaseGate, EveryOutcomeHasADistinctName) {
  // The run evidence keys off these names; two outcomes sharing one would make
  // "timeout" and "eof" indistinguishable after the fact.
  const Outcome all[] = {
      Outcome::kReleased, Outcome::kNotConfigured, Outcome::kTimeout,
      Outcome::kEof, Outcome::kPartialFrame, Outcome::kBadCrc,
      Outcome::kBadFrame, Outcome::kIdentityMismatch,
      Outcome::kDuplicateRelease, Outcome::kStopRequested};
  std::vector<std::string> names;
  for (Outcome o : all) names.emplace_back(w2_gate::outcome_name(o));
  for (size_t i = 0; i < names.size(); ++i) {
    for (size_t j = i + 1; j < names.size(); ++j) {
      EXPECT_NE(names[i], names[j]) << "outcomes " << i << " and " << j;
    }
  }
}

int main(int argc, char ** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
