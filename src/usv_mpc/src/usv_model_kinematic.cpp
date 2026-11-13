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
 * @file usv_model_kinematic.cpp
 * @brief USV 运动学模型实现 (RK4 数值积分)。
 */

#include "usv_mpc/usv_model_kinematic.hpp"

#include <algorithm>
#include <cmath>

namespace usv_mpc
{

USVKinematicModel::USVKinematicModel(double dt, int rk4_substeps)
: dt_(dt), rk4_substeps_(std::max(1, rk4_substeps)) {}

Eigen::Vector3d USVKinematicModel::continuous_ode(
  const Eigen::Vector3d & state, const Eigen::Vector2d & control)
{
  const double psi = state(2);
  const double u = control(0);   // 纵荡速度
  const double r = control(1);   // 艏摇角速度
  Eigen::Vector3d rhs;
  rhs << u * std::cos(psi),
    u * std::sin(psi),
    r;
  return rhs;
}

Eigen::Vector3d USVKinematicModel::forward(
  const Eigen::Vector3d & state, const Eigen::Vector2d & control) const
{
  Eigen::Vector3d X = state;
  const double h = dt_ / static_cast<double>(rk4_substeps_);
  for (int i = 0; i < rk4_substeps_; ++i) {
    Eigen::Vector3d k1 = continuous_ode(X, control);
    Eigen::Vector3d k2 = continuous_ode(X + 0.5 * h * k1, control);
    Eigen::Vector3d k3 = continuous_ode(X + 0.5 * h * k2, control);
    Eigen::Vector3d k4 = continuous_ode(X + h * k3, control);
    X = X + h / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4);
  }
  // 航向归一化 (atan2(sin, cos))
  X(2) = std::atan2(std::sin(X(2)), std::cos(X(2)));
  return X;
}

USVKinematicModel::Vector5d USVKinematicModel::continuous_ode(
  const Vector5d & state, const Eigen::Vector2d & control,
  double tau_u, double tau_r)
{
  const double psi = state(2);
  const double u = state(3);
  const double r = state(4);
  const double uc = control(0);
  const double rc = control(1);
  Vector5d rhs;
  rhs << u * std::cos(psi),
    u * std::sin(psi),
    r,
    (uc - u) / tau_u,
    (rc - r) / tau_r;
  return rhs;
}

USVKinematicModel::Vector5d USVKinematicModel::forward_unwrapped(
  const Vector5d & state, const Eigen::Vector2d & control,
  double tau_u, double tau_r) const
{
  Vector5d X = state;
  const double h = dt_ / static_cast<double>(rk4_substeps_);
  for (int i = 0; i < rk4_substeps_; ++i) {
    Vector5d k1 = continuous_ode(X, control, tau_u, tau_r);
    Vector5d k2 = continuous_ode(X + 0.5 * h * k1, control, tau_u, tau_r);
    Vector5d k3 = continuous_ode(X + 0.5 * h * k2, control, tau_u, tau_r);
    Vector5d k4 = continuous_ode(X + h * k3, control, tau_u, tau_r);
    X = X + h / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4);
  }
  return X;
}

USVKinematicModel::Vector5d USVKinematicModel::forward(
  const Vector5d & state, const Eigen::Vector2d & control,
  double tau_u, double tau_r) const
{
  Vector5d X = forward_unwrapped(state, control, tau_u, tau_r);
  // 航向归一化
  X(2) = std::atan2(std::sin(X(2)), std::cos(X(2)));
  return X;
}

}  // namespace usv_mpc
