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


/**
 * @file utils.cpp
 * @brief 坐标变换与数学工具实现。
 */

#include "usv_mpc/utils.hpp"

#include <algorithm>
#include <cmath>
#include <sstream>

namespace usv_mpc
{

double normalize_angle(double angle)
{
  return std::atan2(std::sin(angle), std::cos(angle));
}

double quaternion_to_yaw(double qx, double qy, double qz, double qw)
{
  double siny_cosp = 2.0 * (qw * qz + qx * qy);
  double cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz);
  return std::atan2(siny_cosp, cosy_cosp);
}

std::pair<double, double> body_to_ned(double u, double v, double psi)
{
  double vx = u * std::cos(psi) - v * std::sin(psi);
  double vy = u * std::sin(psi) + v * std::cos(psi);
  return {vx, vy};
}

std::pair<double, double> ned_to_body(double vn, double ve, double psi)
{
  double u = vn * std::cos(psi) + ve * std::sin(psi);
  double v = -vn * std::sin(psi) + ve * std::cos(psi);
  return {u, v};
}

double cross_track_error(
  double x, double y, double x1, double y1,
  double x2, double y2)
{
  double dx = x2 - x1;
  double dy = y2 - y1;
  if (dx == 0.0 && dy == 0.0) {
    return std::hypot(x - x1, y - y1);
  }
  return ((x - x1) * dy - (y - y1) * dx) / std::hypot(dx, dy);
}

std::pair<int, int> parse_profile_stamp(
  const std::vector<std::string> & dim_labels, bool & ok)
{
  ok = false;
  int sec = -1, nanosec = -1;
  for (const auto & label : dim_labels) {
    if (label.rfind("stamp_sec:", 0) == 0) {
      try {
        sec = std::stoi(label.substr(10));
      } catch (...) {
        return {0, 0};
      }
    } else if (label.rfind("stamp_nanosec:", 0) == 0) {
      try {
        nanosec = std::stoi(label.substr(14));
      } catch (...) {
        return {0, 0};
      }
    }
  }
  if (sec < 0 || nanosec < 0) {return {0, 0};}
  ok = true;
  return {sec, nanosec};
}

std::pair<bool, std::string> profile_sync_state(
  int path_len, int profile_len,
  const std::pair<int, int> * path_stamp,
  const std::pair<int, int> * profile_stamp)
{
  if (profile_len < 0) {return {false, "no_profile"};}
  if (path_len < 2) {return {false, "path_too_short"};}
  if (profile_len != path_len) {return {false, "length_mismatch"};}
  if (profile_stamp == nullptr) {return {true, "legacy_no_profile_stamp"};}
  if (path_stamp == nullptr) {return {false, "missing_path_stamp"};}
  if (*profile_stamp != *path_stamp) {return {false, "stamp_mismatch"};}
  return {true, "stamp_match"};
}

RefSample sample_path_profile_at_time(
  const std::vector<std::array<double, 3>> & path,
  const std::vector<double> & times,
  const std::vector<double> & vs,
  const std::vector<double> & rs,
  double tk, int j_hint)
{
  int last = static_cast<int>(path.size()) - 1;
  int j = j_hint;
  while (j < last && times[j + 1] < tk) {
    ++j;
  }
  if (j >= last) {
    const auto & p = path[last];
    return {p[0], p[1], p[2], vs[last], rs[last], last};
  }
  double t_seg = times[j + 1] - times[j];
  double a = (t_seg > 1e-9) ?
    std::max(0.0, std::min(1.0, (tk - times[j]) / t_seg)) :
    0.0;
  double x = path[j][0] + a * (path[j + 1][0] - path[j][0]);
  double y = path[j][1] + a * (path[j + 1][1] - path[j][1]);
  double dpsi = normalize_angle(path[j + 1][2] - path[j][2]);
  double psi = normalize_angle(path[j][2] + a * dpsi);
  double v = vs[j] + a * (vs[j + 1] - vs[j]);
  double r = rs[j] + a * (rs[j + 1] - rs[j]);
  return {x, y, psi, v, r, j};
}

