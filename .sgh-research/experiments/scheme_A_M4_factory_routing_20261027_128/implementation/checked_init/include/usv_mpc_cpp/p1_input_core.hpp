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
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>
#include "usv_mpc_cpp/usv_model_dynamic.hpp"
#include "usv_mpc_cpp/utils.hpp"
namespace usv_mpc
{
struct InputEligibility
{
  bool odom_received = false, path_received = false, require_fcu = false, armed = false;
  size_t path_size = 0;
  double now_s = 0, last_odom_s = 0, odom_timeout_s = 0, last_state_s = 0, state_timeout_s = 0;
  std::string mode;
  std::vector<std::string> allowed_modes;
};
inline std::pair<bool, std::string> input_eligibility(const InputEligibility & c)
{
  if (!c.odom_received) {return std::make_pair(false, std::string("no_odom"));}
  if (c.odom_timeout_s > 0 && c.now_s - c.last_odom_s > c.odom_timeout_s) {
    return std::make_pair(false, std::string("odom_timeout"));
  }
  if (!c.path_received || c.path_size < 2) {return std::make_pair(false, std::string("no_path"));}
  if (c.require_fcu) {
    if (c.last_state_s == 0) {return std::make_pair(false, std::string("no_state"));}
    if (c.state_timeout_s > 0 && c.now_s - c.last_state_s > c.state_timeout_s) {
      return std::make_pair(false, std::string("state_timeout"));
    }
    if (!c.armed) {return std::make_pair(false, std::string("disarmed"));}
    if (!c.allowed_modes.empty() && std::find(c.allowed_modes.begin(), c.allowed_modes.end(),
        c.mode) == c.allowed_modes.end())
    {
      return std::make_pair(false, std::string("wrong_mode(" + c.mode + ")"));
    }
  }
  return std::make_pair(true, std::string(""));
}
inline bool admit_odom(const std::array<double, 5> & pxy_uvr, const std::array<double, 4> & q)
{
  for (double v : pxy_uvr) {
    if (!std::isfinite(v)) {
      return false;
    }
  }
  double n = 0; for(double v : q) {
    if(!std::isfinite(v)) {
      return false;
    }
    n += v * v;
  }
  return std::isfinite(n) && n >= 1e-12 && std::isfinite(quaternion_to_yaw(q[0], q[1], q[2], q[3]));
}
inline Vector6d compose_odom(const std::array<double, 5> & pxy_uvr, const std::array<double, 4> & q)
{
  Vector6d s;
  s << pxy_uvr[0], pxy_uvr[1], quaternion_to_yaw(q[0], q[1], q[2], q[3]), pxy_uvr[2], pxy_uvr[3],
    pxy_uvr[4];return s;
}
inline bool admit_imu(double r) {return std::isfinite(r);}
inline void compose_imu(Vector6d & s, double r) {s[5] = r;}
inline Eigen::Vector2d map_vrx(
  const Eigen::Vector2d & u, double scale, double tmin, double tmax,
  double cmdmax)
{
  const double lo = std::max(tmin, -cmdmax), hi = std::min(tmax, cmdmax);
  return {std::clamp(u[0] * scale, lo, hi), std::clamp(u[1] * scale, lo, hi)};
}
struct ReferenceMetadata
{
  uint32_t horizon_steps = 0; double prediction_dt = 0;
  uint64_t path_received_sequence = 0, profile_received_sequence = 0;
  int64_t path_stamp_ns = -1, profile_stamp_ns = -1;
  bool profile_stamp_known = false, profile_synced = false, profile_t0_known = false;
  size_t path_size = 0, profile_size = 0;
  int nearest_index = -1, start_index = -1, configured_start_offset = 2, effective_start_offset = 2;
  std::string reference_mode, profile_sync_reason;double profile_t0 = 0;
};
struct ReferenceInput
{
  std::vector<std::array<double, 3>> path;
  std::vector<std::array<double, 4>> profile;
  std::pair<int, int> path_stamp{-1, -1}, profile_stamp{-1, -1};
  uint64_t path_sequence = 0, profile_sequence = 0;
};
// Extracted on host from the verified F5 builder; legacy calls this same function.
Eigen::MatrixXd build_frozen_reference(
  const Vector6d &, const ReferenceInput &, int N, double dt,
  int offset, double cruise, ReferenceMetadata *);
struct HeldInputEvent {int64_t sim_ns = 0;int channel = 0;double value = 0;};
// Publisher-side nominal propagation. A mixed IMU rate is retained and tagged by caller.
// This is a point prediction, never a measured plant input or reachable-set bound.
inline bool propagate_publisher_nominal(
  Vector6d & s, int64_t from, int64_t target,
  Eigen::Vector2d held, const std::vector<HeldInputEvent> & history, const HydroParams & hydro)
{
  if(target < from || target - from > 1000000000LL || !s.allFinite() || !held.allFinite()) {
    return false;
  }
  int64_t cursor = from;
  auto advance = [&](int64_t end) {
      if(end <= cursor) {return;}
      USVDynamicModel m((end - cursor) / 1e9, 4, hydro);s = m.forward(s, held);cursor = end;
    };
  for(const auto & e : history) {
    if(e.channel < 0 || e.channel > 1 || !std::isfinite(e.value)) {return false;}
    if(e.sim_ns <= from) {held[e.channel] = e.value;continue;}
    if(e.sim_ns > target) {break;}
    advance(e.sim_ns);held[e.channel] = e.value;
  }
  advance(target);s[2] = normalize_angle(s[2]);return s.allFinite();
}
}  // namespace usv_mpc
