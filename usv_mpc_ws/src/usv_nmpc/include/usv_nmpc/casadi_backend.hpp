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
 * @file casadi_backend.hpp
 * @brief CasADi Opti+IPOPT fallback 后端 (动力学 NMPC)。
 *
 * 对应 Python 版本: usv_mpc/mpc_dynamic_legacy.py (DynamicMPCLegacy)
 *
 * acados .so 不可用时启用。用 CasADi C++ Opti API 构建与 legacy Python 版
 * 等价的 NMPC:RK4 动力学约束、Q/R/Rd 代价 (含单位圆周期航向项)、
 * T_max/dT_max 边界、warm start。Pi5 上求解 ~80-200ms,接近 200ms 预算上限。
 */

#pragma once

#include <memory>
#include <utility>

#include <casadi/casadi.hpp>

#include "usv_nmpc/mpc_solver.hpp"
#include "usv_nmpc/usv_model_dynamic.hpp"

namespace usv_mpc
{

class CasadiBackend : public DynamicMpc {
public:
  explicit CasadiBackend(const MpcParams & params);

  std::pair<Eigen::Vector2d, SolveInfo>
  solve(const Vector6d & current_state, const Eigen::MatrixXd & reference) override;

  void set_applied_control(const Eigen::Vector2d & applied_control) override;

  void reset_warmstart() override;

  Eigen::MatrixXd get_predicted_trajectory() const override;

  int    N() const override {return params_.N;}
  double dt() const override {return params_.dt;}
  const char * backend() const override {return "casadi";}

private:
  MpcParams params_;
  casadi::Opti opti_;
  casadi::MX X_;          // 6 x (N+1)
  casadi::MX U_;          // 2 x N
  casadi::MX p_x0_;       // 6 x 1
  casadi::MX p_ref_;      // 6 x (N+1)
  casadi::MX p_u_prev_;   // 2 x 1
  // RK4 离散动力学 CasADi 函数 (用构造时数值参数固化)
  casadi::Function f_rk4_;

  bool has_warm_ = false;
  Eigen::MatrixXd X_warm_;  // 6 x (N+1)
  Eigen::MatrixXd U_warm_;  // 2 x N
  Eigen::Vector2d u_prev_ = Eigen::Vector2d::Zero();
};

}  // namespace usv_mpc
