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
 * @file acados_kinematic_backend.hpp
 * @brief acados 后端 (方案 A 运动学 MPC) —— usv_acados 共用引擎的适配器。
 *
 * OCP 结构 (生成码在 usv_acados/acados_generated/kinematic/,
 * 维护脚本 usv_acados/scripts/regenerate_acados_codegen.py --model kinematic):
 *   - 物理状态 [x,y,psi,u,r] (5) + 增广尾部 [u_cmd_prev,r_cmd_prev] (2) => nx=7
 *   - 控制 [u_cmd,r_cmd] (nu=2), 参考 [x_ref,y_ref,psi_ref] (np=3)
 *   - p_global (8) = [tau_u,tau_r,Qx,Qy,Qpsi,Ru,Rr,Qf_scale]
 *   - 变化率约束 |u_k - u_{k-1}| <= [du_max*dt, dr_max*dt] (含首拍 vs anchor)
 *   - NONLINEAR_LS + cost_scaling=ones(N+1) (阶段代价不乘 dt, 与原目标一致)
 *   - SQP + MERIT_BACKTRACKING + GAUSS_NEWTON + FULL_CONDENSING_HPIPM,
 *     nlp_solver_max_iter=50, timeout_max_time=0.12s, tol=1e-4
 *
 * 本类保留方案 A 的语义: p_global 组装、参数合法性校验、候选解四残差
 * 硬门禁、按通道 clamp 的实际下发锚点; 求解循环/热启动委托给
 * usv_acados::AcadosBackend。
 */

#pragma once

#include <memory>
#include <utility>

#include <Eigen/Dense>

#include "usv_acados/acados_backend.hpp"
#include "usv_mpc/kinematic_mpc_solver.hpp"

namespace usv_mpc
{

class AcadosKinematicBackend : public KinematicMpc {
public:
  /// 构造共用 acados 引擎 (kinematic 模型)。
  /// 抛 std::invalid_argument 若 tau/权重/dt/边界非法,
  /// 抛 std::runtime_error 若生成码尺寸与配置不符。
  explicit AcadosKinematicBackend(const KinematicMpcParams & params);

  ~AcadosKinematicBackend() override;

  std::pair<Eigen::Vector2d, SolveInfo>
  solve(
    const Eigen::Matrix<double, 5, 1> & current_state,
    const Eigen::MatrixXd & reference) override;

  void reset_warmstart() override;
  void set_applied_command(const Eigen::Vector2d & applied) override;
  Eigen::MatrixXd get_predicted_trajectory() const override;

  int N() const override {return params_.N;}
  double dt() const override {return params_.dt;}
  const char * backend() const override {return "acados";}

  /// 当前有效有限候选的 acados 代价 (仅数值诊断/测试使用, 每拍不调用)。
  /// 无有效候选时抛 std::logic_error。
  double diagnostic_cost() const;

private:
  /// 8 维 p_global: [tau_u,tau_r,Qx,Qy,Qpsi,Ru,Rr,Qf_scale]。
  Eigen::VectorXd build_p_global_() const;

  /// 把冻结参数映射成共用引擎的 Problem (变化率已乘 dt)。
  usv_acados::Problem build_problem_() const;

  KinematicMpcParams params_;
  std::unique_ptr<usv_acados::AcadosBackend> engine_;
};

}  // namespace usv_mpc
