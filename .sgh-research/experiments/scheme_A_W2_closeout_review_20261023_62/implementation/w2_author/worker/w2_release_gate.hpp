// SPDX-License-Identifier: MIT
//
// W2 private-pipe release gate.
//
// The pattern the frozen matrix asks for is "worker held at the native boundary
// until independent release". This gate is that boundary's waiting room, and
// nothing else: it owns one inherited read end, one single-use command, and a
// bounded wait. It deliberately does NOT own the deadline, the lease, the
// watchdog or the stop decision — the caller re-checks those after the gate
// returns, because a gate that could also decide to proceed would be a second
// authority over the call boundary.
//
// Why a pipe and not a DDS topic: the release must be attributable to one run,
// one Job and one call ordinal. A topic would be shared with every other
// subscriber and would need its own authentication. The pipe's identity is the
// inherited FD, and the command frame carries the rest.
//
// Frame layout (fixed, 44 bytes, little-endian, no padding):
//   0  u32 magic   'W2RL'
//   4  u16 version (1)
//   6  u16 reserved, must be 0
//   8  u64 run sequence number
//  16  u64 job id
//  24  u32 call ordinal
//  28  u32 nonce
//  32  u64 release sequence (must be 1: single-use)
//  40  u32 crc32 over bytes 0..39
//
// A partial frame, a bad CRC, a reserved field that is not zero, a version this
// build does not know, a duplicate release, a release for another run/Job/
// ordinal/nonce, EOF, and timeout are all distinct terminal outcomes. They are
// distinct because "the Driver never released" and "somebody else released"
// must not be reported as the same thing in the run evidence.
#pragma once

#include <cstdint>
#include <cstring>
#include <ctime>
#include <functional>
#include <string>

