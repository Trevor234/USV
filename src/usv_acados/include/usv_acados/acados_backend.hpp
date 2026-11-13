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
 * @brief 方案 A/B 共用的 acados 求解引擎 (ROS 无关)。
 *
 * 本类只负责“一个已 vendored 的 acados OCP 实例 + 求解循环 + 热启动缓存”,
 * 不包含任何方案语义 (不加残差门禁, 不做失败回退决策, 不组装 p_global)。
 * 具体模型由 Model 选择, 两套生成码各自独立:
 *   - Kinematic: src/usv_acados/acados_generated/kinematic/  (usv_kin_mpc_*)
 *   - Dynamic:   src/usv_acados/acados_generated/dynamic/    (usv_dyn_nmpc_*)
 *
 * 数据契约由 Problem 描述, 生成码的烘焙尺寸在构造时逐项核对:
 *   kinematic: n_phys=5, nu=2, n_aug=7, np=3, np_global=8
 *   dynamic:   n_phys=6, nu=2, n_aug=8, np=6, np_global=30
 *
 * 语义约定:
 *   - 增广状态尾部 nu 维是本阶段控制的“精确赋值”, 由生成模型保证;
 *   - anchor 是上一拍实际下发的控制, 由适配器 (方案 A/B 节点) clamp/校验后送入;
 *   - solve() 不提交热启动, accept_candidate() 才左移并写 anchor;
 *   - 候选数据在通过调用方门禁之前不污染 warm/anchor。
 *
 * 线程安全: 每个实例独占 capsule, 无共享可变状态; 同一实例不可并发调用。
 */

#pragma once

// Eigen 与 acados 的 C 头按 cpplint 的 "C system" 分类排在 C++ 标准库之前。
#include <Eigen/Dense>

#include <memory>

namespace usv_acados
{

/// 生成模型选择。两种模型的状态/控制/参数维度与生成码均不同, 不可互换。
enum class Model { Kinematic, Dynamic };

/// 构造参数 (来自冻结 YAML, 由各方案适配器校验后传入)。
struct Problem
{
  int N = 0;
  double dt = 0.0;
  /// 全局参数, 长度必须等于生成码的 np_global。
  Eigen::VectorXd p_global;
  /// 控制幅值下/上界 (nu 维, 两通道各自独立, 允许非对称)。
  Eigen::Vector2d lower = Eigen::Vector2d::Zero();
  Eigen::Vector2d upper = Eigen::Vector2d::Zero();
  /// 每步允许的控制变化量 (nu 维, 已乘 dt)。
  Eigen::Vector2d max_delta = Eigen::Vector2d::Zero();
};

/// 一次求解的候选解 (原始输出, 尚未经过适配器门禁)。
struct Candidate
{
  /// generated solve 返回状态码 (acados 语义; -1 = 尚未求解)。
  int status = -1;
  /// 状态码允许提取且全部数据有限。
  bool finite = false;
  /// 仅 generated solve 调用的墙钟时间 (ms)。
  double solver_time_ms = 0.0;
  /// 增广状态轨迹 n_aug x (N+1); 未提取时为空。
  Eigen::MatrixXd X_aug;
  /// 控制序列 nu x N; 未提取时为空。
  Eigen::MatrixXd U;
};

/**
 * @brief 单个 acados OCP 实例的求解引擎。
 *
 * 构造失败抛 std::runtime_error (capsule 创建/尺寸不匹配/缺少生成符号),
 * 参数错误抛 std::invalid_argument。所有 acados 返回状态均被检查。
 */
class AcadosBackend {
public:
  AcadosBackend(Model model, const Problem & problem);
  ~AcadosBackend();

  AcadosBackend(const AcadosBackend &) = delete;
  AcadosBackend & operator=(const AcadosBackend &) = delete;

  /// 求解一拍。
  /// physical_state: n_phys 维实测状态 (psi 已归一化到 [-pi, pi])。
  /// reference: n_ref x (N+1), n_ref = np (kinematic 3 / dynamic 6), 第 2 行为 psi。
  /// 返回的引用在下一次 solve()/reset_warmstart() 前有效。
  const Candidate & solve(
    const Eigen::Ref<const Eigen::VectorXd> & physical_state,
    const Eigen::Ref<const Eigen::MatrixXd> & reference);

  /// 设定上一拍实际下发控制 (调用方负责 clamp/校验), 同时更新 warm 首列尾部。
  void set_anchor(const Eigen::Vector2d & anchor);
  const Eigen::Vector2d & anchor() const;

  /// 把当前候选提交为热启动链 (左移 + 末列复制 + anchor=首控制)。
  void accept_candidate();

  /// 失败回退原语: 取 warm 首控制并限幅, U 左移末列归零, X 左移, 更新 anchor。
  /// 无 warm 时返回零向量 (不改变 anchor)。
  Eigen::Vector2d shift_fallback();

  /// 清空热启动缓存/anchor 并重置 acados (含 QP 内存)。
  void reset_warmstart();

  bool has_warmstart() const;
  const Eigen::MatrixXd & warm_states() const;

  /// 有效有限候选的 acados 代价 (0.5*y'W*y 之和)。无候选时抛 std::logic_error。
  /// 仅用于数值诊断, 不进入生产每拍路径。
  double candidate_cost() const;

  Model model() const;
  int n_phys() const;
  int n_aug() const;
  int nu() const;

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace usv_acados
