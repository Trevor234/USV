// Private host-only oracle generated from the verified F5 backup.
// It is independent of the new core implementation and stays on this host.
#pragma once
#include "usv_mpc_cpp/p1_input_core.hpp"
namespace usv_mpc {
struct F5SolverShape {
  int n; double step;
  int N() const {return n;}
  double dt() const {return step;}
};
class F5ReferenceOracle {
public:
  F5ReferenceOracle(const ReferenceInput & in, int n, double dt, int offset, double cruise)
  : solver_{n, dt}, mpc_(&solver_), reference_path_(in.path),
    reference_path_stamp_(in.path_stamp), ref_profile_(in.profile),
    ref_profile_stamp_(in.profile_stamp), path_received_sequence_(in.path_sequence),
    profile_received_sequence_(in.profile_sequence), reference_start_offset_(offset),
    cruise_speed_(cruise) {}
  Eigen::MatrixXd build_reference(const Vector6d &, ReferenceMetadata *);
  bool cached_synced() const {return profile_synced_;}
  const std::string & cached_reason() const {return profile_sync_reason_;}
private:
  F5SolverShape solver_; F5SolverShape * mpc_;
  std::vector<std::array<double, 3>> reference_path_;
  std::pair<int, int> reference_path_stamp_;
  std::vector<std::array<double, 4>> ref_profile_;
  std::pair<int, int> ref_profile_stamp_;
  uint64_t path_received_sequence_, profile_received_sequence_;
  int reference_start_offset_; double cruise_speed_;
  bool profile_synced_ = false;
  std::string profile_sync_reason_ = "no_profile";
};
class F5EligibilityOracle {
public:
  explicit F5EligibilityOracle(const InputEligibility & c)
  : odom_received_(c.odom_received), path_received_(c.path_received),
    reference_path_(c.path_size), require_fcu_state_(c.require_fcu), armed_(c.armed),
    now_s_(c.now_s), last_odom_time_(c.last_odom_s), odom_timeout_s_(c.odom_timeout_s),
    last_state_time_(c.last_state_s), state_timeout_s_(c.state_timeout_s),
    mode_(c.mode), allowed_fcu_modes_(c.allowed_modes) {}
  std::pair<bool, std::string> can_solve() const;
private:
  bool odom_received_, path_received_;
  std::vector<int> reference_path_;
  bool require_fcu_state_, armed_;
  double now_s_, last_odom_time_, odom_timeout_s_, last_state_time_, state_timeout_s_;
  std::string mode_; std::vector<std::string> allowed_fcu_modes_;
};
struct F5Point {double x, y;};
struct F5Quat {double x, y, z, w;};
struct F5Linear {double x, y;};
struct F5Angular {double z;};
struct F5Twist {F5Linear linear; F5Angular angular;};
struct F5Scalar {double data;};
Eigen::MatrixXd F5ReferenceOracle::build_reference(
  const Vector6d & current_state,
  ReferenceMetadata * evidence)
{
  const int N = mpc_->N();
  double dt = mpc_->dt();
  Eigen::MatrixXd ref = Eigen::MatrixXd::Zero(6, N + 1);
  const auto & path = reference_path_;
  if (evidence) {
    evidence->horizon_steps = static_cast<uint32_t>(N);
    evidence->prediction_dt = dt;
    evidence->path_received_sequence = path_received_sequence_;
    evidence->profile_received_sequence = profile_received_sequence_;
    evidence->path_stamp_ns = reference_path_stamp_.first < 0 ? -1 :
      int64_t(reference_path_stamp_.first) * 1000000000LL + reference_path_stamp_.second;
    evidence->profile_stamp_known = ref_profile_stamp_.first >= 0;
    evidence->profile_stamp_ns = !evidence->profile_stamp_known ? -1 :
      int64_t(ref_profile_stamp_.first) * 1000000000LL + ref_profile_stamp_.second;
    evidence->path_size = path.size();
    evidence->profile_size = ref_profile_.size();
    evidence->nearest_index = -1;
    evidence->start_index = -1;
    evidence->configured_start_offset = reference_start_offset_;
    evidence->effective_start_offset = std::max(1, reference_start_offset_);
    evidence->reference_mode = "empty_path";
    evidence->profile_sync_reason = "empty_path";
  }

  if (path.empty()) {return ref;}

  // 最近点 + start_offset
  double best_d = 1e18; int nearest = 0;
  for (size_t i = 0; i < path.size(); ++i) {
    double d = std::hypot(path[i][0] - current_state(0), path[i][1] - current_state(1));
    if (d < best_d) {best_d = d; nearest = static_cast<int>(i);}
  }
  int idx = std::min(nearest + std::max(1, reference_start_offset_),
                     static_cast<int>(path.size()) - 1);
  if (evidence) {evidence->nearest_index = nearest; evidence->start_index = idx;}

  // profile 同步判定
  int profile_len = ref_profile_.empty() ? -1 : static_cast<int>(ref_profile_.size());
  const std::pair<int,
    int> * p_stamp = (ref_profile_stamp_.first >= 0) ? &ref_profile_stamp_ : nullptr;
  const std::pair<int,
    int> * path_stamp = (reference_path_stamp_.first >= 0) ? &reference_path_stamp_ : nullptr;
  auto [synced, sync_reason] = profile_sync_state(
      static_cast<int>(path.size()), profile_len, path_stamp, p_stamp);

  if (evidence) {
    evidence->profile_synced = synced; evidence->profile_sync_reason = sync_reason;
    evidence->reference_mode = synced ? "profile_time" : "cruise_arc_fallback";
  }
  if (synced) {
    std::vector<double> times(ref_profile_.size()), vs(ref_profile_.size()),
    rs(ref_profile_.size());
    for (size_t i = 0; i < ref_profile_.size(); ++i) {
      times[i] = ref_profile_[i][3]; vs[i] = ref_profile_[i][0]; rs[i] = ref_profile_[i][2];
    }
    double t0 = times[idx];
    if (evidence) {evidence->profile_t0_known = true; evidence->profile_t0 = t0;}
    int j = idx;
    for (int k = 0; k <= N; ++k) {
      double tk = t0 + k * dt;
      RefSample s = sample_path_profile_at_time(path, times, vs, rs, tk, j);
      ref(0, k) = s.x; ref(1, k) = s.y; ref(2, k) = s.psi;
      ref(3, k) = s.v; ref(4, k) = 0.0; ref(5, k) = s.r;
      j = s.j;
    }
    profile_synced_ = true;
    profile_sync_reason_ = sync_reason;
  } else {
    // 回退: 匀速弧长采样
    profile_synced_ = false;
    profile_sync_reason_ = sync_reason;
    std::vector<double> arc;
    arc.push_back(0.0);
    for (int i = idx; i < static_cast<int>(path.size()) - 1; ++i) {
      arc.push_back(arc.back() + std::hypot(path[i + 1][0] - path[i][0],
          path[i + 1][1] - path[i][1]));
    }
    for (int k = 0; k <= N; ++k) {
      double s_des = cruise_speed_ * dt * k;
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
      ref(3, k) = cruise_speed_; ref(4, k) = 0.0; ref(5, k) = 0.0;
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
std::pair<bool, std::string> F5EligibilityOracle::can_solve() const
{
  double now = now_s_;
  if (!odom_received_) {return {false, "no_odom"};}
  if (odom_timeout_s_ > 0.0 && (now - last_odom_time_) > odom_timeout_s_) {
    return {false, "odom_timeout"};
  }
  if (!path_received_ || reference_path_.size() < 2) {return {false, "no_path"};}
  if (require_fcu_state_) {
    if (last_state_time_ == 0.0) {return {false, "no_state"};}
    if (state_timeout_s_ > 0.0 && (now - last_state_time_) > state_timeout_s_) {
      return {false, "state_timeout"};
    }
    if (!armed_) {return {false, "disarmed"};}
    if (!allowed_fcu_modes_.empty()) {
      bool allowed = false;
      for (const auto & m : allowed_fcu_modes_) {
        if (m == mode_) {
          allowed = true; break;
        }
      }
      if (!allowed) {return {false, "wrong_mode(" + mode_ + ")"};}
    }
  }
  return {true, ""};
}
// Diagnostics are discarded by the macro; the original numeric
// conditions and their original order are retained verbatim below.
#define RCLCPP_WARN_THROTTLE(...) do {} while (false)
inline bool f5_admit_odom(const std::array<double, 5> & a,
  const std::array<double, 4> & orientation) {
  F5Point p{a[0], a[1]};
  F5Quat q{orientation[0], orientation[1], orientation[2], orientation[3]};
  F5Twist t{{a[2], a[3]}, {a[4]}};
if (!std::isfinite(p.x) || !std::isfinite(p.y) ||
    !std::isfinite(q.x) || !std::isfinite(q.y) ||
    !std::isfinite(q.z) || !std::isfinite(q.w) ||
    !std::isfinite(t.linear.x) || !std::isfinite(t.linear.y) ||
    !std::isfinite(t.angular.z))
  {
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "odom 含 NaN/Inf, 丢弃该样本");
    return false;
  }
  // Keep raw research records above, but never admit degenerate orientations.
  const double quaternion_norm2 = q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w;
  if (!std::isfinite(quaternion_norm2) || quaternion_norm2 < 1e-12) {
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                        "odom quaternion norm is invalid; dropping sample");
    return false;
  }
  double psi = quaternion_to_yaw(q.x, q.y, q.z, q.w);
  if (!std::isfinite(psi)) {  // Final guard for the yaw calculation
    RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                         "odom 四元数退化, 丢弃该样本");
    return false;
  }
    return true;
}
#undef RCLCPP_WARN_THROTTLE
inline Vector6d f5_compose_odom(const std::array<double, 5> & a,
  const std::array<double, 4> & orientation) {
  F5Point p{a[0], a[1]};
  F5Quat q{orientation[0], orientation[1], orientation[2], orientation[3]};
  F5Twist t{{a[2], a[3]}, {a[4]}};
  double psi = quaternion_to_yaw(q.x, q.y, q.z, q.w);
  double x_, y_, psi_, u_, v_, r_;
x_ = p.x;
  y_ = p.y;
  psi_ = psi;
  u_ = t.linear.x;
  v_ = t.linear.y;
  r_ = t.angular.z;
  Vector6d s; s << x_, y_, psi_, u_, v_, r_; return s;
}
inline Eigen::Vector2d f5_map_vrx(const Eigen::Vector2d & thrust,
  double vrx_thrust_scale_, double dyn_T_min_, double dyn_T_max_,
  double vrx_thrust_cmd_max_) {

  F5Scalar left, right;
  const double lower = std::max(dyn_T_min_, -vrx_thrust_cmd_max_);
  const double upper = std::min(dyn_T_max_, vrx_thrust_cmd_max_);
  left.data = std::clamp(thrust(0) * vrx_thrust_scale_, lower, upper);
  right.data = std::clamp(thrust(1) * vrx_thrust_scale_, lower, upper);
    return Eigen::Vector2d(left.data, right.data);
}
}  // namespace usv_mpc
