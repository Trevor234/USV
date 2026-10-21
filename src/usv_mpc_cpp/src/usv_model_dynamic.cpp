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
 * @file usv_model_dynamic.cpp
 * @brief USV Fossen 动力学模型实现 (C++ 版本)。
 *
 * 对应 Python 版本: usv_mpc/usv_model_dynamic.py
 */

#include "usv_mpc_cpp/usv_model_dynamic.hpp"

#include <cmath>

namespace usv_mpc {

USVDynamicModel::USVDynamicModel(double dt, int rk4_substeps,
                                 const HydroParams& p)
    : dt_(dt), rk4_substeps_(rk4_substeps), params_(p) {}

Vector6d USVDynamicModel::continuous_ode(const Vector6d& state,
                                         const Eigen::Vector2d& control,
                                         const HydroParams& p) {
  double psi_s = state(2);
  double u_s = state(3), v_s = state(4), r_s = state(5);
  double TL = control(0), TR = control(1);

  // 惯性矩阵 M (含附加质量)
  double m11 = p.mass - p.Xu_dot;
  double m22 = p.mass - p.Yv_dot;
  double m23 = p.mass * p.xg - p.Yr_dot;
  double m32 = p.mass * p.xg - p.Nv_dot;
  double m33 = p.Iz - p.Nr_dot;

  Eigen::Matrix3d M;
  M << m11, 0.0, 0.0,
       0.0, m22, m23,
       0.0, m32, m33;

  // 科里奥利矩阵 C(nu)
  double c13 = -m22 * v_s - m23 * r_s;
  double c23 = m11 * u_s;
  Eigen::Matrix3d C;
  C.setZero();
  C(0, 2) = c13;
  C(1, 2) = c23;
  C(2, 0) = -c13;
  C(2, 1) = -c23;

  // 阻尼矩阵 D(nu) — 线性 + 二次
  Eigen::Matrix3d D;
  D.setZero();
  D(0, 0) = -p.Xu - p.Xuu * std::fabs(u_s);
  D(1, 1) = -p.Yv - p.Yvv * std::fabs(v_s);
  D(1, 2) = -p.Yr - p.Yrr * std::fabs(r_s);
  D(2, 1) = -p.Nv - p.Nvv * std::fabs(v_s);
  D(2, 2) = -p.Nr - p.Nrr * std::fabs(r_s);

  // 推力映射: tau = [TL+TR, 0, d*(TR-TL)]
  Eigen::Vector3d tau(TL + TR, 0.0, p.d_thruster * (TR - TL));

  // 运动学: dot_eta = J(psi) * nu
  Eigen::Vector3d nu(u_s, v_s, r_s);
  double cos_psi = std::cos(psi_s);
  double sin_psi = std::sin(psi_s);
  Eigen::Matrix3d J;
  J << cos_psi, -sin_psi, 0.0,
       sin_psi,  cos_psi, 0.0,
       0.0,      0.0,     1.0;
  Eigen::Vector3d eta_dot = J * nu;

  // 动力学: dot_nu = M^{-1} * (tau - C*nu - D*nu)
  Eigen::Vector3d rhs_nu = M.inverse() * (tau - C * nu - D * nu);

  Vector6d rhs;
  rhs << eta_dot, rhs_nu;
  return rhs;
}

Vector6d USVDynamicModel::forward(const Vector6d& state,
                                  const Eigen::Vector2d& control) const {
  // RK4 离散化 (rk4_substeps 子步)
  Vector6d X = state;
  double h = dt_ / static_cast<double>(rk4_substeps_);
  for (int i = 0; i < rk4_substeps_; ++i) {
    Vector6d k1 = continuous_ode(X, control, params_);
    Vector6d k2 = continuous_ode(X + 0.5 * h * k1, control, params_);
    Vector6d k3 = continuous_ode(X + 0.5 * h * k2, control, params_);
    Vector6d k4 = continuous_ode(X + h * k3, control, params_);
    X = X + h / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4);
  }
  // 航向归一化 (与 Python forward 一致)
  X(2) = std::atan2(std::sin(X(2)), std::cos(X(2)));
  return X;
}

}  // namespace usv_mpc
