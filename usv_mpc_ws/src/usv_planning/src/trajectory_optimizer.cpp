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
 * @file trajectory_optimizer.cpp
 * @brief G1 圆弧倒角（fillet）平滑实现（纯 C++，Eigen）。
 *
 * 对应 Python 版本: usv_planning/trajectory_optimizer.py
 *
 * 把折线航点序列平滑成"直线段 + 最小转弯半径圆弧"的可行路径，
 * 并解析地给出每点的航向 psi、曲率 kappa 与累积弧长 s。
 */

#include "usv_planning/trajectory_optimizer.hpp"

#include <cmath>
#include <sstream>
#include <iomanip>

namespace usv_planning
{

// ── 内部辅助函数 ─────────────────────────────────────────

/// 返回 (ux, uy, length)；零向量返回 (0,0,0)。
static std::tuple<double, double, double> unit_vec(double dx, double dy)
{
  double length = std::hypot(dx, dy);
  if (length < 1e-9) {return {0.0, 0.0, 0.0};}
  return {dx / length, dy / length, length};
}

/// 从入方向到出方向的有符号转角（左正右负），范围 [-pi, pi]。
static double signed_turn(
  double uin_x, double uin_y,
  double uout_x, double uout_y)
{
  double cross = uin_x * uout_y - uin_y * uout_x;
  double dot = uin_x * uout_x + uin_y * uout_y;
  return std::atan2(cross, dot);
}

/// 对直线段按 res 采样（不含起点，避免与上一段重复）。
static void sample_straight(
  double x0, double y0, double x1, double y1,
  double psi, double res,
  std::vector<double> & xs, std::vector<double> & ys,
  std::vector<double> & psis, std::vector<double> & kappas)
{
  double seg_len = std::hypot(x1 - x0, y1 - y0);
  if (seg_len < 1e-6) {return;}
  int n_steps = std::max(1, static_cast<int>(std::round(seg_len / res)));
  for (int k = 1; k <= n_steps; ++k) {
    double t = static_cast<double>(k) / n_steps;
    xs.push_back(x0 + t * (x1 - x0));
    ys.push_back(y0 + t * (y1 - y0));
    psis.push_back(psi);
    kappas.push_back(0.0);
  }
}

/// 对常曲率圆弧精确积分采样（不含起点）。返回 (x_end, y_end, psi_end)。
static std::tuple<double, double, double> sample_arc(
  double x0, double y0, double psi0,
  double kappa, double arc_len, double res,
  std::vector<double> & xs, std::vector<double> & ys,
  std::vector<double> & psis, std::vector<double> & kappas_out)
{
  int n_steps = std::max(1, static_cast<int>(std::round(arc_len / res)));
  double ds = arc_len / n_steps;
  double x = x0, y = y0, psi = psi0;
  for (int i = 0; i < n_steps; ++i) {
    double psi_next = psi + kappa * ds;
    if (std::abs(kappa) > 1e-9) {
      x += (std::sin(psi_next) - std::sin(psi)) / kappa;
      y += (std::cos(psi) - std::cos(psi_next)) / kappa;
    } else {
      x += ds * std::cos(psi);
      y += ds * std::sin(psi);
    }
    psi = psi_next;
    xs.push_back(x);
    ys.push_back(y);
    psis.push_back(psi);
    kappas_out.push_back(kappa);
  }
  return {x, y, psi};
}

// ── 公开 API ─────────────────────────────────────────────

Eigen::VectorXd arc_length(
  const Eigen::VectorXd & xs,
  const Eigen::VectorXd & ys)
{
  const int n = static_cast<int>(xs.size());
  Eigen::VectorXd s = Eigen::VectorXd::Zero(n);
  for (int i = 1; i < n; ++i) {
    s(i) = s(i - 1) + std::hypot(xs(i) - xs(i - 1), ys(i) - ys(i - 1));
  }
  return s;
}

FilletResult fillet_path(
  const std::vector<std::pair<double, double>> & waypoints,
  double turn_radius,
  double resolution)
{
  FilletResult result;
  const int n = static_cast<int>(waypoints.size());
  if (n < 2) {return result;}

  // 有限性门禁: NaN/Inf 航点会让 round(seg_len/res) 变成 UB、后续几何全部
  // 污染。返回空结果, 由调用方按"路径过短"发布空路径。
  for (const auto & wp : waypoints) {
    if (!std::isfinite(wp.first) || !std::isfinite(wp.second)) {
      return result;
    }
  }

  double res = std::max(1e-3, resolution);
  double R = std::max(1e-3, turn_radius);

  std::vector<double> xs_v, ys_v, psis_v, kappas_v;

  // 连续累积航向：以第一段方向为起点
  auto [ux0, uy0, len0] = unit_vec(
      waypoints[1].first - waypoints[0].first,
      waypoints[1].second - waypoints[0].second);
  (void)len0;
  double psi_cont = std::atan2(uy0, ux0);

  // 游标位置
  double cx = waypoints[0].first;
  double cy = waypoints[0].second;
  xs_v.push_back(cx);
  ys_v.push_back(cy);
  psis_v.push_back(psi_cont);
  kappas_v.push_back(0.0);

  for (int i = 1; i < n - 1; ++i) {
    auto [ax, ay] = waypoints[i - 1];
    auto [bx, by] = waypoints[i];
    auto [ccx, ccy] = waypoints[i + 1];

    auto [uin_x, uin_y, len_in_raw] = unit_vec(bx - ax, by - ay);
    auto [uout_x, uout_y, len_out] = unit_vec(ccx - bx, ccy - by);
    (void)len_in_raw;

    if (uin_x == 0.0 && uin_y == 0.0) {continue;}
    if (uout_x == 0.0 && uout_y == 0.0) {continue;}

    double delta = signed_turn(uin_x, uin_y, uout_x, uout_y);
    if (std::abs(delta) < 1e-4) {continue;}

    // 切线缩进
    double len_in = std::hypot(bx - cx, by - cy);
    double tan_half = std::tan(std::abs(delta) / 2.0);
    double t_desired = R * tan_half;
    // len_in 是从游标(上一圆弧出口切点)到当前角点的剩余直段, 上一圆弧已
    // 占用其份额, 不应再折半; len_out 折半为下一圆弧预留。
    // (此前 0.5*min(len_in,len_out) 在密集航点下把半径压到 1e-6 以下被跳过,
    //  留下 G0 尖角 → TOPP 近零速 → 加减速震荡; 2026-09-08 review 定位)
    double t_max_geom = std::min(len_in, 0.5 * len_out);
    double T = std::min(t_desired, t_max_geom);
    if (T < 1e-6) {continue;}

    double r_eff = T / tan_half;
    if (r_eff < R - 1e-3) {
      std::ostringstream oss;
      oss << "航点#" << i << " 处航段过短，转弯半径被裁剪 R_eff="
          << std::fixed << std::setprecision(2) << r_eff
          << "m < turn_radius=" << R << "m";
      result.warnings.push_back(oss.str());
    }

    // 入切点
    double tp_in_x = bx - uin_x * T;
    double tp_in_y = by - uin_y * T;

    // 1) 直线段：游标 -> 入切点
    sample_straight(cx, cy, tp_in_x, tp_in_y, psi_cont, res,
                    xs_v, ys_v, psis_v, kappas_v);
    cx = tp_in_x;
    cy = tp_in_y;

    // 2) 圆弧段
    double kappa = std::copysign(1.0 / r_eff, delta);
    double arc_len = r_eff * std::abs(delta);
    auto [cx_new, cy_new, psi_new] = sample_arc(
        cx, cy, psi_cont, kappa, arc_len, res,
        xs_v, ys_v, psis_v, kappas_v);
    cx = cx_new;
    cy = cy_new;
    psi_cont = psi_new;
  }

  // 3) 末段直线：游标 -> 终点航点
  sample_straight(cx, cy,
                  waypoints[n - 1].first, waypoints[n - 1].second,
                  psi_cont, res, xs_v, ys_v, psis_v, kappas_v);

  // 转换为 Eigen 向量
  const int m = static_cast<int>(xs_v.size());
  result.xs = Eigen::Map<Eigen::VectorXd>(xs_v.data(), m);
  result.ys = Eigen::Map<Eigen::VectorXd>(ys_v.data(), m);
  result.psis = Eigen::Map<Eigen::VectorXd>(psis_v.data(), m);
  result.kappas = Eigen::Map<Eigen::VectorXd>(kappas_v.data(), m);
  result.s = arc_length(result.xs, result.ys);
  return result;
}

GeometryResult recompute_geometry(
  const Eigen::VectorXd & xs,
  const Eigen::VectorXd & ys)
{
  GeometryResult res;
  const int n = static_cast<int>(xs.size());
  res.s = arc_length(xs, ys);

  if (n < 2) {
    res.psis = Eigen::VectorXd::Zero(n);
    res.kappas = Eigen::VectorXd::Zero(n);
    return res;
  }

  // numpy.gradient 的 C++ 等价：中心差分，端点用单侧差分
  Eigen::VectorXd dx(n), dy(n);
  // 端点：单侧差分
  dx(0) = xs(1) - xs(0);
  dy(0) = ys(1) - ys(0);
  dx(n - 1) = xs(n - 1) - xs(n - 2);
  dy(n - 1) = ys(n - 1) - ys(n - 2);
  // 内部：中心差分
  for (int i = 1; i < n - 1; ++i) {
    dx(i) = 0.5 * (xs(i + 1) - xs(i - 1));
    dy(i) = 0.5 * (ys(i + 1) - ys(i - 1));
  }

  // psi = atan2(dy, dx)，然后 unwrap 保持连续
  Eigen::VectorXd psi(n);
  for (int i = 0; i < n; ++i) {
    psi(i) = std::atan2(dy(i), dx(i));
  }
  // unwrap：使相邻差值在 [-pi, pi] 范围内
  for (int i = 1; i < n; ++i) {
    double diff = psi(i) - psi(i - 1);
    while (diff > M_PI) {diff -= 2.0 * M_PI;}
    while (diff < -M_PI) {diff += 2.0 * M_PI;}
    psi(i) = psi(i - 1) + diff;
  }

  // 二阶差分 ddx, ddy
  Eigen::VectorXd ddx(n), ddy(n);
  ddx(0) = dx(1) - dx(0);
  ddy(0) = dy(1) - dy(0);
  ddx(n - 1) = dx(n - 1) - dx(n - 2);
  ddy(n - 1) = dy(n - 1) - dy(n - 2);
  for (int i = 1; i < n - 1; ++i) {
    ddx(i) = 0.5 * (dx(i + 1) - dx(i - 1));
    ddy(i) = 0.5 * (dy(i + 1) - dy(i - 1));
  }

  // kappa = (dx*ddy - dy*ddx) / (dx^2 + dy^2 + eps)^1.5
  Eigen::VectorXd kappa(n);
  for (int i = 0; i < n; ++i) {
    double denom = std::pow(dx(i) * dx(i) + dy(i) * dy(i) + 1e-8, 1.5);
    kappa(i) = (dx(i) * ddy(i) - dy(i) * ddx(i)) / denom;
  }

  res.psis = std::move(psi);
  res.kappas = std::move(kappa);
  return res;
}

}  // namespace usv_planning
