// SPDX-License-Identifier: MIT
//
// POSIX adapter for the W2 release gate's Reader interface.
//
// The gate itself is transport-agnostic; this file is the only part that knows
// about file descriptors. Keeping it separate means the state machine can be
// tested without a pipe, and the pipe behaviour can be tested for exactly the
// things a pipe does: EINTR, a write end that closes, a write end left open,
// and a frame split across writes.
//
// Two properties matter for the run's evidence, and both are the caller's to
// check rather than this adapter's:
//   * the descriptor must be the inherited read end of a pipe the Worker does
//     not own the write end of, otherwise EOF never arrives;
//   * the descriptor must not be the controlling terminal or a shared socket,
//     so `configured()` only proves "an fd was handed over", not "it is the
//     right fd".
#pragma once

#include <cerrno>
#include <cstdint>
#include <poll.h>
#include <ctime>
#include <unistd.h>

#include "w2_release_gate.hpp"

namespace w2_gate {

/// Reads release frames from one pipe read end with a bounded wait.
///
/// `read_some` never blocks longer than its budget, and it reports how long it
/// blocked so the gate can charge a partial read against the total. A poll that
/// times out returns -1; a poll interrupted by a signal is retried (EINTR is
/// not a protocol event), but the retry is charged to the remaining budget by
/// the gate, not by this class.
class PipeReader final : public Reader {
 public:
  /// `fd` is inherited and owned by the caller; this class never closes it.
  explicit PipeReader(int fd) : fd_(fd) {}

  bool valid() const { return fd_ >= 0; }
  int fd() const { return fd_; }

  long read_some(uint8_t * buf, size_t n, int64_t timeout_ns,
                 int64_t * elapsed_ns) override {
    // Every return path below reports against this one origin. Reporting only
    // the last poll's duration would hide the waits consumed before an EINTR
    // retry; the gate would then think it had budget it had already spent.
    const int64_t call_start_ns = monotonic_ns();
    const auto finish = [&](long rc) -> long {
      if (elapsed_ns) *elapsed_ns = monotonic_ns() - call_start_ns;
      return rc;
    };

    // An invalid fd is not a timeout: returning -1 would make the gate sit for
    // its whole budget on a descriptor that can never produce a byte. Report it
    // as EOF so the gate names it immediately.
    if (fd_ < 0 || n == 0) return finish(0);

    // The budget is an absolute instant, not a decrementing counter, so an
    // interrupted poll cannot hand the retry a fresh full window.
    const int64_t deadline_ns = call_start_ns + (timeout_ns > 0 ? timeout_ns : 0);

    struct pollfd pfd{};
    pfd.fd = fd_;
    pfd.events = POLLIN;

    for (;;) {
      const int64_t left = deadline_ns - monotonic_ns();
      if (left <= 0) return finish(-1);
      // poll() takes milliseconds and rounds up: rounding down would turn a
      // positive budget into an immediate spurious timeout.
      int timeout_ms = int((left + 999999) / 1000000);
      if (timeout_ms <= 0) timeout_ms = 1;

      const int rc = ::poll(&pfd, 1, timeout_ms);
      if (rc < 0) {
        if (errno == EINTR) {
          // A signal is not a protocol outcome. The deadline above already
          // charged the interrupted wait, so simply poll again with what is
          // left; if nothing is left the next iteration returns -1.
          continue;
        }
        return finish(-1);
      }
      if (rc == 0) return finish(-1);  // slice expired; the gate decides

      // POLLHUP/POLLERR with POLLIN still mean "read what is left, then EOF".
      const ssize_t got = ::read(fd_, buf, n);
      if (got < 0) {
        if (errno == EINTR) continue;
        if (errno == EAGAIN || errno == EWOULDBLOCK) return finish(-1);
        return finish(0);  // unreadable fd: report EOF, the gate names it
      }
      return finish(long(got));  // 0 is EOF, which the gate reports as eof/partial
    }
  }

 private:
  static int64_t monotonic_ns() {
    struct timespec ts{};
    ::clock_gettime(CLOCK_MONOTONIC, &ts);
    return int64_t(ts.tv_sec) * 1000000000LL + int64_t(ts.tv_nsec);
  }

  int fd_;
};

}  // namespace w2_gate
