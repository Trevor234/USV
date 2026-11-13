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
 * @file utils.hpp
 * @brief 坐标变换与数学工具。
 *
 * 运行时坐标系遵循 ROS 约定:平面位置/航向在局部 map 坐标系 (ENU 风格 x/y 平面),
 * 船体速度在 base_link。部分函数名保留 legacy `ned` 措辞以兼容,其语义为
 * 当前 ROS 图使用的 local-map/body-frame 旋转。
 */

#pragma once

#include <array>
#include <string>
#include <utility>
#include <vector>

#include <Eigen/Dense>

namespace usv_mpc
{

/// 将角度归一化到 [-pi, pi]。
double normalize_angle(double angle);

/// 从四元数 (x,y,z,w) 提取 ROS yaw (rad)。
/// 不做坐标系转换;返回与局部 map 帧 + base_link 约定一致的 yaw。
double quaternion_to_yaw(double qx, double qy, double qz, double qw);

/// 旋转 body-frame 速度到局部 map 帧 (legacy 名, 实为 local-map 旋转)。
std::pair<double, double> body_to_ned(double u, double v, double psi);

/// 旋转局部 map 帧速度到 body 帧 (legacy 名)。
std::pair<double, double> ned_to_body(double vn, double ve, double psi);

/// 从当前点 (x,y) 到线段 (x1,y1)-(x2,y2) 的有向横向跟踪误差。
double cross_track_error(
  double x, double y, double x1, double y1,
  double x2, double y2);

/// 从 profile 的 layout.dim 标签列表解析 stamp。
/// 返回 (sec, nanosec);ok=false 表示解析失败。
std::pair<int, int> parse_profile_stamp(
  const std::vector<std::string> & dim_labels, bool & ok);

/// path/profile 是否同步及原因字符串。
/// 返回 (synced, reason)。profile_len<0 表示无 profile。
std::pair<bool, std::string> profile_sync_state(
  int path_len, int profile_len,
  const std::pair<int, int> * path_stamp,
  const std::pair<int, int> * profile_stamp);

/// profile 同步原因码。
enum class SyncReason
{
  no_profile, path_too_short, length_mismatch,
  legacy_no_profile_stamp, missing_path_stamp, stamp_mismatch, stamp_match
};

/// 单个参考点 (path + profile 在某时刻的插值结果)。
struct RefSample
{
  double x, y, psi, v, r;
  int j;  // 下次搜索的段索引提示
};

/// 在时间 tk 处对 (path, profile) 插值,返回 (x, y, psi, v, r, j)。
/// times 单调递增;j_hint 为搜索起点。tk 超出末点时夹取到末点。
RefSample sample_path_profile_at_time(
  const std::vector<std::array<double, 3>> & path,    // [x, y, psi]
  const std::vector<double> & times,
  const std::vector<double> & vs,
  const std::vector<double> & rs,
  double tk, int j_hint);

}  // namespace usv_mpc