namespace w2_gate {

inline constexpr uint32_t kMagic = 0x4c523257;  // 'W2RL' little-endian
inline constexpr uint16_t kVersion = 1;
inline constexpr size_t kFrameBytes = 44;

enum class Outcome {
  kReleased,        // a well-formed, matching, first release arrived
  kNotConfigured,   // no gate was registered for this run; caller proceeds
  kTimeout,         // no complete frame before the bound
  kEof,             // the write end closed without a release
  kPartialFrame,    // bytes arrived but the frame is short or trailing
  kBadCrc,          // frame integrity failed
  kBadFrame,        // magic/version/reserved/sequence malformed
  kIdentityMismatch,// run/Job/ordinal/nonce do not name this boundary
  kDuplicateRelease,// a second release, or a release after one already taken
  kStopRequested,   // the caller asked to stop while waiting
};

inline const char * outcome_name(Outcome o) {
  switch (o) {
    case Outcome::kReleased: return "released";
    case Outcome::kNotConfigured: return "not_configured";
    case Outcome::kTimeout: return "timeout";
    case Outcome::kEof: return "eof";
    case Outcome::kPartialFrame: return "partial_frame";
    case Outcome::kBadCrc: return "bad_crc";
    case Outcome::kBadFrame: return "bad_frame";
    case Outcome::kIdentityMismatch: return "identity_mismatch";
    case Outcome::kDuplicateRelease: return "duplicate_release";
    case Outcome::kStopRequested: return "stop_requested";
  }
  return "unknown";
}

/// CRC-32 (IEEE 802.3), table-free and small enough to audit by eye.
inline uint32_t crc32(const uint8_t * data, size_t n) {
  uint32_t crc = 0xffffffffu;
  for (size_t i = 0; i < n; ++i) {
    crc ^= data[i];
    for (int b = 0; b < 8; ++b) {
      crc = (crc & 1u) ? (crc >> 1) ^ 0xedb88320u : (crc >> 1);
    }
  }
  return crc ^ 0xffffffffu;
}

/// The identity a release must match. All five fields together, because
/// "ordinal == 1" alone would pause every Job that reaches its first call.
struct Identity {
  uint64_t run_seq = 0;
  uint64_t job_id = 0;
  uint32_t ordinal = 0;
  uint32_t nonce = 0;
};

inline void put_u16(uint8_t * p, uint16_t v) {
  p[0] = uint8_t(v); p[1] = uint8_t(v >> 8);
}
inline void put_u32(uint8_t * p, uint32_t v) {
  for (int i = 0; i < 4; ++i) p[i] = uint8_t(v >> (8 * i));
}
inline void put_u64(uint8_t * p, uint64_t v) {
  for (int i = 0; i < 8; ++i) p[i] = uint8_t(v >> (8 * i));
}
inline uint16_t get_u16(const uint8_t * p) {
  return uint16_t(p[0]) | (uint16_t(p[1]) << 8);
}
inline uint32_t get_u32(const uint8_t * p) {
  uint32_t v = 0;
  for (int i = 0; i < 4; ++i) v |= uint32_t(p[i]) << (8 * i);
  return v;
}
inline uint64_t get_u64(const uint8_t * p) {
  uint64_t v = 0;
  for (int i = 0; i < 8; ++i) v |= uint64_t(p[i]) << (8 * i);
  return v;
}

/// Serialize a release frame. Used by the Driver and by the component tests.
inline void encode_release(uint8_t out[kFrameBytes], const Identity & id) {
  std::memset(out, 0, kFrameBytes);
  put_u32(out + 0, kMagic);
  put_u16(out + 4, kVersion);
  put_u16(out + 6, 0);
  put_u64(out + 8, id.run_seq);
  put_u64(out + 16, id.job_id);
  put_u32(out + 24, id.ordinal);
  put_u32(out + 28, id.nonce);
  put_u64(out + 32, 1);  // release sequence: this protocol admits exactly one
  put_u32(out + 40, crc32(out, 40));
}

/// Decode and validate a frame against the expected identity.
///
/// Structural faults are named before identity is compared, so a corrupted
/// frame is never misreported as "a release for another Job".
inline Outcome decode_release(const uint8_t in[kFrameBytes], const Identity & want) {
  if (get_u32(in + 0) != kMagic) return Outcome::kBadFrame;
  if (get_u16(in + 4) != kVersion) return Outcome::kBadFrame;
  if (get_u16(in + 6) != 0) return Outcome::kBadFrame;
  if (get_u32(in + 40) != crc32(in, 40)) return Outcome::kBadCrc;
  const uint64_t release_seq = get_u64(in + 32);
  if (release_seq != 1) {
    // 0 is "no release", >1 is "more than one release": both malformed for a
    // single-use protocol.
    return Outcome::kBadFrame;
  }
  const Identity got{get_u64(in + 8), get_u64(in + 16),
                     get_u32(in + 24), get_u32(in + 28)};
  if (got.run_seq != want.run_seq || got.job_id != want.job_id ||
      got.ordinal != want.ordinal || got.nonce != want.nonce) {
    return Outcome::kIdentityMismatch;
  }
  return Outcome::kReleased;
}

// ── I/O seam ──────────────────────────────────────────────────────────────
//
// The gate is written against this interface so the state machine is testable
// without a pipe, a thread or a clock. The production adapter uses poll() on
// the inherited FD; the tests use a scripted reader.

class Reader {
 public:
  virtual ~Reader() = default;
  /// Read up to n bytes, blocking at most `timeout_ns`, and report in
  /// `elapsed_ns` the **full** wall time this call consumed, including any
  /// interrupted and retried waits. Reporting only the last retry would let a
  /// signal extend the gate's total budget without the gate noticing.
  /// Returns >0 bytes read, 0 on EOF, -1 on timeout.
  virtual long read_some(uint8_t * buf, size_t n, int64_t timeout_ns,
                         int64_t * elapsed_ns) = 0;
};

/// The caller's stop condition, evaluated by the gate itself.
///
/// A predicate rather than a `const bool *` because the Worker's flag is a
/// std::atomic<bool>: there is no legal way to hand that to a `const bool *`
/// (copying it snapshots once, and reading it as a plain bool is not an atomic
/// access). The caller keeps ownership of the memory order; the gate only calls
/// the predicate.
using StopPredicate = std::function<bool()>;

/// One gate, one boundary, one release.
///
/// The lifecycle is: construct; `wait()` exactly once; the result is terminal.
/// Calling `wait()` again returns the stored outcome, so a caller that retries
/// cannot consume a second release.
///
/// Timing is anchored to one absolute deadline rather than a decrementing
/// budget: every slice shares the same end instant, so a partial read or an
/// interrupted poll can never hand the next slice a fresh full window.
class Gate {
 public:
  Gate() = default;
  Gate(Reader * reader, Identity identity, int64_t timeout_ns)
  : reader_(reader), identity_(identity), timeout_ns_(timeout_ns) {}

