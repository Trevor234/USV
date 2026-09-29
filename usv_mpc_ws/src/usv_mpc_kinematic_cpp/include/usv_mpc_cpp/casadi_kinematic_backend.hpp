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
 * @file casadi_kinematic_backend.hpp
 * @brief CasADi Opti+IPOPT 后端 (方案 A 运动学 MPC)。
 *
 * 对应 Python 版本: usv_mpc/mpc_kinematic.py (KinematicMPC)
 *
 * 用 CasADi C++ MX 符号构建运动学 ODE (5 状态: x,y,psi + 一阶滞后
 * u,r; 控制 = 速度目标 u_cmd,r_cmd), RK4 离散化, Opti+IPOPT 求解。
 * 滞后让 MPC 预测执行器响应 (tau_r = Iz_eff/Nr ≈ 1.78s), 消除级联
 * 内外环时间尺度失配导致的锯齿。
 *
 * 代价: 位置误差二次 + 航向 2*Q_psi*(1-cos(dψ)) + 控制能量 ||u||_R^2
 *       (无 Rd 控制率代价, 对齐 Python mpc_kinematic.py)
 * 约束: u in [u_min, u_max], r in [-r_max, r_max],
 *       du/dr 速率约束 (du_max/dr_max * dt 每步)
 * 热启动: 保存上次解, 平移作下次初值 (对齐 Python)。
 */

#pragma once

#include <utility>

#include <Eigen/Dense>
#include <casadi/casadi.hpp>

#include "usv_mpc_cpp/kinematic_mpc_solver.hpp"
#include "usv_mpc_cpp/usv_model_kinematic.hpp"

namespace usv_mpc
{

class CasadiKinematicBackend : public KinematicMpc {
public:
  explicit CasadiKinematicBackend(const KinematicMpcParams & params);

  std::pair<Eigen::Vector2d, SolveInfo>
  solve(
    const Eigen::Matrix<double, 5, 1> & current_state,
    const Eigen::MatrixXd & reference) override;

  void reset_warmstart() override;
  void set_applied_command(const Eigen::Vector2d & applied) override;
  Eigen::MatrixXd get_predicted_trajectory() const override;

  int    N() const override {return params_.N;}
  double dt() const override {return params_.dt;}
  const char * backend() const override {return "casadi";}

private:
  KinematicMpcParams params_;
  casadi::Opti opti_;
  casadi::MX X_;          // 5 x (N+1)
  casadi::MX U_;          // 2 x N
  casadi::MX p_x0_;       // 5 x 1
  casadi::MX p_ref_;      // 3 x (N+1)  (代价只引用 x,y,psi)
  casadi::MX p_u_prev_;   // 2 x 1
  // RK4 离散动力学 CasADi 函数 (符号构建, 运动学 ODE 无参数)
  casadi::Function f_rk4_;

  bool has_warm_ = false;
  Eigen::MatrixXd X_warm_;  // 5 x (N+1)
  Eigen::MatrixXd U_warm_;  // 2 x N
  Eigen::Vector2d u_prev_ = Eigen::Vector2d::Zero();
  // 对偶热启动: Opti 每次求解把 lam_g() 符号当前值作为 lam_g0 传给 IPOPT
  // (solve_prepare 无条件读取), 成功后回存。限制: Opti 不支持 lam_x0,
  // 界乘子无法热启动, 只有约束乘子生效。
  casadi::DM lam_g_warm_;
  bool has_dual_ = false;
};

}  // namespace usv_mpc
