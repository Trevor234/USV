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
 * @brief acados 后端 (动力学 NMPC) —— usv_acados 共用求解引擎的适配器。
 *
 * OCP 结构 (生成码在 usv_acados/acados_generated/dynamic/,
 * 维护脚本 usv_acados/scripts/regenerate_acados_codegen.py --model dynamic):
 *   - 增广状态 x_aug = [x(6); T_prev(2)] (nx=8)
 *   - 控制量 u = [T_L, T_R] (nu=2)
 *   - 每阶段参数 p = x_ref (np=6)
 *   - 全局参数 p_global (30) = 19 水动力学 + 6 Q + 2 R + 2 Rd + 1 Qf_scale
 *   - 变化率非线性约束 h = u - u_prev, |h| <= dT_max*dt (nh=2)
 *   - NONLINEAR_LS 代价, 航向单位圆残差, SQP_RTI + GAUSS_NEWTON
 *
 * 本类保留方案 B 的全部语义: p_global 组装 (水动力+权重)、权重校验、
 * 连续失败计数、分级安全回退; 求解循环/热启动/候选管理委托给
 * usv_acados::AcadosBackend。
 *
 * 2026-08-11 起: 推力边界 (lbu/ubu) 与变化率边界 (lh/uh) 由 solve() 按
 * params (yaml) 逐阶段运行时下发 (K1/K2), codegen 烘焙值仅为默认值;
 * 求解失败回退为分级安全动作 (K4): shift 轨迹继续 → 轨迹耗尽双桨归零。
 */

#pragma once

#include <array>
#include <memory>
#include <string>
#include <utility>

#include "usv_acados/acados_backend.hpp"
#include "usv_nmpc/mpc_solver.hpp"

namespace usv_mpc
{

class AcadosBackend : public DynamicMpc {
public:
  /// 构造共用 acados 引擎 (dynamic 模型)。抛 std::runtime_error 若 create 失败,
  /// 抛 std::invalid_argument 若权重非法。
  explicit AcadosBackend(const MpcParams & params);

  ~AcadosBackend() override;

  std::pair<Eigen::Vector2d, SolveInfo>
  solve(const Vector6d & current_state, const Eigen::MatrixXd & reference) override;

  void set_applied_control(const Eigen::Vector2d & applied_control) override;

  void reset_warmstart() override;

  Eigen::MatrixXd get_predicted_trajectory() const override;

  int    N() const override {return params_.N;}
  double dt() const override {return params_.dt;}
  const char * backend() const override {return "acados";}

private:
  /// 组装 30 维 p_global (19 水动力学 + 6 Q + 2 R + 2 Rd + 1 Qf)。
  std::array<double, 30> build_p_global_() const;

  /// 把冻结参数映射成共用引擎的 Problem (边界已乘 dt)。
  usv_acados::Problem build_problem_() const;

  /// K4 分级安全回退:沿历史最优轨迹继续 → 轨迹耗尽后双桨归零。
  /// note 追加回退说明 (写入 SolveInfo.error 供 /mpc/status 上报)。
  Eigen::Vector2d safe_fallback_(std::string & note);

  MpcParams params_;

  // 共用求解引擎 (独占 capsule + 热启动缓存)
  std::unique_ptr<usv_acados::AcadosBackend> engine_;
  int fail_count_ = 0;      // K4: 连续求解失败计数 (成功/reset 时清零)
};

}  // namespace usv_mpc