  bool configured() const { return reader_ != nullptr; }
  const Identity & identity() const { return identity_; }

  /// Wait for the single release, or for the deadline to pass.
  ///
  /// The stop predicate is evaluated before every read **and again after a
  /// complete frame arrives**, so a stop that lands while the bytes are in
  /// flight wins over the frame. Waiting is sliced so a predicate can be
  /// observed within `kSliceNs` even when the Driver never writes.
  Outcome wait(const StopPredicate & stop_requested = {}) {
    if (done_) return outcome_;
    done_ = true;
    if (!reader_) {
      outcome_ = Outcome::kNotConfigured;
      return outcome_;
    }
    if (timeout_ns_ <= 0) {
      outcome_ = Outcome::kBadFrame;
      return outcome_;
    }
    const int64_t deadline_ns = now_ns() + timeout_ns_;
    size_t got = 0;
    while (got < kFrameBytes) {
      if (stop_requested && stop_requested()) {
        outcome_ = Outcome::kStopRequested;
        return outcome_;
      }
      const int64_t left = deadline_ns - now_ns();
      if (left <= 0) {
        outcome_ = got == 0 ? Outcome::kTimeout : Outcome::kPartialFrame;
        return outcome_;
      }
      const int64_t slice = left < kSliceNs ? left : kSliceNs;
      int64_t elapsed = 0;
      const long n = reader_->read_some(frame_ + got, kFrameBytes - got, slice,
                                        &elapsed);
      if (n == 0) {
        outcome_ = got == 0 ? Outcome::kEof : Outcome::kPartialFrame;
        return outcome_;
      }
      if (n < 0) {
        // A read that ends past the deadline is a timeout, not a partial frame;
        // a read that ends inside it is the slice boundary and the loop
        // continues. The distinction is time, not the return code.
        if (now_ns() >= deadline_ns) {
          outcome_ = got == 0 ? Outcome::kTimeout : Outcome::kPartialFrame;
          return outcome_;
        }
        continue;
      }
      got += size_t(n);
      if (got > kFrameBytes) {
        outcome_ = Outcome::kPartialFrame;
        return outcome_;
      }
    }
    // A stop that arrives while the frame is being read must not be converted
    // into a release: the caller asked to stop, and a frame in flight does not
    // overrule that.
    if (stop_requested && stop_requested()) {
      outcome_ = Outcome::kStopRequested;
      return outcome_;
    }
    // The deadline is re-checked after assembly. A complete frame that arrives
    // after the window closed is a late release, not a valid one; the OS may
    // still hand us the bytes, and reporting them as valid would make the
    // bounded-wait evidence untrue.
    if (now_ns() >= deadline_ns) {
      outcome_ = Outcome::kPartialFrame;
      return outcome_;
    }
    outcome_ = decode_release(frame_, identity_);
    if (outcome_ == Outcome::kReleased) released_ = true;
    return outcome_;
  }

  bool released() const { return released_; }

  /// The gate's own clock, injectable for tests that must pin the boundary.
  using Clock = std::function<int64_t()>;
  void set_clock(Clock clock) { clock_ = std::move(clock); }

  static constexpr int64_t kSliceNs = 50000000;  // 50 ms per wait slice

  static int64_t default_now_ns();
  int64_t now_ns() const { return clock_ ? clock_() : default_now_ns(); }

  Reader * reader_ = nullptr;
  Identity identity_{};
  int64_t timeout_ns_ = 0;
  Clock clock_;
  uint8_t frame_[kFrameBytes] = {};
  Outcome outcome_ = Outcome::kNotConfigured;
  bool done_ = false;
  bool released_ = false;
};

inline int64_t Gate::default_now_ns() {
  struct timespec ts{};
  ::clock_gettime(CLOCK_MONOTONIC, &ts);
  return int64_t(ts.tv_sec) * 1000000000LL + int64_t(ts.tv_nsec);
}

}  // namespace w2_gate
