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

#include "usv_nmpc/utils.hpp"

#include <algorithm>
#include <cmath>
#include <sstream>
#include <stdexcept>

namespace usv_mpc {

double normalize_angle(double angle) {
  return std::atan2(std::sin(angle), std::cos(angle));
}

double quaternion_to_yaw(double qx, double qy, double qz, double qw) {
  double siny_cosp = 2.0 * (qw * qz + qx * qy);
  double cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz);
  return std::atan2(siny_cosp, cosy_cosp);
}

std::pair<double, double> body_to_ned(double u, double v, double psi) {
  double vx = u * std::cos(psi) - v * std::sin(psi);
  double vy = u * std::sin(psi) + v * std::cos(psi);
  return {vx, vy};
}

std::pair<double, double> ned_to_body(double vn, double ve, double psi) {
  double u = vn * std::cos(psi) + ve * std::sin(psi);
  double v = -vn * std::sin(psi) + ve * std::cos(psi);
  return {u, v};
}

RcActuationResult thrust_to_rc_actuation(
    const Eigen::Vector2d& thrust, const RcActuationConfig& config) {
  if (!thrust.allFinite() || !std::isfinite(config.thrust_max) ||
      !std::isfinite(config.thrust_min) ||
      !std::isfinite(config.steering_sign) ||
      !std::isfinite(config.throttle_sign) ||
      !std::isfinite(config.steering_gain) ||
      !std::isfinite(config.throttle_gain) ||
      !std::isfinite(config.deadband_min_thrust_n) ||
      !std::isfinite(config.quad_coeff_a) ||
      !std::isfinite(config.quad_coeff_b) || config.thrust_max <= 0.0 ||
      config.thrust_min > 0.0 || config.pwm_min >= config.pwm_center ||
      config.pwm_center >= config.pwm_max ||
      config.pwm_deadband_reverse < config.pwm_min ||
      config.pwm_deadband_reverse > config.pwm_center ||
      config.pwm_deadband_forward < config.pwm_center ||
      config.pwm_deadband_forward >= config.pwm_max ||
      config.deadband_min_thrust_n < 0.0 || config.quad_coeff_a < 0.0 ||
      config.quad_coeff_b <= 0.0 ||
      std::abs(std::abs(config.steering_sign) - 1.0) > 1e-9 ||
      std::abs(std::abs(config.throttle_sign) - 1.0) > 1e-9 ||
      config.steering_gain < 0.0 || config.throttle_gain < 0.0) {
    throw std::invalid_argument("invalid RC actuation mapping");
  }

  const double reverse_scale =
      (config.thrust_min < 0.0) ? -config.thrust_min : config.thrust_max;
  const double steering_scale = std::max(config.thrust_max, reverse_scale);
  const double left =
      std::clamp(thrust(0), config.thrust_min, config.thrust_max);
  const double right =
      std::clamp(thrust(1), config.thrust_min, config.thrust_max);

  const double requested_surge = 0.5 * (left + right);
  const double requested_yaw = 0.5 * (right - left);

  const auto to_pwm_linear = [&](double axis) {
    axis = std::clamp(axis, -1.0, 1.0);
    const double pwm = (axis >= 0.0)
        ? config.pwm_center + axis * (config.pwm_max - config.pwm_center)
        : config.pwm_center + axis * (config.pwm_center - config.pwm_min);
    return static_cast<int>(std::clamp(
        std::round(pwm), static_cast<double>(config.pwm_min),
        static_cast<double>(config.pwm_max)));
  };
  const auto from_pwm_linear = [&](int pwm) {
    pwm = std::clamp(pwm, config.pwm_min, config.pwm_max);
    if (pwm >= config.pwm_center) {
      return static_cast<double>(pwm - config.pwm_center) /
             (config.pwm_max - config.pwm_center);
    }
    return static_cast<double>(pwm - config.pwm_center) /
           (config.pwm_center - config.pwm_min);
  };

  RcActuationResult result;
  double applied_surge = 0.0;
  double applied_yaw = 0.0;

  if (!config.deadband_compensation) {
    const double surge_scale =
        (requested_surge >= 0.0) ? config.thrust_max : reverse_scale;
    const double throttle_axis = config.throttle_sign * config.throttle_gain *
        std::clamp(requested_surge / surge_scale, -1.0, 1.0);
    const double steering_axis = config.steering_sign * config.steering_gain *
        std::clamp(requested_yaw / steering_scale, -1.0, 1.0);

    result.steering_pwm = to_pwm_linear(steering_axis);
    result.throttle_pwm = to_pwm_linear(throttle_axis);

    const double applied_throttle_axis =
        config.throttle_sign * from_pwm_linear(result.throttle_pwm);
    const double applied_steering_axis =
        config.steering_sign * from_pwm_linear(result.steering_pwm);
    const double applied_surge_scale =
        (applied_throttle_axis >= 0.0) ? config.thrust_max : reverse_scale;
    applied_surge = applied_throttle_axis * applied_surge_scale;
    applied_yaw = applied_steering_axis * steering_scale;
  } else {
    // 1) 油门通道: 小于防抖门限回中 1500; 否则直接跳过死区并按二次或线性反解
    if (std::abs(requested_surge) <= config.deadband_min_thrust_n) {
      result.throttle_pwm = config.pwm_center;
      applied_surge = 0.0;
    } else if (config.use_quadratic_model) {
      const double mag = std::abs(requested_surge);
      const double a = config.quad_coeff_a;
      const double b = config.quad_coeff_b;
      const double delta_pwm_mag = (a > 0.0)
          ? (-b + std::sqrt(b * b + 4.0 * a * mag)) / (2.0 * a)
          : (mag / b);
      const double delta_pwm_scaled = config.throttle_gain * delta_pwm_mag;
      const double throttle_dir =
          config.throttle_sign * ((requested_surge >= 0.0) ? 1.0 : -1.0);
      if (throttle_dir >= 0.0) {
        result.throttle_pwm = static_cast<int>(std::clamp(
            std::round(config.pwm_deadband_forward + delta_pwm_scaled),
            static_cast<double>(config.pwm_deadband_forward),
            static_cast<double>(config.pwm_max)));
      } else {
        result.throttle_pwm = static_cast<int>(std::clamp(
            std::round(config.pwm_deadband_reverse - delta_pwm_scaled),
            static_cast<double>(config.pwm_min),
            static_cast<double>(config.pwm_deadband_reverse)));
      }

      if (result.throttle_pwm >= config.pwm_deadband_forward) {
        const double d = static_cast<double>(
            result.throttle_pwm - config.pwm_deadband_forward);
        const double applied_mag = a * d * d + b * d;
        const double max_scale =
            (config.throttle_sign >= 0.0) ? config.thrust_max : reverse_scale;
        applied_surge = config.throttle_sign * std::min(max_scale, applied_mag);
      } else if (result.throttle_pwm <= config.pwm_deadband_reverse) {
        const double d = static_cast<double>(
            config.pwm_deadband_reverse - result.throttle_pwm);
        const double applied_mag = a * d * d + b * d;
        const double max_scale =
            (config.throttle_sign >= 0.0) ? reverse_scale : config.thrust_max;
        applied_surge = -config.throttle_sign * std::min(max_scale, applied_mag);
      } else {
        applied_surge = 0.0;
      }
    } else {
      const double surge_scale =
          (requested_surge >= 0.0) ? config.thrust_max : reverse_scale;
      const double throttle_axis = std::clamp(
          config.throttle_sign * config.throttle_gain *
              std::clamp(requested_surge / surge_scale, -1.0, 1.0),
          -1.0, 1.0);
      if (throttle_axis >= 0.0) {
        result.throttle_pwm = static_cast<int>(std::clamp(
            std::round(config.pwm_deadband_forward +
                       throttle_axis * (config.pwm_max - config.pwm_deadband_forward)),
            static_cast<double>(config.pwm_deadband_forward),
            static_cast<double>(config.pwm_max)));
      } else {
        result.throttle_pwm = static_cast<int>(std::clamp(
            std::round(config.pwm_deadband_reverse +
                       throttle_axis * (config.pwm_deadband_reverse - config.pwm_min)),
            static_cast<double>(config.pwm_min),
            static_cast<double>(config.pwm_deadband_reverse)));
      }

      double applied_axis = 0.0;
      if (result.throttle_pwm >= config.pwm_deadband_forward) {
        applied_axis = static_cast<double>(
            result.throttle_pwm - config.pwm_deadband_forward) /
            (config.pwm_max - config.pwm_deadband_forward);
      } else if (result.throttle_pwm <= config.pwm_deadband_reverse) {
        applied_axis = static_cast<double>(
            result.throttle_pwm - config.pwm_deadband_reverse) /
            (config.pwm_deadband_reverse - config.pwm_min);
      }
      const double signed_axis = config.throttle_sign * applied_axis;
      const double applied_surge_scale =
          (signed_axis >= 0.0) ? config.thrust_max : reverse_scale;
      applied_surge = signed_axis * applied_surge_scale;
    }

    // 2) 转向通道: 维持线性连续比例控制 (防巡航微调跳变), 小于防抖门限回中
    if (std::abs(requested_yaw) <= config.deadband_min_thrust_n) {
      result.steering_pwm = config.pwm_center;
      applied_yaw = 0.0;
    } else {
      const double steering_axis = config.steering_sign * config.steering_gain *
          std::clamp(requested_yaw / steering_scale, -1.0, 1.0);
      result.steering_pwm = to_pwm_linear(steering_axis);
      const double applied_steering_axis =
          config.steering_sign * from_pwm_linear(result.steering_pwm);
      applied_yaw = applied_steering_axis * steering_scale;
    }
  }

  result.effective_thrust(0) = std::clamp(
      applied_surge - applied_yaw, config.thrust_min, config.thrust_max);
  result.effective_thrust(1) = std::clamp(
      applied_surge + applied_yaw, config.thrust_min, config.thrust_max);
  return result;
}

