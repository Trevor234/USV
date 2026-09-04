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
 * @file usv_model_dynamic.hpp
 * @brief USV 三自由度 Fossen 动力学模型 (NMPC, C++ 版本)。
 *
 * 对应 Python 版本: usv_mpc/usv_model_dynamic.py
 *
 * 状态量:  [x, y, psi, u, v, r]  (ROS local map 位置 + base_link 速度, 共 6 维)
 * 控制量: [T_L, T_R]             (左右推进器推力, N)
 *
 * 动力学方程: M * dot_nu + C(nu)*nu + D(nu)*nu = tau
 *
 * 本模型用于 legacy CasADi fallback 后端的 RK4 数值积分,以及与 acados
 * codegen 求解器做数值对拍验证。acados 后端自身用 codegen 的 C 求解器,
 * 不调用本类。
 */

#pragma once

#include <array>

#include <Eigen/Dense>

namespace usv_mpc {

/// 6 维状态向量 (Eigen 无 Vector6d 内置 typedef)。
using Vector6d = Eigen::Matrix<double, 6, 1>;

/// 19 维水动力学参数 (p_global 的前 19 维)。
/// 对应 Python: PG_INDICES / hydro_dict_to_p_global。
struct HydroParams {
  double mass       = 14.2;
  double Iz         = 2.13;
  double xg         = 0.12;
  double d_thruster = 0.25;
  // 附加质量
  double Xu_dot = -2.0;
  double Yv_dot = -8.0;
  double Yr_dot = 0.0;
  double Nv_dot = -0.363545;
  double Nr_dot = -1.621220;
  // 线性阻尼
  double Xu = -2.272063;
  double Yv = -2.629019;
  double Yr = 0.0;     // zeroed (开环稳定)
  double Nv = 0.0;     // zeroed (开环稳定)
  double Nr = -4.286144;
  // 二次阻尼
  double Xuu = -11.571784;
  double Yvv = -0.05;
  double Yrr = 0.0;    // zeroed
  double Nvv = 0.0;    // zeroed
  double Nrr = -0.001;
};

/// USV 三自由度 Fossen 动力学模型 (双推进器)。
class USVDynamicModel {
 public:
  USVDynamicModel(double dt = 0.2, int rk4_substeps = 4,
                  const HydroParams& p = HydroParams{});

  /// 连续 Fossen ODE 右端 rhs = [eta_dot; nu_dot] (6 维)。
  /// 对应 Python: continuous_ode_expr (数值版, 非符号)。
  static usv_mpc::Vector6d continuous_ode(const usv_mpc::Vector6d& state,
                                        const Eigen::Vector2d& control,
                                        const HydroParams& p);

  /// 将 6 维状态向前推进 dt 时间步 (RK4)。
  /// 对应 Python: forward
  usv_mpc::Vector6d forward(const usv_mpc::Vector6d& state,
                          const Eigen::Vector2d& control) const;

  // ── 维度访问器 ──
  int n_states() const { return 6; }
  int n_controls() const { return 2; }
  double dt() const { return dt_; }

  const HydroParams& params() const { return params_; }

 private:
  double dt_;
  int rk4_substeps_;
  HydroParams params_;
};

}  // namespace usv_mpc
