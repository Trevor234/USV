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
 * @file trajectory_optimizer.hpp
 * @brief 轨迹几何层：G1 圆弧倒角（fillet）平滑（纯 C++）。
 *
 * 对应 Python 版本: usv_planning/trajectory_optimizer.py
 */

#pragma once

#include <string>
#include <utility>
#include <vector>

#include <Eigen/Dense>

namespace usv_planning
{

/// fillet_path 的输出结果。
struct FilletResult
{
  Eigen::VectorXd xs;       // 位置 x
  Eigen::VectorXd ys;       // 位置 y
  Eigen::VectorXd psis;     // 连续累积航向 (rad)
  Eigen::VectorXd kappas;   // 有符号曲率 (1/m)
  Eigen::VectorXd s;        // 累积弧长 (m)
  std::vector<std::string> warnings;
};

/// recompute_geometry 的输出结果。
struct GeometryResult
{
  Eigen::VectorXd psis;
  Eigen::VectorXd kappas;
  Eigen::VectorXd s;
};

/**
 * @brief 对折线航点做圆弧倒角，返回稠密采样的可行路径。
 *
 * @param waypoints  [(x, y), ...] 顺序航点
 * @param turn_radius  期望最小转弯半径 R (m)
 * @param resolution   采样间距 (m)
 * @return FilletResult
 */
FilletResult fillet_path(
  const std::vector<std::pair<double, double>> & waypoints,
  double turn_radius,
  double resolution);

/**
 * @brief 从离散点数值重算 (psi_continuous, kappa, s)。
 *
 * 供最小曲率精修改动点位后重新导出航向/曲率使用。
 */
GeometryResult recompute_geometry(
  const Eigen::VectorXd & xs,
  const Eigen::VectorXd & ys);

/**
 * @brief 累积弧长计算。
 */
Eigen::VectorXd arc_length(
  const Eigen::VectorXd & xs,
  const Eigen::VectorXd & ys);

}  // namespace usv_planning