Eigen::Vector2d apply_large_heading_forward_assist(
    const Eigen::Vector2d& thrust,
    double abs_heading_error_rad,
    double surge_speed_mps,
    const LargeHeadingAssistConfig& config) {
  if (!config.enabled || !thrust.allFinite() ||
      !std::isfinite(abs_heading_error_rad) ||
      !std::isfinite(surge_speed_mps)) {
    return thrust;
  }
  if (std::abs(abs_heading_error_rad) <= config.heading_threshold_rad ||
      surge_speed_mps >= config.speed_threshold_mps) {
    return thrust;
  }

  const double floor_n = std::max(config.thrust_min, config.reverse_thrust_floor_n);
  double tl = std::max(thrust(0), floor_n);
  double tr = std::max(thrust(1), floor_n);

  const double target_net = std::min(config.min_net_thrust_n, 2.0 * config.thrust_max);
  if (tl + tr < target_net) {
    const double deficit = target_net - (tl + tr);
    tl += 0.5 * deficit;
    tr += 0.5 * deficit;
    if (tl > config.thrust_max) {
      tr += (tl - config.thrust_max);
      tl = config.thrust_max;
    } else if (tr > config.thrust_max) {
      tl += (tr - config.thrust_max);
      tr = config.thrust_max;
    }
  }

  return Eigen::Vector2d(
      std::clamp(tl, config.thrust_min, config.thrust_max),
      std::clamp(tr, config.thrust_min, config.thrust_max));
}

