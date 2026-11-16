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
 * @file mpc_solver.hpp
 * @brief 动力学 NMPC 求解器抽象接口 (NMPC C++ 版本)。
 *
 *
 * 后端选择:
 *   - acados (默认): 链接 codegen 的 C 求解器 (SQP_RTI), 求解 <10ms。
 *   - CasADi+IPOPT (fallback): acados .so 加载失败时启用 (Pi5 ~80-200ms)。
 *
 * 接口契约 ( mpc_node 无感知后端切换):
 *   solve(current_state[6], reference[6,N+1]) -> (u_opt[2], info)
 *   reset_warmstart()
 *   get_predicted_trajectory() -> [6, N+1] 或空
 *   N(), dt(), backend()
 */

#pragma once

#include <memory>
#include <string>
#include <utility>

#include <Eigen/Dense>

#include "usv_nmpc/usv_model_dynamic.hpp"

namespace usv_mpc
{

/// 6 维状态向量别名 (复用 model 头)。
using Vector6d = Eigen::Matrix<double, 6, 1>;

/// 求解结果信息。
struct SolveInfo
{
  bool        success = false;
  double      solve_time_ms = 0.0;
  // 字符串用定长数组: SolveInfo 按值跨 old/new ABI 边界返回 (casadi wheel
  // 为旧 ABI 构建时), std::string 的析构归属不安全 — POD 可安全跨界。
  char        backend[16] = "unknown";   // "acados" / "casadi" / "unknown"
  char        error[256] = "";
  // 预测轨迹 (6 x N+1), 列存;失败时为空。
  Eigen::MatrixXd X_pred;
  // 控制序列 (2 x N), 列存;失败时为空。
  Eigen::MatrixXd U_pred;
};

/// MPC 求解参数 (对应 mpc_params.yaml 的 dynamic.* + vehicle.*)。
struct MpcParams
{
  // 时域
  double dt = 0.2;
  int    N = 20;
  // 权重。Q/R/Rd 定义阶段运行代价密度，两个后端均对整段阶段代价乘 dt；
  // Qf_scale 只缩放不乘 dt 的终端状态代价。Rd 惩罚每步推力增量 ΔT，
  // 当前权重按固定 dt 调定，并不表示连续时间的推力变化率权重。
  Eigen::Matrix<double, 6, 1> Q_diag =
    (Eigen::Matrix<double, 6, 1>() << 20.0, 20.0, 50.0, 8.0, 1.0, 8.0).finished();
  Eigen::Vector2d R_diag = {0.05, 0.05};
  Eigen::Vector2d Rd_diag = {0.2, 0.2};
  double Qf_scale = 8.0;
  // 推力约束
  double T_max = 25.0;
  double T_min = -25.0;
  double dT_max = 80.0;
  // 模型
  HydroParams hydro;
};

/// 动力学 NMPC 求解器抽象接口。
class DynamicMpc {
public:
  virtual ~DynamicMpc() = default;

  /// 求解 NMPC。
  /// current_state: [x, y, psi, u, v, r]
  /// reference: [6, N+1] 参考状态轨迹
  /// 返回 (u_opt[2], info)
  virtual std::pair<Eigen::Vector2d, SolveInfo>
  solve(const Vector6d & current_state, const Eigen::MatrixXd & reference) = 0;

  /// 用执行层最终下发的等效左右推力覆盖下一拍 delta_T 锚点。
  /// 调用方应在每次发布控制后调用；输入必须有限且位于推力硬边界内。
  virtual void set_applied_control(const Eigen::Vector2d & applied_control) = 0;

  /// 清空热启动。
  virtual void reset_warmstart() = 0;

  /// 返回预测轨迹 (6 x N+1) 或空矩阵。
  virtual Eigen::MatrixXd get_predicted_trajectory() const = 0;

  virtual int    N() const = 0;
  virtual double dt() const = 0;
  virtual const char * backend() const = 0;  // 跨 ABI 边界, 返回字面量
};

/// 工厂:优先构造 acados 后端 (codegen 已 vendored+静态链接),失败回退 CasADi。
std::unique_ptr<DynamicMpc> make_dynamic_mpc(const MpcParams & params);

#ifdef USV_MPC_HAS_CASADI
/// 显式构造 CasADi 后端，供后端一致性诊断和回归测试使用。
std::unique_ptr<DynamicMpc> make_casadi_dynamic_mpc(const MpcParams & params);
#endif

}  // namespace usv_mpc
