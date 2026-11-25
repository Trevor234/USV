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
 * @file kinematic_solution_audit.hpp
 * @brief 运动学 MPC 候选解的独立可行性核查 (纯函数, 不依赖求解器)。
 *
 * 迁移到 acados 后, 候选解来自生成的 C 求解器, 但验收标准与 IPOPT 时期
 * 完全相同: 初值、逐步动力学、控制幅值、首拍相对 anchor 的变化率、后续
 * 相邻变化率都必须落在 solution_constraint_tol 内。状态码 0 也不能免检。
 *
 * 动力学核查使用 USVKinematicModel::forward_unwrapped (显式四子步 RK4,
 * psi 不做 atan2 归一化), 避免把 ±2π 的连续轨迹误判为动力学残差。
 */

#pragma once

#include <Eigen/Dense>

#include "usv_mpc/kinematic_mpc_solver.hpp"

namespace usv_mpc
{

/// 候选解的可行性核查。诊断值写入 diagnostics 的四个残差字段。
/// X: 5 x (N+1) 预测状态; U: 2 x N 控制序列; anchor: 上一拍实际下发控制。
/// 返回 true 表示全部残差 <= params.solution_constraint_tol。
bool audit_kinematic_solution(
  const KinematicMpcParams & params,
  const Vector5d & measured,
  const Eigen::Vector2d & anchor,
  const Eigen::MatrixXd & X,
  const Eigen::MatrixXd & U,
  SolveInfo & diagnostics);

/// 是否接受候选: 只有成功/最大迭代/超时 + 有限 + 全部约束通过才接受。
bool accept_kinematic_candidate(int status, bool finite, bool constraints_ok);

}  // namespace usv_mpc