double cross_track_error(double x, double y, double x1, double y1,
                         double x2, double y2) {
  double dx = x2 - x1;
  double dy = y2 - y1;
  if (dx == 0.0 && dy == 0.0) {
    return std::hypot(x - x1, y - y1);
  }
  return ((x - x1) * dy - (y - y1) * dx) / std::hypot(dx, dy);
}

std::pair<int, int> parse_profile_stamp(
    const std::vector<std::string>& dim_labels, bool& ok) {
  ok = false;
  int sec = -1, nanosec = -1;
  for (const auto& label : dim_labels) {
    if (label.rfind("stamp_sec:", 0) == 0) {
      try {
        sec = std::stoi(label.substr(10));
      } catch (...) { return {0, 0}; }
    } else if (label.rfind("stamp_nanosec:", 0) == 0) {
      try {
        nanosec = std::stoi(label.substr(14));
      } catch (...) { return {0, 0}; }
    }
  }
  if (sec < 0 || nanosec < 0) return {0, 0};
  ok = true;
  return {sec, nanosec};
}

std::pair<bool, std::string> profile_sync_state(
    int path_len, int profile_len,
    const std::pair<int, int>* path_stamp,
    const std::pair<int, int>* profile_stamp) {
  if (profile_len < 0) return {false, "no_profile"};
  if (path_len < 2) return {false, "path_too_short"};
  if (profile_len != path_len) return {false, "length_mismatch"};
  if (profile_stamp == nullptr) return {true, "legacy_no_profile_stamp"};
  if (path_stamp == nullptr) return {false, "missing_path_stamp"};
  if (*profile_stamp != *path_stamp) return {false, "stamp_mismatch"};
  return {true, "stamp_match"};
}

