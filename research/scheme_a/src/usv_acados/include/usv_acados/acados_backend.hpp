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

// 标头只依赖 Eigen 与 C++ 标准库; acados 的 C API 是私有实现细节 (见 model_api.hpp)。
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>

#include <Eigen/Dense>

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

/// 单次 solve() 准备过程的 native 调用记账 (研究路径检查用, 每 solve 清零)。
/// N=20 的 dynamic 一轮完整准备必须是: constraints 82 次 (2 次 stage0 lbx/ubx
/// + 20 stage x 4 次 lbu/ubu/lh/uh), update_params 21 次, out_set 41 次。
struct PreparationLedger
{
  /// 进入本轮准备记 1 (每 solve 清零后置 1)。
  unsigned ordinals = 0;
  /// ocp_nlp_constraints_model_set 实际进入次数。
  unsigned constraint_set_calls = 0;
  /// 其中返回非零的次数。
  unsigned constraint_set_failed = 0;
  /// update_params 实际进入次数。
  unsigned update_params_calls = 0;
  /// 其中返回非零的次数。
  unsigned update_params_failed = 0;
  /// ocp_nlp_out_set 进入次数 (void 返回, 只计进入数)。
  unsigned out_set_calls = 0;
  /// 本轮准备是否全部完成 (任一 int 状态非零即 false)。
  bool complete = false;
};

/// 研究路径最后一道 native guard: 准备全部完成后、真实 solve 紧前回调。
/// 固定函数指针, 不逐拍分配 std::function; 回调抛出的类型化拒绝原样上抛。
struct SolveHooks
{
  void * context = nullptr;
  void (* before_native)(void * context, const PreparationLedger & ledger) = nullptr;
};

/// native 准备失败: constraints setter / update_params 返回非零。
/// 抛出时本轮零 C solve, 候选已失效, 未触碰 warm/anchor。
class NativePreparationError : public std::runtime_error
{
public:
  NativePreparationError(std::string operation, int stage, int status);
  const std::string operation;
  const int stage;
  const int status;
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
  /// reference: n_ref x (N+1), n_ref = 3 (kinematic) / 6 (dynamic), 第 2 行为 psi。
  /// 返回的引用在下一次 solve()/reset_warmstart() 前有效。
  const Candidate & solve(
    const Eigen::Ref<const Eigen::VectorXd> & physical_state,
    const Eigen::Ref<const Eigen::MatrixXd> & reference);

  /// 求解一拍 (研究路径): 准备全部完成后、真实 native solve 紧前调用 hook。
  /// hook 抛出的类型化拒绝原样上抛; 抛出时本轮零 C solve, 候选已失效,
  /// 不调用 accept_candidate()/shift_fallback(), 不重启 capsule。
  const Candidate & solve(
    const Eigen::Ref<const Eigen::VectorXd> & physical_state,
    const Eigen::Ref<const Eigen::MatrixXd> & reference,
    const SolveHooks & hooks);

  /// WP6/WP7 求解一拍: 为 dynamic 模型注入逐阶段 GP 速度残差均值 (3 x (N+1))
  /// 与首拍 PPO 偏好 (q_pi, lambda_pi >= 0)。kinematic 模型保持纯 3 维参考参数。
  const Candidate & solve(
    const Eigen::Ref<const Eigen::VectorXd> & physical_state,
    const Eigen::Ref<const Eigen::MatrixXd> & reference,
    const Eigen::Ref<const Eigen::MatrixXd> & stage_residuals,
    const Eigen::Vector2d & q_pi,
    double lambda_pi,
    const SolveHooks & hooks = SolveHooks{});

  /// 运行期全局参数事务: 维度/有限性检查通过后调用 set_p_global,
  /// 返回真实状态码。进入前使旧候选失效; 不清 warm 与 C++ 参数镜像。
  /// 非零状态必须由调用方 (事务层终端) 隔离, 不得继续求解。
  int update_p_global(const Eigen::Ref<const Eigen::VectorXd> & values);

  /// 受检原生重置: 先使当前候选失效, 再调用生成码 reset, 返回真实状态码。
  /// 不清 warm 与 C++ 参数镜像。
  int reset_native(int reset_qp_memory);

  /// 只清 C++ 侧 warm/anchor/candidate, 零 native 调用。
  void clear_cpp_state();

  /// 最近一次 solve() 的准备记账 (每 solve 开始清零)。
  const PreparationLedger & preparation() const;

  /// 真实 native solve 进入次数 (累计, 不随 solve 清零)。
  uint64_t native_solve_entries() const;

  /// 设定上一拍实际下发控制 (调用方负责 clamp/校验), 同时更新 warm 首列尾部。
  void set_anchor(const Eigen::Vector2d & anchor);
  const Eigen::Vector2d & anchor() const;

  /// 把当前候选提交为热启动链 (左移 + 末列复制 + anchor=首控制)。
  void accept_candidate();

  /// 失败回退原语: 取 warm 首控制并限幅, U 左移末列归零, X 左移, 更新 anchor。
  /// 无 warm 时返回零向量 (不改变 anchor)。
  Eigen::Vector2d shift_fallback();

  /// 受检整体重置: 先 reset_native(1), 非零抛 std::runtime_error 且不清 warm;
  /// 成功后才 clear_cpp_state()。旧调用方不得静默忽略失败状态。
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
