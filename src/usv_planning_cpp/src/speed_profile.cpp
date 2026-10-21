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
 * @file speed_profile.cpp
 * @brief 时间最优速度剖面 TOPP 实现（纯 C++，Eigen）。
 *
 * 对应 Python 版本: usv_planning/speed_profile.py
 *
 * 确定性两遍扫描，O(N)，<1ms，无实时性风险。
 */

#include "usv_planning_cpp/speed_profile.hpp"

#include <algorithm>
#include <cmath>

namespace usv_planning {

static constexpr double EPS = 1e-6;

ProfileResult compute_profile(
    const Eigen::VectorXd& kappas,
    const Eigen::VectorXd& s,
    double u_max,
    double r_max,
    double a_lat_max,
    double a_acc,
    double a_dec,
    double v_start,
    double v_end,
    double v_min) {
  const int n = static_cast<int>(s.size());
  ProfileResult result;

  if (n == 0) {
    return result;
  }
  if (n == 1) {
    result.vs = Eigen::VectorXd::Constant(1, std::max(v_min, 0.0));
    result.rs = Eigen::VectorXd::Zero(1);
    result.ts = Eigen::VectorXd::Zero(1);
    return result;
  }

  // 参数下限保护
  u_max     = std::max(EPS, u_max);
  a_lat_max = std::max(EPS, a_lat_max);
  a_acc     = std::max(EPS, a_acc);
  a_dec     = std::max(EPS, a_dec);

  Eigen::VectorXd kappa_abs = kappas.array().abs();

  // ── 曲率限速包络 ──
  Eigen::VectorXd v_curve = Eigen::VectorXd::Constant(n, u_max);
  for (int i = 0; i < n; ++i) {
    if (kappa_abs(i) > EPS) {
      double v_turn = r_max / kappa_abs(i);
      double v_lat  = std::sqrt(a_lat_max / kappa_abs(i));
      v_curve(i) = std::min({v_curve(i), v_turn, v_lat});
    }
  }
  v_curve = v_curve.cwiseMax(0.0);

  Eigen::VectorXd v = v_curve;

  // 起点速度（受当前速度与曲率限速共同约束）
  v(0) = std::min(v_curve(0), std::max(v_start, 0.0));

  // ── 前向扫描：受加速度上限 a_acc 约束 ──
  for (int i = 1; i < n; ++i) {
    double ds = std::max(EPS, s(i) - s(i - 1));
    v(i) = std::min(v_curve(i),
                    std::sqrt(v(i - 1) * v(i - 1) + 2.0 * a_acc * ds));
  }

  // 末端速度
  v(n - 1) = std::min(v(n - 1), std::max(v_end, 0.0));

  // ── 后向扫描：受减速度上限 a_dec 约束 ──
  for (int i = n - 2; i >= 0; --i) {
    double ds = std::max(EPS, s(i + 1) - s(i));
    v(i) = std::min(v(i),
                    std::sqrt(v(i + 1) * v(i + 1) + 2.0 * a_dec * ds));
  }

  // ── 时间积分（梯形） ──
  Eigen::VectorXd ts = Eigen::VectorXd::Zero(n);
  for (int i = 1; i < n; ++i) {
    double ds    = s(i) - s(i - 1);
    double v_avg = std::max(0.5 * (v(i - 1) + v(i)), v_min);
    ts(i) = ts(i - 1) + ds / v_avg;
  }

  // rs = kappas * v
  Eigen::VectorXd rs = kappas.array() * v.array();

  result.vs = std::move(v);
  result.rs = std::move(rs);
  result.ts = std::move(ts);
  return result;
}

}  // namespace usv_planning
