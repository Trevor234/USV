// SPDX-License-Identifier: MIT
//
// Pipe-level tests for the W2 release gate.
//
// These use a real pipe and a real fd, because the behaviours a pipe has are
// the ones the component suite cannot model: EOF only arrives when every write
// end is closed, a write can be split across reads, and a reader that falls
// behind does not lose bytes. No ROS, no threads, no subprocesses.
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <unistd.h>

#include <chrono>
#include <csignal>
#include <sys/wait.h>

#include <gtest/gtest.h>

#include "w2_pipe_reader.hpp"
#include "w2_release_gate.hpp"

namespace {

using w2_gate::Gate;
using w2_gate::Identity;
using w2_gate::kFrameBytes;
using w2_gate::Outcome;
using w2_gate::PipeReader;

Identity want() {
  return Identity{/*run_seq=*/11, /*job_id=*/4, /*ordinal=*/3, /*nonce=*/0x5a5au};
}

void encode_into(uint8_t * dst, const Identity & id) {
  w2_gate::encode_release(dst, id);
}

/// Owns both ends of one pipe so a test can decide when EOF happens.
struct PipePair {
  int r = -1, w = -1;
  PipePair() {
    int fds[2];
    EXPECT_EQ(::pipe(fds), 0);
    r = fds[0];
    w = fds[1];
  }
  ~PipePair() {
    if (r >= 0) ::close(r);
    if (w >= 0) ::close(w);
  }
  void close_write() {
    if (w >= 0) { ::close(w); w = -1; }
  }
};

}  // namespace

TEST(W2ReleasePipe, CompleteReleaseThroughRealPipeIsAccepted) {
  PipePair p;
  uint8_t frame[kFrameBytes];
  encode_into(frame, want());
  ASSERT_EQ(::write(p.w, frame, kFrameBytes), long(kFrameBytes));

  PipeReader reader(p.r);
  Gate gate(&reader, want(), 2000000000);
  EXPECT_EQ(gate.wait(), Outcome::kReleased);
}

TEST(W2ReleasePipe, ClosedWriteEndWithNoBytesIsEof) {
  PipePair p;
  p.close_write();  // every write end now closed
  PipeReader reader(p.r);
  Gate gate(&reader, want(), 2000000000);
  EXPECT_EQ(gate.wait(), Outcome::kEof);
}

TEST(W2ReleasePipe, OpenWriteEndWithNoBytesIsTimeout) {
  PipePair p;
  // The write end stays open, so the pipe never reports EOF. This is the
  // difference between "the Driver died" and "the Driver never wrote".
  PipeReader reader(p.r);
  Gate gate(&reader, want(), 30000000);  // 30 ms
  EXPECT_EQ(gate.wait(), Outcome::kTimeout);
}

TEST(W2ReleasePipe, WriteEndClosedAfterAPartialFrameIsPartialFrame) {
  PipePair p;
  uint8_t frame[kFrameBytes];
  encode_into(frame, want());
  ASSERT_EQ(::write(p.w, frame, 10), 10);
  p.close_write();

  PipeReader reader(p.r);
  Gate gate(&reader, want(), 2000000000);
  EXPECT_EQ(gate.wait(), Outcome::kPartialFrame);
}

TEST(W2ReleasePipe, FrameSplitAcrossTwoWritesIsAssembled) {
  // A pipe write of 44 bytes is atomic here, but the gate must not depend on
  // that: splitting proves the read loop assembles rather than assuming one
  // read is one frame.
  PipePair p;
  uint8_t frame[kFrameBytes];
  encode_into(frame, want());
  ASSERT_EQ(::write(p.w, frame, 17), 17);
  ASSERT_EQ(::write(p.w, frame + 17, kFrameBytes - 17), long(kFrameBytes - 17));

  PipeReader reader(p.r);
  Gate gate(&reader, want(), 2000000000);
  EXPECT_EQ(gate.wait(), Outcome::kReleased);
}

