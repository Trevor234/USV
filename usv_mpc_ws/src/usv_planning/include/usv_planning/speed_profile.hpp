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
 * @file speed_profile.hpp
 * @brief 速度/时间层：时间最优速度剖面 TOPP（纯 C++）。
 *
 * 对应 Python 版本: usv_planning/speed_profile.py
 */

#pragma once

#include <Eigen/Dense>

namespace usv_planning
{

/// compute_profile 的输出结果。
struct ProfileResult
{
  Eigen::VectorXd vs;   // 每点速度 (m/s)
  Eigen::VectorXd rs;   // 参考转艏角速度 = kappa*v (rad/s)
  Eigen::VectorXd ts;   // 每点时间戳 (s)
};

/**
 * @brief 计算时间最优速度剖面（确定性两遍扫描，O(N)，<1ms）。
 *
 * @param kappas     每点曲率 (1/m)
 * @param s          累积弧长 (m)
 * @param u_max      最大巡航速度 (m/s)
 * @param r_max      最大转艏角速度 (rad/s)
 * @param a_lat_max  最大侧向加速度 (m/s²)
 * @param a_acc      最大纵向加速度 (m/s²)
 * @param a_dec      最大纵向减速度 (m/s²)
 * @param v_start    起点速度 (m/s)
 * @param v_end      末端目标速度 (m/s)
 * @param v_min      最小速度下限，保证时间推进 (m/s)
 * @return ProfileResult
 */
ProfileResult compute_profile(
  const Eigen::VectorXd & kappas,
  const Eigen::VectorXd & s,
  double u_max,
  double r_max,
  double a_lat_max,
  double a_acc,
  double a_dec,
  double v_start,
  double v_end,
  double v_min = 0.2);

}  // namespace usv_planning
