// Copyright 2026 USV Developer
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
// THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.
#include "usv_nmpc/p1_input_core.hpp"

#include <limits>
#include <stdexcept>

namespace usv_mpc
{
Eigen::MatrixXd build_frozen_reference(
  const Vector6d & current_state, const ReferenceInput & input,
  int N, double dt, int offset, double cruise, ReferenceMetadata * evidence)
{
  return build_frozen_reference(current_state, input, N, dt, offset, cruise,
           ReferenceOptions{}, evidence);
}

Eigen::MatrixXd build_frozen_reference(
  const Vector6d & current_state, const ReferenceInput & input,
  int N, double dt, int offset, double cruise, const ReferenceOptions & options,
  ReferenceMetadata * evidence)
{
  const bool request_projection = options.projection_mode == "polyline_time";
  if (!request_projection && options.projection_mode != "discrete_offset") {
    throw std::invalid_argument("unknown reference projection mode");
  }
  if (!std::isfinite(options.lead_s) || (options.lead_s < 0.0 && options.lead_s != -1.0)) {
    throw std::invalid_argument("reference lead must be nonnegative or -1");
  }

  Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(6, N + 1);
  const auto & path = input.path;
  if (evidence) {
    evidence->horizon_steps = static_cast<uint32_t>(N);
    evidence->prediction_dt = dt;
    evidence->path_received_sequence = input.path_sequence;
    evidence->profile_received_sequence = input.profile_sequence;
    evidence->path_stamp_ns = input.path_stamp.first < 0 ? -1 :
      int64_t(input.path_stamp.first) * 1000000000LL + input.path_stamp.second;
    evidence->profile_stamp_known = input.profile_stamp.first >= 0;
    evidence->profile_stamp_ns = !evidence->profile_stamp_known ? -1 :
      int64_t(input.profile_stamp.first) * 1000000000LL + input.profile_stamp.second;
    evidence->path_size = path.size();
    evidence->profile_size = input.profile.size();
    evidence->nearest_index = -1;
    evidence->start_index = -1;
    evidence->configured_start_offset = offset;
    evidence->effective_start_offset = std::max(1, offset);
    evidence->reference_mode = "empty_path";
    evidence->profile_sync_reason = "empty_path";
    evidence->projection_mode = "discrete_offset";
    evidence->lead_s = -1.0;
  }

  if (path.empty()) {return ref;}

  // profile 同步判定
  int profile_len = input.profile.empty() ? -1 : static_cast<int>(input.profile.size());
  const std::pair<int,
    int> * p_stamp = (input.profile_stamp.first >= 0) ? &input.profile_stamp : nullptr;
  const std::pair<int,
    int> * path_stamp = (input.path_stamp.first >= 0) ? &input.path_stamp : nullptr;
  auto [synced, sync_reason] = profile_sync_state(
      static_cast<int>(path.size()), profile_len, path_stamp, p_stamp);

  const bool project = request_projection && synced;
  const int last = static_cast<int>(path.size()) - 1;
  const double px = current_state(0), py = current_state(1);
  double best_d = project ? std::numeric_limits<double>::infinity() : 1e18;
  int nearest = 0;
  for (size_t i = 0; i < path.size(); ++i) {
    const double dx = path[i][0] - px, dy = path[i][1] - py;
    const double d = project ? dx * dx + dy * dy : std::hypot(dx, dy);
    if (d < best_d) {best_d = d; nearest = static_cast<int>(i);}
  }
  int idx = std::min(nearest + std::max(1, offset), last);
  double alpha = 0.0;
  double lead = -1.0;
  if (project) {
    const int first_segment = std::max(0, nearest - 1);
    double best_segment_d2 = std::numeric_limits<double>::infinity();
    for (int i = first_segment; i <= std::min(nearest, last - 1); ++i) {
      const auto & a = path[i];
      const auto & b = path[i + 1];
      const double dx = b[0] - a[0], dy = b[1] - a[1];
      const double length2 = dx * dx + dy * dy;
      const double fraction = length2 <= 1e-12 ? 0.0 :
        std::clamp(((px - a[0]) * dx + (py - a[1]) * dy) / length2, 0.0, 1.0);
      const double ex = length2 <= 1e-12 ? px - a[0] : px - (a[0] + fraction * dx);
      const double ey = length2 <= 1e-12 ? py - a[1] : py - (a[1] + fraction * dy);
      const double d2 = ex * ex + ey * ey;
      if (i == first_segment || d2 < best_segment_d2) {
        best_segment_d2 = d2;
        idx = i;
        alpha = fraction;
      }
    }
    lead = options.lead_s >= 0.0 ? options.lead_s : static_cast<double>(std::max(1, offset)) * dt;
  }

  if (evidence) {
    evidence->nearest_index = nearest; evidence->start_index = idx;
    if (project) {
      evidence->projection_mode = "polyline_time";
      evidence->lead_s = lead;
    }
    evidence->profile_synced = synced; evidence->profile_sync_reason = sync_reason;
    evidence->reference_mode = synced ? "profile_time" : "cruise_arc_fallback";
  }
  if (synced) {
    std::vector<double> times(input.profile.size()), vs(input.profile.size()),
    rs(input.profile.size());
    for (size_t i = 0; i < input.profile.size(); ++i) {
      times[i] = input.profile[i][3]; vs[i] = input.profile[i][0]; rs[i] = input.profile[i][2];
    }
    double t0 = times[idx];
    if (project) {
      const double t_proj = t0 + alpha * (times[idx + 1] - t0);
      t0 = t_proj + lead;
    }
    if (evidence) {evidence->profile_t0_known = true; evidence->profile_t0 = t0;}
    int j = idx;
    for (int k = 0; k <= N; ++k) {
      double tk = t0 + k * dt;
      RefSample s = sample_path_profile_at_time(path, times, vs, rs, tk, j);
      ref(0, k) = s.x; ref(1, k) = s.y; ref(2, k) = s.psi;
      ref(3, k) = s.v; ref(4, k) = 0.0; ref(5, k) = s.r;
      j = s.j;
    }
  } else {
    // 回退: 匀速弧长采样
    std::vector<double> arc;
    arc.push_back(0.0);
    for (int i = idx; i < static_cast<int>(path.size()) - 1; ++i) {
      arc.push_back(arc.back() + std::hypot(path[i + 1][0] - path[i][0],
          path[i + 1][1] - path[i][1]));
    }
    for (int k = 0; k <= N; ++k) {
      double s_des = cruise * dt * k;
      int j = 0;
      while (j < static_cast<int>(arc.size()) - 1 && arc[j + 1] < s_des) {++j;}
      int ii = std::min(idx + j, static_cast<int>(path.size()) - 1);
      if (ii < static_cast<int>(path.size()) - 1 && j < static_cast<int>(arc.size()) - 1) {
        double seg_len = arc[j + 1] - arc[j];
        if (seg_len > 1e-6) {
          double t = std::clamp((s_des - arc[j]) / seg_len, 0.0, 1.0);
          ref(0, k) = path[ii][0] + t * (path[ii + 1][0] - path[ii][0]);
          ref(1, k) = path[ii][1] + t * (path[ii + 1][1] - path[ii][1]);
          double dpsi = normalize_angle(path[ii + 1][2] - path[ii][2]);
          ref(2, k) = normalize_angle(path[ii][2] + t * dpsi);
        } else {
          ref(0, k) = path[ii][0]; ref(1, k) = path[ii][1]; ref(2, k) = path[ii][2];
        }
      } else {
        ref(0, k) = path[ii][0]; ref(1, k) = path[ii][1]; ref(2, k) = path[ii][2];
      }
      ref(3, k) = cruise; ref(4, k) = 0.0; ref(5, k) = 0.0;
    }
  }

  // 航向角连续化展开 (Phase Unwrapping):
  // 保证 ref(2, 0) 与 current_state(2) 无 ±2pi 阶跃,
  // 且 ref(2, k) 在时域内连续, 消除 ±pi 边界处的 360° 虚假跳跃
  ref(2, 0) = current_state(2) + normalize_angle(ref(2, 0) - current_state(2));
  for (int k = 1; k <= N; ++k) {
    ref(2, k) = ref(2, k - 1) + normalize_angle(ref(2, k) - ref(2, k - 1));
  }

  return ref;
}
}  // namespace usv_mpc