TEST(W2ReleasePipe, TwoFramesWrittenMeansTheFirstIsUsedAndTheGateStops) {
  // The protocol is single-use. If a second frame is sitting in the pipe, the
  // gate must consume exactly one and remain released — not read the second and
  // reinterpret the boundary.
  PipePair p;
  uint8_t frame[kFrameBytes];
  encode_into(frame, want());
  ASSERT_EQ(::write(p.w, frame, kFrameBytes), long(kFrameBytes));
  Identity second = want();
  second.ordinal = want().ordinal + 1;
  uint8_t frame2[kFrameBytes];
  encode_into(frame2, second);
  ASSERT_EQ(::write(p.w, frame2, kFrameBytes), long(kFrameBytes));

  PipeReader reader(p.r);
  Gate gate(&reader, want(), 2000000000);
  EXPECT_EQ(gate.wait(), Outcome::kReleased);
  // A second wait is terminal and cannot consume the queued frame.
  EXPECT_EQ(gate.wait(), Outcome::kReleased);
}

TEST(W2ReleasePipe, NegativeFdIsReportedImmediatelyNotAfterTheBudget) {
  // A gate constructed with a bad fd must fail at once. Waiting out the whole
  // budget on a descriptor that can never carry a byte would be indistinguishable
  // from a Driver that never wrote, and would stall the run for nothing.
  Gate gate;  // default-constructed: no reader at all
  EXPECT_FALSE(gate.configured());
  EXPECT_EQ(gate.wait(), Outcome::kNotConfigured);

  PipeReader bad(-1);
  Gate g2(&bad, want(), 5000000000);  // 5 s budget
  EXPECT_TRUE(g2.configured());  // a reader was supplied; validity is separate
  const auto started = std::chrono::steady_clock::now();
  EXPECT_EQ(g2.wait(), Outcome::kEof);
  const auto took = std::chrono::duration_cast<std::chrono::milliseconds>(
      std::chrono::steady_clock::now() - started).count();
  EXPECT_LT(took, 1000) << "invalid fd waited " << took << " ms";
}

TEST(W2ReleasePipe, ReleaseForAnotherOrdinalThroughPipeIsRejected) {
  PipePair p;
  Identity other = want();
  other.ordinal = 1;
  uint8_t frame[kFrameBytes];
  encode_into(frame, other);
  ASSERT_EQ(::write(p.w, frame, kFrameBytes), long(kFrameBytes));

  PipeReader reader(p.r);
  Gate gate(&reader, want(), 2000000000);
  EXPECT_EQ(gate.wait(), Outcome::kIdentityMismatch);
}

TEST(W2ReleasePipe, CrcSurvivesThePipeRoundTrip) {
  // Guards against an encode/decode asymmetry that only shows up once the bytes
  // actually travel through a kernel buffer.
  PipePair p;
  uint8_t frame[kFrameBytes];
  Identity id = want();
  id.run_seq = 0xffffffffffffffffull;  // all-ones, to catch sign handling
  encode_into(frame, id);
  ASSERT_EQ(::write(p.w, frame, kFrameBytes), long(kFrameBytes));

  PipeReader reader(p.r);
  Gate gate(&reader, id, 2000000000);
  EXPECT_EQ(gate.wait(), Outcome::kReleased);
}

TEST(W2ReleasePipe, SignalInterruptingPollIsRetriedNotReportedAsTimeout) {
  // SIGALRM with a handler installed and SA_RESTART clear interrupts poll()
  // with EINTR without killing the process. A reader that reports EINTR as a
  // timeout would turn ordinary signal delivery into a "Driver never released"
  // verdict.
  PipePair p;
  uint8_t frame[kFrameBytes];
  encode_into(frame, want());

  // Trap SIGALRM first: with the default disposition the process would die.
  struct sigaction sa {};
  sa.sa_handler = [](int) {};
  sigemptyset(&sa.sa_mask);
  sa.sa_flags = 0;  // deliberately no SA_RESTART, so poll() returns EINTR
  struct sigaction old {};
  ASSERT_EQ(::sigaction(SIGALRM, &sa, &old), 0);

  // A child completes the release well after the alarm, so the parent's first
  // poll() is interrupted and a second one must go on to read the frame.
  pid_t pid = ::fork();
  ASSERT_GE(pid, 0);
  if (pid == 0) {
    ::usleep(150000);
    const ssize_t n = ::write(p.w, frame, kFrameBytes);
    ::_exit(n == long(kFrameBytes) ? 0 : 1);
  }
  ::ualarm(20000, 0);  // fires at 20 ms, while the parent is inside poll()

  PipeReader reader(p.r);
  Gate gate(&reader, want(), 2000000000);
  const Outcome got = gate.wait();
  ::ualarm(0, 0);
  ::sigaction(SIGALRM, &old, nullptr);
  int status = 0;
  ::waitpid(pid, &status, 0);
  EXPECT_EQ(got, Outcome::kReleased);
}