MonotonicProgressResult select_monotonic_nearest_index(
  const std::vector<std::array<double, 3>> & path,
  double x, double y,
  int prev_progress_index,
  const MonotonicProgressConfig & config)
{
  const int m = static_cast<int>(path.size());
  if (m <= 1 || !std::isfinite(x) || !std::isfinite(y)) {
    return {0, 0};
  }

  const int prev_idx = std::clamp(prev_progress_index, 0, m - 1);
  std::vector<double> arc(m, 0.0);
  for (int i = 1; i < m; ++i) {
    arc[i] = arc[i - 1] +
      std::hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]);
  }

  const double fwd_window = std::max(0.0, config.forward_window_m);
  const double back_window = std::max(0.0, config.back_window_m);
  const bool initial_search = config.is_initial || (prev_idx == 0);

  int lo = prev_idx;
  if (initial_search) {
    lo = 0;
  } else {
    while (lo > 0 && (arc[prev_idx] - arc[lo - 1]) <= back_window) {
      --lo;
    }
  }

  int hi = prev_idx;
  while (hi + 1 < m && (arc[hi + 1] - arc[prev_idx]) <= fwd_window) {
    ++hi;
  }

  if (initial_search && config.end_guard_m > 0.0 && arc.back() > config.end_guard_m && m >= 3) {
    int guard_limit = m - 2;
    while (guard_limit > 0 && (arc.back() - arc[guard_limit]) < config.end_guard_m) {
      --guard_limit;
    }
    hi = std::max(lo, std::min(hi, guard_limit));
  }

  double best_d = 1e18;
  int best_i = lo;
  for (int i = lo; i <= hi; ++i) {
    const double d = std::hypot(path[i][0] - x, path[i][1] - y);
    if (d < best_d) {
      best_d = d;
      best_i = i;
    }
  }

  const int next_progress = initial_search ? best_i : std::max(prev_idx, best_i);
  return {best_i, next_progress};
}

bool is_substantive_path_change(
  const std::vector<std::array<double, 3>> & old_path,
  const std::vector<std::array<double, 3>> & new_path,
  double tol_m)
{
  if (old_path.size() != new_path.size()) {
    return true;
  }
  if (new_path.empty()) {
    return false;
  }
  const double d_start = std::hypot(
    new_path.front()[0] - old_path.front()[0],
    new_path.front()[1] - old_path.front()[1]);
  const double d_end = std::hypot(
    new_path.back()[0] - old_path.back()[0],
    new_path.back()[1] - old_path.back()[1]);
  return (d_start > tol_m) || (d_end > tol_m);
}

bool is_goal_reached(
  const std::vector<std::array<double, 3>> & path,
  double x, double y,
  int progress_index,
  int start_offset,
  double goal_tolerance_m)
{
  if (path.size() < 2 || !std::isfinite(x) || !std::isfinite(y) ||
    !std::isfinite(goal_tolerance_m) || goal_tolerance_m <= 0.0)
  {
    return false;
  }
  const int m = static_cast<int>(path.size());
  const int end_margin = std::max(3, start_offset);
  const int min_progress = std::max(0, m - end_margin);
  if (progress_index < min_progress) {
    return false;
  }
  const double d_goal = std::hypot(x - path.back()[0], y - path.back()[1]);
  return d_goal < goal_tolerance_m;
}

double smooth_reference_heading(
  Eigen::MatrixXd & ref,
  double current_psi,
  double dt,
  double max_initial_step_rad,
  double align_turn_rate_rad_s,
  double align_min_speed_mps)
{
  if (ref.rows() < 3 || ref.cols() < 1 || !std::isfinite(current_psi)) {
    return 0.0;
  }
  ref(2, 0) = current_psi + normalize_angle(ref(2, 0) - current_psi);
  for (int k = 1; k < ref.cols(); ++k) {
    ref(2, k) = ref(2, k - 1) + normalize_angle(ref(2, k) - ref(2, k - 1));
  }

  const double raw_e0 = ref(2, 0) - current_psi;
  if (dt <= 0.0 || max_initial_step_rad <= 0.0 || align_turn_rate_rad_s <= 0.0 ||
    std::abs(raw_e0) <= max_initial_step_rad)
  {
    return raw_e0;
  }

  for (int k = 0; k < ref.cols(); ++k) {
    const double max_delta_k = align_turn_rate_rad_s * static_cast<double>(k + 1) * dt;
    const double desired_delta = ref(2, k) - current_psi;
    if (std::abs(desired_delta) > max_delta_k) {
      ref(2, k) = current_psi + std::copysign(max_delta_k, desired_delta);
    }
    if (ref.rows() >= 4 && align_min_speed_mps > 0.0) {
      ref(3, k) = std::max(ref(3, k), align_min_speed_mps);
    }
  }
  return raw_e0;
}

}  // namespace usv_mpc