RefSample sample_path_profile_at_time(
    const std::vector<std::array<double, 3>>& path,
    const std::vector<double>& times,
    const std::vector<double>& vs,
    const std::vector<double>& rs,
    double tk, int j_hint) {
  int last = static_cast<int>(path.size()) - 1;
  int j = j_hint;
  while (j < last && times[j + 1] < tk) {
    ++j;
  }
  if (j >= last) {
    const auto& p = path[last];
    return {p[0], p[1], p[2], vs[last], rs[last], last};
  }
  double t_seg = times[j + 1] - times[j];
  double a = (t_seg > 1e-9)
                 ? std::max(0.0, std::min(1.0, (tk - times[j]) / t_seg))
                 : 0.0;
  double x = path[j][0] + a * (path[j + 1][0] - path[j][0]);
  double y = path[j][1] + a * (path[j + 1][1] - path[j][1]);
  double dpsi = normalize_angle(path[j + 1][2] - path[j][2]);
  double psi = normalize_angle(path[j][2] + a * dpsi);
  double v = vs[j] + a * (vs[j + 1] - vs[j]);
  double r = rs[j] + a * (rs[j + 1] - rs[j]);
  return {x, y, psi, v, r, j};
}

MonotonicProgressResult select_monotonic_nearest_index(
    const std::vector<std::array<double, 3>>& path,
    double x, double y,
    int prev_progress_index,
    const MonotonicProgressConfig& config) {
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
    const std::vector<std::array<double, 3>>& old_path,
    const std::vector<std::array<double, 3>>& new_path,
    double tol_m) {
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
    const std::vector<std::array<double, 3>>& path,
    double x, double y,
    int progress_index,
    int start_offset,
    double goal_tolerance_m) {
  if (path.size() < 2 || !std::isfinite(x) || !std::isfinite(y) ||
      !std::isfinite(goal_tolerance_m) || goal_tolerance_m <= 0.0) {
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
    Eigen::MatrixXd& ref,
    double current_psi,
    double dt,
    double max_initial_step_rad,
    double align_turn_rate_rad_s,
    double align_min_speed_mps) {
  if (ref.rows() < 3 || ref.cols() < 1 || !std::isfinite(current_psi)) {
    return 0.0;
  }
  ref(2, 0) = current_psi + normalize_angle(ref(2, 0) - current_psi);
  for (int k = 1; k < ref.cols(); ++k) {
    ref(2, k) = ref(2, k - 1) + normalize_angle(ref(2, k) - ref(2, k - 1));
  }

  const double raw_e0 = ref(2, 0) - current_psi;
  if (dt <= 0.0 || max_initial_step_rad <= 0.0 || align_turn_rate_rad_s <= 0.0 ||
      std::abs(raw_e0) <= max_initial_step_rad) {
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
