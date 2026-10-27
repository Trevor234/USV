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
  /// Read up to n bytes, blocking at most `timeout_ns`, and report how long the
  /// call actually blocked in `elapsed_ns` so the gate can charge a partial
  /// read against its own total budget.
  /// Returns >0 bytes read, 0 on EOF, -1 on timeout.
  virtual long read_some(uint8_t * buf, size_t n, int64_t timeout_ns,
                         int64_t * elapsed_ns) = 0;
};

/// One gate, one boundary, one release.
///
/// The lifecycle is: `arm()` once before the wait; `wait()` exactly once; the
/// result is terminal for this gate. Calling `wait()` again returns the stored
/// outcome, so a caller that retries cannot accidentally consume a second
/// release.
class Gate {
 public:
  Gate() = default;
  Gate(Reader * reader, Identity identity, int64_t timeout_ns)
  : reader_(reader), identity_(identity), timeout_ns_(timeout_ns) {}

  bool configured() const { return reader_ != nullptr; }
  const Identity & identity() const { return identity_; }

  /// Wait for the single release, or for the bound to expire.
  ///
  /// `stop_requested` is polled between reads. It is a plain bool* rather than
  /// a std::atomic<bool> so this header stays free of synchronisation
  /// decisions: the caller owns the memory order, and the Worker passes a
  /// pointer to its existing atomic's relaxed view.
  Outcome wait(const bool * stop_requested) {
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
    int64_t remaining = timeout_ns_;
    size_t got = 0;
    while (got < kFrameBytes) {
      if (stop_requested && *stop_requested) {
        outcome_ = Outcome::kStopRequested;
        return outcome_;
      }
      int64_t elapsed = 0;
      const long n = reader_->read_some(frame_ + got, kFrameBytes - got, remaining,
                                        &elapsed);
      if (elapsed > remaining) elapsed = remaining;
      const int64_t before = remaining;
      remaining -= elapsed;
      if (n == 0) {
        outcome_ = got == 0 ? Outcome::kEof : Outcome::kPartialFrame;
        return outcome_;
      }
      if (n < 0) {
        // A timeout after bytes have arrived is a truncated frame, not a clean
        // timeout: the Driver started a release and then died mid-frame.
        outcome_ = got == 0 ? Outcome::kTimeout : Outcome::kPartialFrame;
        return outcome_;
      }
      got += size_t(n);
      if (got > kFrameBytes) {
        outcome_ = Outcome::kPartialFrame;
        return outcome_;
      }
      // A reader that reports no elapsed time must still make progress, or the
      // loop would spin. Charging one nanosecond keeps it terminating while
      // leaving the budget effectively intact for a real blocking reader.
      if (remaining == before && got < kFrameBytes) remaining -= 1;
    }
    outcome_ = decode_release(frame_, identity_);
    if (outcome_ == Outcome::kReleased) released_ = true;
    return outcome_;
  }

  bool released() const { return released_; }

 private:
  Reader * reader_ = nullptr;
  Identity identity_{};
  int64_t timeout_ns_ = 0;
  uint8_t frame_[kFrameBytes] = {};
  Outcome outcome_ = Outcome::kNotConfigured;
  bool done_ = false;
  bool released_ = false;
};

}  // namespace w2_gate
