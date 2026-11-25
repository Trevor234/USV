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
 * @file kinematic_solution_audit.cpp
 * @brief 运动学候选解可行性核查实现。
 */

#include "usv_mpc/kinematic_solution_audit.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>

#include "usv_mpc/usv_model_kinematic.hpp"

namespace usv_mpc
{

bool audit_kinematic_solution(
  const KinematicMpcParams & params,
  const Vector5d & measured,
  const Eigen::Vector2d & anchor,
  const Eigen::MatrixXd & X,
  const Eigen::MatrixXd & U,
  SolveInfo & diagnostics)
{
  constexpr int NX = 5;
  constexpr int NU = 2;
  const int N = params.N;

  if (X.rows() != NX || X.cols() != N + 1 ||
    U.rows() != NU || U.cols() != N)
  {
    snprintf(diagnostics.error, sizeof(diagnostics.error),
             "invalid_solution_dimensions");
    return false;
  }
  if (!X.allFinite() || !U.allFinite()) {
    snprintf(diagnostics.error, sizeof(diagnostics.error),
             "non_finite_solution");
    return false;
  }

  diagnostics.initial_state_residual =
    (X.col(0) - measured).cwiseAbs().maxCoeff();
  diagnostics.max_dynamics_residual = 0.0;
  diagnostics.max_control_bound_violation = 0.0;
  diagnostics.max_control_rate_violation = 0.0;

  // 与生成模型同一离散语义: dt 内四个 RK4 子步, psi 不归一化。
  const USVKinematicModel model(params.dt, 4);
  const double du_step = params.du_max * params.dt;
  const double dr_step = params.dr_max * params.dt;

  Eigen::Vector2d previous_control = anchor;
  for (int k = 0; k < N; ++k) {
    const Eigen::Vector2d uk = U.col(k);

    diagnostics.max_control_bound_violation = std::max({
        diagnostics.max_control_bound_violation,
        params.u_min - uk(0), uk(0) - params.u_max,
        -params.r_max - uk(1), uk(1) - params.r_max});
    diagnostics.max_control_rate_violation = std::max({
        diagnostics.max_control_rate_violation,
        std::abs(uk(0) - previous_control(0)) - du_step,
        std::abs(uk(1) - previous_control(1)) - dr_step});

    const Vector5d predicted = model.forward_unwrapped(
      X.col(k), uk, params.tau_u, params.tau_r);
    diagnostics.max_dynamics_residual = std::max(
      diagnostics.max_dynamics_residual,
      (predicted - Vector5d(X.col(k + 1))).cwiseAbs().maxCoeff());

    previous_control = uk;
  }

  const double max_violation = std::max({
      diagnostics.initial_state_residual,
      diagnostics.max_dynamics_residual,
      diagnostics.max_control_bound_violation,
      diagnostics.max_control_rate_violation});
  if (max_violation > params.solution_constraint_tol) {
    snprintf(diagnostics.error, sizeof(diagnostics.error),
             "constraint_violation: initial=%.3g dynamics=%.3g "
             "bounds=%.3g rate=%.3g tol=%.3g",
             diagnostics.initial_state_residual,
             diagnostics.max_dynamics_residual,
             diagnostics.max_control_bound_violation,
             diagnostics.max_control_rate_violation,
             params.solution_constraint_tol);
    return false;
  }
  return true;
}

bool accept_kinematic_candidate(int status, bool finite, bool constraints_ok)
{
  const bool status_ok = (status == 0 || status == 2 || status == 7);
  return status_ok && finite && constraints_ok;
}

}  // namespace usv_mpc
