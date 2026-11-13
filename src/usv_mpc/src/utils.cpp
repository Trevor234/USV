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

}  // namespace usv_mpc
