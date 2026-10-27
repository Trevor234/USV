// SPDX-License-Identifier: MIT
#pragma once
// B2' resume stamp pairing mapping (batch 115 review R115-06, batch 118 S2).
//
// The production Fixture calls step_stamp() on every writer step and
// note_published() at every ACTUAL clock publish; clock_resume arms the
// pending flag instead of adding a registered advance. The first step after
// resume re-derives the stamp from the last actually published pair:
//     S_next = S_last + min(T_next - T_last, CAP)
// where (S_last, T_last) is the last real (published stamp, writer steady
// target) pair — never the action execution time and never the regulator
// receive time — applied exactly once (the ordinary per-step delta is skipped
// for that step, so nothing is double-counted). Wall alignment makes the
// regulator's post-resume engineering projection never fall below the output
// history written during the silence, removing the L844 regression trigger
// for this scenario class. The cap keeps any single resumed step below the
// regulator's 5s clock-epoch threshold; longer holds need the separate
// clock-epoch path (out of scope here). Header-only, no ROS: the native S2
// suite tests this exact function and its mutants.
#include <algorithm>
#include <cstdint>
namespace resume_mapping {
constexpr int64_t CATCH_UP_CAP_NS = 4900000000LL;
struct Mapping {
  int64_t published_stamp_ns = 0, published_target_ns = 0;
  bool resume_pending = false;
};
inline void note_published(Mapping &m, int64_t stamp, int64_t target) {
  m.published_stamp_ns = stamp;
  m.published_target_ns = target;
}
inline void arm_resume(Mapping &m) { m.resume_pending = true; }
inline int64_t step_stamp(Mapping &m, bool holding, int64_t stamp_ns,
                          int64_t target, int64_t last_target) {
  if (holding) return stamp_ns;
  if (m.resume_pending) {
    m.resume_pending = false;
    const int64_t elapsed = target - m.published_target_ns;
    const int64_t bounded = elapsed < 0 ? 0 : (elapsed > CATCH_UP_CAP_NS ? CATCH_UP_CAP_NS : elapsed);
    return m.published_stamp_ns + bounded;
  }
  return stamp_ns + (last_target ? std::max(int64_t(0), target - last_target) : 100000000000LL);
}
}  // namespace resume_mapping