TEST(W2ReleasePipe, BudgetAlreadyExpiredBeforeTheGateStartsNeverReleases) {
  // The gate anchors an absolute deadline at entry. A 1 ns budget is spent
  // before the first read can complete, so even bytes already sitting in the
  // pipe are a late release, not a valid one. This is the boundary the review
  // asked to pin: late bytes must not be converted into "released".
  PipePair p;
  uint8_t frame[kFrameBytes];
  encode_into(frame, want());
  ASSERT_EQ(::write(p.w, frame, kFrameBytes), long(kFrameBytes));

  PipeReader reader(p.r);
  Gate gate(&reader, want(), 1);  // 1 ns
  EXPECT_NE(gate.wait(), Outcome::kReleased);
  EXPECT_FALSE(gate.released());
}

TEST(W2ReleasePipe, ReportedElapsedCoversInterruptedWaitNotJustTheLastPoll) {
  // The defect this pins: the reader used to report only the final poll's
  // duration, so a signal during the wait silently donated time to the gate's
  // budget. Every return path must now report from the call's own origin.
  PipePair p;
  struct sigaction sa {};
  sa.sa_handler = [](int) {};
  sigemptyset(&sa.sa_mask);
  sa.sa_flags = 0;  // no SA_RESTART: poll returns EINTR
  struct sigaction old {};
  ASSERT_EQ(::sigaction(SIGALRM, &sa, &old), 0);

  pid_t pid = ::fork();
  ASSERT_GE(pid, 0);
  if (pid == 0) {
    ::usleep(120000);  // 120 ms in, well after the 40 ms alarm
    uint8_t frame[kFrameBytes];
    encode_into(frame, want());
    const ssize_t n = ::write(p.w, frame, kFrameBytes);
    ::_exit(n == long(kFrameBytes) ? 0 : 1);
  }
  ::ualarm(40000, 0);

  PipeReader reader(p.r);
  int64_t reported = 0;
  uint8_t buf[kFrameBytes];
  const auto start = std::chrono::steady_clock::now();
  const long got = reader.read_some(buf, kFrameBytes, 1000000000, &reported);
  const auto actual = std::chrono::duration_cast<std::chrono::nanoseconds>(
      std::chrono::steady_clock::now() - start).count();
  ::ualarm(0, 0);
  ::sigaction(SIGALRM, &old, nullptr);
  int status = 0;
  ::waitpid(pid, &status, 0);

  EXPECT_GT(got, 0);
  // The reported time must track the real wait, not just the post-alarm slice.
  // A 40 ms under-report is the bug; allow scheduling noise well below that.
  EXPECT_GE(reported, actual - 20000000)
      << "reported " << reported << " ns vs actual " << actual << " ns";
  EXPECT_LE(reported, actual + 20000000)
      << "reported " << reported << " ns vs actual " << actual << " ns";
}

TEST(W2ReleasePipe, TinyBudgetWithNoBytesReturnsRatherThanHanging) {
  PipePair p;  // write end stays open, so no EOF
  PipeReader reader(p.r);
  Gate gate(&reader, want(), 1000);  // 1 us
  EXPECT_EQ(gate.wait(), Outcome::kTimeout);
}

int main(int argc, char ** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
