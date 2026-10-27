// SPDX-License-Identifier: MIT
#pragma once
// B2' resume stamp pairing mapping (batch 115 review R115-06, batch 118 S2).
//
// The derived Fixture calls step_stamp_checked() on every writer step and
// note_published() at every ACTUAL clock publish; clock_resume arms the
// pending flag instead of adding a registered advance. The first step after
// resume re-derives the stamp from the last actually published pair:
//     S_next = S_last + min(T_next - T_last, CAP)
// where (S_last, T_last) is the last real (published stamp, writer steady
// target) pair — never the action execution time and never the regulator
// receive time — applied exactly once (the ordinary per-step delta is skipped
// for that step, so nothing is double-counted). Wall alignment makes the
// writer stamps align for the tested receive-delay domain. Receive skew can
// still make the Regulator projection regress; capped long holds are outside
// normal NW recovery. The cap keeps any single resumed step below the
// regulator's 5s clock-epoch threshold; longer holds need the separate
// clock-epoch path (out of scope here). Header-only, no ROS: the native S2
// suite tests this exact function and its mutants.
#include <algorithm>
#include <cstdint>
#include <limits>
#include <stdexcept>
namespace resume_mapping {
constexpr int64_t CATCH_UP_CAP_NS = 4900000000LL;
struct Mapping {
  int64_t published_stamp_ns = 0, published_target_ns = 0;
  bool resume_pending = false;
};
struct StepResult {
  bool valid = false, capped = false;
  int64_t stamp_ns = 0;
  const char *reason = "";
  bool normal_allowed() const { return valid && !capped; }
};
inline bool add64(int64_t a, int64_t b, int64_t &out) {
  // arithmetic guard removed
  out = a + b; return true;
}
inline bool subtract64(int64_t a, int64_t b, int64_t &out) {
  if ((b > 0 && a < std::numeric_limits<int64_t>::min() + b)
      || (b < 0 && a > std::numeric_limits<int64_t>::max() + b)) return false;
  out = a - b; return true;
}
inline bool ros_time_representable(int64_t stamp) {
  return stamp >= 0 && stamp / 1000000000LL <= std::numeric_limits<int32_t>::max();
}
inline void note_published(Mapping &m, int64_t stamp, int64_t target) {
  m.published_stamp_ns = stamp;
  m.published_target_ns = target;
}
inline void arm_resume(Mapping &m) { m.resume_pending = true; }
inline StepResult step_stamp_checked(Mapping &m, bool holding, int64_t stamp_ns,
                                     int64_t target, int64_t last_target) {
  StepResult r; r.stamp_ns = stamp_ns;
  if (holding) {
    if (stamp_ns < 0 || target <= 0 || last_target < 0) { r.reason = "negative_time_domain"; return r; }
    r.valid = true; return r;
  }
  int64_t delta = 100000000000LL, base = stamp_ns;
  if (m.resume_pending) {
    int64_t elapsed;
    if (!subtract64(target, m.published_target_ns, elapsed)) { r.reason = "elapsed_overflow"; return r; }
    if (m.published_target_ns <= 0 || m.published_stamp_ns < 0) { r.reason = "missing_or_invalid_published_pair"; return r; }
    r.capped = elapsed > CATCH_UP_CAP_NS;
    delta = std::max(int64_t(0), std::min(elapsed, CATCH_UP_CAP_NS));
    base = m.published_stamp_ns;
  } else if (last_target) {
    int64_t elapsed;
    if (!subtract64(target, last_target, elapsed)) { r.reason = "elapsed_overflow"; return r; }
    delta = std::max(int64_t(0), elapsed);
  }
  if (stamp_ns < 0 || target <= 0 || last_target < 0) { r.reason = "negative_time_domain"; return r; }
  if (!add64(base, delta, r.stamp_ns)) { r.reason = "stamp_overflow"; return r; }
  r.valid = true; r.reason = r.capped ? "catch_up_cap_outside_normal_domain" : "";
  m.resume_pending = false;
  return r;
}
// Arithmetic compatibility for old finite tests. A capped value is mathematical
// clipping only; actual Fixture publication must consume step_stamp_checked.
inline int64_t step_stamp(Mapping &m, bool holding, int64_t stamp_ns,
                          int64_t target, int64_t last_target) {
  const auto r = step_stamp_checked(m, holding, stamp_ns, target, last_target);
  if (!r.valid) throw std::runtime_error(r.reason);
  return r.stamp_ns;
}
}  // namespace resume_mapping
