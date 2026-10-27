// SPDX-License-Identifier: MIT
//
// W2 release-channel entry contract.
//
// Extracted so the *production* Worker and the entry test run the same code.
// The 61 review's D5 found the previous test mirrored a hand-copied whitelist
// and therefore passed with the real Worker's parameters deleted: the test
// verified a copy, not the implementation.
//
// Two responsibilities, both pure:
//   * the exact set of W2 parameter names the strict override whitelist admits;
//   * the parameter-tuple and fd-direction rules the Worker applies at startup.
#pragma once

#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <fcntl.h>
#include <set>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

namespace w2_entry {

/// The five names the Driver passes. The Worker's strict whitelist includes
/// these in addition to its ordinary ones.
inline const std::set<std::string> & parameters() {
  static const std::set<std::string> names = {
      "w2_release_fd", "w2_release_job_id", "w2_release_ordinal",
      "w2_release_nonce", "w2_release_wait_ns"};
  return names;
}

/// The channel as the Worker sees it after validation.
struct Channel {
  int fd = -1;
  int64_t job_id = 0;
  int ordinal = 0;
  int nonce = 0;
  int64_t wait_budget_ns = 0;
  uint64_t device = 0;
  uint64_t inode = 0;
  bool read_only = false;
};

enum class Reject {
  kOk,
  kNoFdButOtherParametersSet,
  kNonZeroNonceWithoutFd,
  kNonceZero,
  kBindingOutOfRange,
  kFdDoesNotResolve,
  kNotAFifo,
  kNotReadOnly,
};

inline const char * reject_name(Reject r) {
  switch (r) {
    case Reject::kOk: return "ok";
    case Reject::kNoFdButOtherParametersSet:
      return "w2 release parameters given without an fd";
    case Reject::kNonZeroNonceWithoutFd: return "w2 nonce set without an fd";
    case Reject::kNonceZero: return "w2 release nonce must be non-zero";
    case Reject::kBindingOutOfRange:
      return "w2 release binding incomplete or out of bounds";
    case Reject::kFdDoesNotResolve: return "w2 release fd does not resolve";
    case Reject::kNotAFifo: return "w2 release fd is not a FIFO";
    case Reject::kNotReadOnly: return "w2 release fd is not read-only";
  }
  return "unknown";
}

/// Validate the parameter tuple and the inherited fd.
///
/// The fd checks are the ones 60/R3 fixed: `S_ISFIFO` identifies the object and
/// `F_GETFL` is the only way to learn direction, because both ends of a pipe
/// report the same `st_mode`.
inline Reject validate(int fd, int64_t job_id, int ordinal, int nonce,
                       int64_t wait_budget_ns, Channel * out) {
  if (fd < 0) {
    if (job_id >= 0 || ordinal != 0 || wait_budget_ns != 0) {
      return Reject::kNoFdButOtherParametersSet;
    }
    if (nonce != 0) return Reject::kNonZeroNonceWithoutFd;
    return Reject::kOk;  // ordinary profile
  }
  if (nonce == 0) return Reject::kNonceZero;
  if (job_id <= 0 || ordinal <= 0 || wait_budget_ns <= 0 ||
      wait_budget_ns > 2000000000LL) {
    return Reject::kBindingOutOfRange;
  }
  char path[64];
  std::snprintf(path, sizeof(path), "/proc/self/fd/%d", fd);
  char target[256] = {};
  const auto n = ::readlink(path, target, sizeof(target) - 1);
  if (n <= 0) return Reject::kFdDoesNotResolve;

  struct stat st {};
  if (::fstat(fd, &st) != 0 || !S_ISFIFO(st.st_mode)) return Reject::kNotAFifo;
  const int flags = ::fcntl(fd, F_GETFL);
  if (flags < 0 || (flags & O_ACCMODE) != O_RDONLY) {
    return Reject::kNotReadOnly;
  }
  if (out) {
    out->fd = fd;
    out->job_id = job_id;
    out->ordinal = ordinal;
    out->nonce = nonce;
    out->wait_budget_ns = wait_budget_ns;
    out->device = uint64_t(st.st_dev);
    out->inode = uint64_t(st.st_ino);
    out->read_only = true;
  }
  return Reject::kOk;
}

}  // namespace w2_entry
