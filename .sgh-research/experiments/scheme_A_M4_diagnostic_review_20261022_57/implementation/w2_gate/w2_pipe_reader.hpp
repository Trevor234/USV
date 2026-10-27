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
    if (elapsed_ns) *elapsed_ns = 0;
    // An invalid fd is not a timeout: returning -1 would make the gate sit for
    // its whole budget on a descriptor that can never produce a byte. Report it
    // as EOF with no elapsed time so the gate names it immediately.
    if (fd_ < 0 || n == 0) return 0;

    // poll() takes milliseconds and rounds up: rounding down would let a 1 ns
    // budget return immediately with a spurious timeout.
    const int64_t wait_ns = timeout_ns > 0 ? timeout_ns : 0;
    int timeout_ms = int((wait_ns + 999999) / 1000000);
    if (timeout_ms < 0 || timeout_ms > 3600000) timeout_ms = 3600000;

    struct pollfd pfd{};
    pfd.fd = fd_;
    pfd.events = POLLIN;

    int64_t waited_ns = 0;
    int64_t budget_ns = wait_ns;
    for (;;) {
      const int64_t slice_start_ns = monotonic_ns();
      const int rc = ::poll(&pfd, 1, timeout_ms);
      const int64_t slice_elapsed_ns = monotonic_ns() - slice_start_ns;
      if (rc < 0) {
        if (errno == EINTR) {
          // A signal is not a protocol outcome. Charge only the time actually
          // spent, then poll again with what remains of the budget. Charging
          // the whole requested slice here would let a single signal consume
          // the entire budget and turn EINTR into a spurious timeout.
          waited_ns += slice_elapsed_ns;
          if (waited_ns >= budget_ns) {
            if (elapsed_ns) *elapsed_ns = waited_ns;
            return -1;
          }
          const int64_t left = budget_ns - waited_ns;
          timeout_ms = int((left + 999999) / 1000000);
          if (timeout_ms <= 0) timeout_ms = 1;
          continue;
        }
        if (elapsed_ns) *elapsed_ns = waited_ns + slice_elapsed_ns;
        return -1;
      }
      if (rc == 0) {
        if (elapsed_ns) *elapsed_ns = slice_elapsed_ns;
        return -1;  // timeout
      }
      if (elapsed_ns) *elapsed_ns = slice_elapsed_ns;
      // POLLHUP/POLLERR with POLLIN still mean "read what is left, then EOF".
      const ssize_t got = ::read(fd_, buf, n);
      if (got < 0) {
        if (errno == EINTR) continue;
        if (errno == EAGAIN || errno == EWOULDBLOCK) return -1;
        return 0;  // treat an unreadable fd as EOF: the gate names it
      }
      return long(got);  // 0 is EOF, which the gate reports as eof/partial
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
