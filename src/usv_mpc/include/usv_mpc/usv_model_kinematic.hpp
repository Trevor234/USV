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
 * @file usv_model_kinematic.hpp
 * @brief USV 三自由度运动学模型 (方案 A)。
 *
 * 状态量:  [x, y, psi]   (ROS local map 位置 + 航向, 共 3 维)
 * 控制量: [u_surge, r_yaw] (纵向速度 + 艏摇角速度)
 *
 * 动力学方程 (纯运动学, 无水动力参数):
 *   dx/dt   = u * cos(psi)
 *   dy/dt   = u * sin(psi)
 *   dpsi/dt = r
 *
 * 本模型用于 CasADi fallback 后端的 RK4 数值积分,以及 gtest sanity 验证。
 * 与方案 B 的 USVDynamicModel 对齐接口风格,但无 HydroParams (运动学是纯函数)。
 */

#pragma once

#include <Eigen/Dense>

namespace usv_mpc
{

/// USV 三自由度运动学模型 (双推进器, 运动学抽象)。
class USVKinematicModel {
public:
  /// 构造。dt: 离散步长; rk4_substeps: RK4 子步数 (默认 4)。
  USVKinematicModel(double dt = 0.2, int rk4_substeps = 4);

  using Vector5d = Eigen::Matrix<double, 5, 1>;

  /// 连续运动学 ODE 右端 rhs = [u*cos(psi), u*sin(psi), r] (3 维)。
  /// 纯函数 (无物理参数), 可被 backend 的符号构建与 gtest 共用数值版本。
  static Eigen::Vector3d continuous_ode(
    const Eigen::Vector3d & state,
    const Eigen::Vector2d & control);

  /// 将 3 维状态向前推进 dt 时间步 (RK4, rk4_substeps 子步)。
  /// 航向归一化到 [-pi, pi] (atan2(sin, cos))。
  Eigen::Vector3d forward(
    const Eigen::Vector3d & state,
    const Eigen::Vector2d & control) const;

  /// 5 状态连续运动学 ODE 右端 (含一阶速度滞后):
  ///   state = [x, y, psi, u, r], control = [u_cmd, r_cmd]
  ///   dx = u*cos(psi); dy = u*sin(psi); dpsi = r
  ///   du = (u_cmd - u)/tau_u; dr = (r_cmd - r)/tau_r
  static Vector5d continuous_ode(
    const Vector5d & state,
    const Eigen::Vector2d & control,
    double tau_u, double tau_r);

  /// 5 状态向前推进 dt (RK4, rk4_substeps 子步), 航向归一化到 [-pi, pi]。
  Vector5d forward(
    const Vector5d & state,
    const Eigen::Vector2d & control,
    double tau_u, double tau_r) const;

  /// 同上, 但不归一化 psi (保持连续展开)。
  /// acados 生成模型内部不做 atan2, 用它核查动力学残差才不会把跨 ±pi 的
  /// 连续轨迹误判成 2*pi 误差。其余 4 维与 forward() 完全相同。
  Vector5d forward_unwrapped(
    const Vector5d & state,
    const Eigen::Vector2d & control,
    double tau_u, double tau_r) const;

  // ── 维度访问器 (对齐 B 的 USVDynamicModel 接口风格) ──
  int n_states() const {return 3;}
  int n_controls() const {return 2;}
  double dt() const {return dt_;}

private:
  double dt_;
  int rk4_substeps_;
};

}  // namespace usv_mpc
