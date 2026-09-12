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
 * @file acados_backend.hpp
 * @brief acados C 后端 (动力学 NMPC)。
 *
 * codegen 逻辑对应 scripts/regenerate_acados_codegen.py (原 Python
 * usv_mpc/mpc_dynamic.py 的 _build_acados_solver 抽出)。
 *
 * 链接本包 vendored 的 codegen C 求解器 (acados_generated/,含
 * acados_solver_usv_dyn_nmpc.{c,h}),编译进 codegen_lib 静态库。运行时通过
 * C API 设 p_global(30维)/每阶段 x_ref(6维)/初始状态/热启动,调用
 * usv_dyn_nmpc_acados_solve。不再依赖 ~/.cache/usv_mpc_acados/ 或 Python codegen。
 *
 * acados OCP 设计 (与 Python codegen 完全一致):
 *   - 增广状态 x_aug = [x(6); u_prev(2)] (nx=8)
 *   - 控制量 u = [T_L, T_R] (nu=2)
 *   - 每阶段参数 p = x_ref (np=6)
 *   - 全局参数 p_global (30维) = 19 水动力学 + 6 Q + 2 R + 2 Rd + 1 Qf_scale
 *   - 变化率非线性约束 h = u - u_prev, |h| <= dT_max*dt (nh=2)
 *   - NONLINEAR_LS 代价，航向采用单位圆残差并使用 Gauss-Newton Hessian
 *   - SQP_RTI, DISCRETE 动力学 (内嵌 RK4 4 子步)
 *
 * 2026-08-11 起:推力边界 (lbu/ubu) 与变化率边界 (lh/uh) 在 solve() 中
 * 由 params (yaml) 逐阶段运行时下发 (K1/K2),codegen 烘焙值仅为默认值;
 * 求解失败回退为分级安全动作 (K4):shift 轨迹继续 → 轨迹耗尽双桨归零。
 */

#pragma once

#include <memory>
#include <string>

#include "usv_mpc_cpp/mpc_solver.hpp"

// codegen 求解器头 (本包 vendored, acados_generated/, CMake 加 -I)
#include "acados_solver_usv_dyn_nmpc.h"

namespace usv_mpc {

class AcadosBackend : public DynamicMpc {
 public:
  /// 构造 acados 求解器 (codegen 已静态链接进本包)。
  /// 抛 std::runtime_error 若 create 失败。
  explicit AcadosBackend(const MpcParams& params);

  ~AcadosBackend() override;

  std::pair<Eigen::Vector2d, SolveInfo>
  solve(const Vector6d& current_state, const Eigen::MatrixXd& reference) override;

  void set_applied_control(const Eigen::Vector2d& applied_control) override;

  void reset_warmstart() override;

  Eigen::MatrixXd get_predicted_trajectory() const override;

  int    N() const override { return params_.N; }
  double dt() const override { return params_.dt; }
  const char* backend() const override { return "acados"; }

 private:
  /// 组装 30 维 p_global (19 水动力学 + 6 Q + 2 R + 2 Rd + 1 Qf)。
  std::array<double, 30> build_p_global_() const;

  /// K4 分级安全回退:沿历史最优轨迹继续 → 轨迹耗尽后双桨归零。
  /// note 追加回退说明 (写入 SolveInfo.error 供 /mpc/status 上报)。
  Eigen::Vector2d safe_fallback_(std::string& note);

  MpcParams params_;

  // acados 句柄
  usv_dyn_nmpc_solver_capsule* capsule_ = nullptr;
  // nlp 句柄 (用于 set/get, 类型来自 acados)
  ocp_nlp_config* nlp_config_ = nullptr;
  ocp_nlp_dims*   nlp_dims_   = nullptr;
  ocp_nlp_in*     nlp_in_     = nullptr;
  ocp_nlp_out*    nlp_out_    = nullptr;

  // 热启动状态
  bool has_warm_ = false;
  Eigen::MatrixXd X_warm_;  // 8 x (N+1) 增广
  Eigen::MatrixXd U_warm_;  // 2 x N
  Eigen::Vector2d u_prev_ = Eigen::Vector2d::Zero();
  int fail_count_ = 0;      // K4: 连续求解失败计数 (成功/reset 时清零)
};

}  // namespace usv_mpc
