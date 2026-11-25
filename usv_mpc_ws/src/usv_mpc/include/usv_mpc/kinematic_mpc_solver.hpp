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
 * @file kinematic_mpc_solver.hpp
 * @brief 运动学 MPC 求解器抽象接口 (方案 A)。
 *
 * 后端: 仅 acados (SQP + MERIT_BACKTRACKING)。生成码 vendored 在共用包
 * usv_acados/acados_generated/kinematic/ (usv_kin_mpc_*), 求解循环由
 * usv_acados::AcadosBackend 提供; 本方案不再包含 CasADi/IPOPT 后端。
 *
 * 接口契约 (mpc_node 无感知后端切换):
 *   solve(current_state[5], reference[3,N+1]) -> (u_opt[2], info)
 *   reset_warmstart() / set_applied_command(applied)
 *   get_predicted_trajectory() -> [5, N+1] 或空
 *   N(), dt(), backend()
 */

#pragma once

#include <memory>
#include <string>
#include <utility>

#include <Eigen/Dense>

#include "usv_mpc/usv_model_kinematic.hpp"

namespace usv_mpc
{

/// 5 状态向量 [x, y, psi, u, r] (含一阶速度滞后)
using Vector5d = Eigen::Matrix<double, 5, 1>;

/// 求解结果信息。
/// 字段与方案 B 的 SolveInfo 对齐, 便于 mpc_node 统一处理。
struct SolveInfo
{
  bool        success = false;
  double      solve_time_ms = 0.0;
  // 候选轨迹可行性诊断。成功解和 IPOPT 早停回收解使用同一套门禁。
  double initial_state_residual = 0.0;
  double max_dynamics_residual = 0.0;
  double max_control_bound_violation = 0.0;
  double max_control_rate_violation = 0.0;
  // 字符串用定长数组: SolveInfo 按值返回, POD 布局在跨模块/测试间稳定。
  char        backend[16] = "acados";    // 方案 A 仅支持 acados
  char        error[256] = "";
  // 预测轨迹 (5 x N+1), 列存 (前 3 行 x,y,psi); 失败时为空。
  Eigen::MatrixXd X_pred;
  // 控制序列 (2 x N), 列存; 失败时为空。
  Eigen::MatrixXd U_pred;
};

/// 运动学 MPC 参数 (对应 mpc_params_A.yaml 的 kinematic.*)。
/// 与方案 B 的 MpcParams 对齐, 但: 无 Rd (控制率代价)、无 HydroParams、
/// 约束是 u/r 边界 + du/dr 速率 (非 T/dT)。
struct KinematicMpcParams
{
  // 时域
  double dt = 0.2;
  int    N = 20;
  // 权重 (Q 3维: x, y, psi; R 2维: u, r)
  Eigen::Vector3d Q_diag = {10.0, 10.0, 50.0};
  Eigen::Vector2d R_diag = {1.0, 1.0};
  double Qf_scale = 10.0;
  // 控制: 无 Rd (运动学方案无控制率代价; 速率仍作硬约束)
  // 边界
  double u_max = 2.0;
  double u_min = 0.0;     // 运动学允许 u_min>=0 (不允许倒车); 非对称边界
  double r_max = 0.5;     // r 对称: [-r_max, r_max]
  // 速率约束 (单位: 每秒变化率; 实际每步约束 = *dt)
  double du_max = 0.8;    // u 的每秒变化率上限
  double dr_max = 0.5;    // r 的每秒变化率上限
  // 执行器一阶滞后时间常数 (2026-09-03/07 辨识): 5 状态模型的滞后动力学
  double tau_u = 0.8;     // s, 纵向速度环 (m/drag'(u_cruise) ≈ 0.7-0.9)
  double tau_r = 1.78;    // s, 艏摇环 (Iz_eff/Nr = 5.537/3.105)
  // 成功解和早停候选解允许的最大初值/动力学/边界/变化率残差。
  double solution_constraint_tol = 5e-3;
};

/// 运动学 MPC 求解器抽象接口 (对齐 B 的 DynamicMpc)。
class KinematicMpc {
public:
  virtual ~KinematicMpc() = default;

  /// 求解运动学 MPC。
  /// current_state: [x, y, psi, u, r] (u/r 为测量值, 滞后状态初值)
  /// reference: [3, N+1] 参考轨迹 (x, y, psi)
  /// 返回 (u_opt[2]=[u_cmd_surge, r_cmd_yaw], info)
  virtual std::pair<Eigen::Vector2d, SolveInfo>
  solve(
    const Eigen::Matrix<double, 5, 1> & current_state,
    const Eigen::MatrixXd & reference) = 0;

  /// 清空热启动 (含对偶乘子; 速率约束锚点 u_prev_ 归零)。
  virtual void reset_warmstart() = 0;

  /// 写回"实际下发的指令"作为下一拍速率约束锚点 (U(0,0)-u_prev 约束)。
  /// 节点在每次发布 cmd 后调用, 使锚点语义与真实执行一致; 实现方须
  /// clamp 到 [u_min,u_max]x[-r_max,r_max], 防异常值导致首步约束不可行。
  virtual void set_applied_command(const Eigen::Vector2d & applied) = 0;

  /// 返回预测轨迹 (5 x N+1, 前 3 行 x,y,psi) 或空矩阵。
  virtual Eigen::MatrixXd get_predicted_trajectory() const = 0;

  virtual int    N() const = 0;
  virtual double dt() const = 0;
  virtual const char * backend() const = 0;  // 跨 ABI 边界, 返回字面量
};

/// 工厂: 构造 acados 后端 (方案 A 唯一后端)。
/// 与 B 的 make_dynamic_mpc 对齐, 但无 cache/inc/lib 参数。
std::unique_ptr<KinematicMpc> make_kinematic_mpc(const KinematicMpcParams & params);

}  // namespace usv_mpc
