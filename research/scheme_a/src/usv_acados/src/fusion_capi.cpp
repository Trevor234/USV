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
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
// FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
// IN THE SOFTWARE.

/**
 * @file fusion_capi.cpp
 * @brief 融合求解器的 C ABI 包装：只做参数搬运与异常翻译，不含任何 OCP 语义。
 *
 * 每个 handle 独占一个 AcadosBackend(Model::Dynamic) 实例；融合项（GP 残差、
 * PPO 首拍偏好）全部由 AcadosBackend::solve 实现，这里不重复。
 */

#include "usv_acados/fusion_capi.h"

#include <Eigen/Dense>

#include <cmath>
#include <cstring>
#include <exception>
#include <new>
#include <string>

#include "usv_acados/acados_backend.hpp"

namespace
{

constexpr int kPGlobal = 30;
constexpr int kN = 20;
constexpr int kCols = kN + 1;
constexpr double kDt = 0.2;

/// 线程内最近错误（研究/训练侧单线程调用；不是跨线程错误通道）。
thread_local std::string g_last_error;

struct FusionHandle
{
  usv_acados::AcadosBackend backend;
  Eigen::MatrixXd reference;
  Eigen::MatrixXd residuals;

  FusionHandle(const Eigen::VectorXd & p_global, double lower, double upper,
    double max_delta)
  : backend(usv_acados::Model::Dynamic, make_problem(p_global, lower, upper, max_delta)),
    reference(Eigen::MatrixXd::Zero(6, kCols)),
    residuals(Eigen::MatrixXd::Zero(3, kCols))
  {
  }

  static usv_acados::Problem make_problem(
    const Eigen::VectorXd & p_global, double lower, double upper, double max_delta)
  {
    usv_acados::Problem problem;
    problem.N = kN;
    problem.dt = kDt;
    problem.p_global = p_global;
    problem.lower = Eigen::Vector2d::Constant(lower);
    problem.upper = Eigen::Vector2d::Constant(upper);
    problem.max_delta = Eigen::Vector2d::Constant(max_delta);
    return problem;
  }
};

int fail(const std::string & message)
{
  g_last_error = message;
  return 1;
}

/// 行主序缓冲 -> Eigen 列主序矩阵：按 (rows, cols) 行主序映射后逐元素拷贝，
/// 逻辑下标 (i, k) 保持为第 i 行第 k 列（拷贝即完成布局转换，不能再转置）。
void load_row_major(const double * src, int rows, int cols, Eigen::MatrixXd & dst)
{
  const Eigen::Map<const Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic,
    Eigen::RowMajor>> view(src, rows, cols);
  dst = view;
}

}  // namespace

extern "C" {

int p1_fusion_create(
  const double p_global[30], double lower, double upper, double max_delta,
  void ** out_handle)
{
  if (out_handle == nullptr) {
    return fail("p1_fusion_create: out_handle is NULL");
  }
  *out_handle = nullptr;
  if (p_global == nullptr) {
    return fail("p1_fusion_create: p_global is NULL");
  }
  if (!std::isfinite(lower) || !std::isfinite(upper) || !std::isfinite(max_delta) ||
    !(lower < upper) || !(max_delta > 0.0))
  {
    return fail("p1_fusion_create: 非法边界 (需要 lower<upper, max_delta>0)");
  }
  try {
    Eigen::Map<const Eigen::VectorXd> p(p_global, kPGlobal);
    if (!p.allFinite()) {
      return fail("p1_fusion_create: p_global 含非有限值");
    }
    *out_handle = new FusionHandle(p, lower, upper, max_delta);
    return 0;
  } catch (const std::exception & exc) {
    return fail(std::string("p1_fusion_create: ") + exc.what());
  } catch (...) {
    return fail("p1_fusion_create: 未知异常");
  }
}

void p1_fusion_destroy(void * handle)
{
  delete static_cast<FusionHandle *>(handle);
}

int p1_fusion_solve(
  void * handle, const double state6[6], const double * ref_6x21_rowmajor,
  const double * res_3x21_rowmajor, const double q_pi[2], double lambda_pi,
  double out_u0[2], double * out_solve_ms)
{
  auto * self = static_cast<FusionHandle *>(handle);
  if (self == nullptr) {
    return fail("p1_fusion_solve: handle is NULL");
  }
  if (state6 == nullptr || ref_6x21_rowmajor == nullptr ||
    res_3x21_rowmajor == nullptr || q_pi == nullptr || out_u0 == nullptr)
  {
    return fail("p1_fusion_solve: NULL 输入/输出指针");
  }
  if (!std::isfinite(lambda_pi) || lambda_pi < 0.0) {
    return fail("p1_fusion_solve: lambda_pi 必须有限且 >= 0");
  }
  try {
    Eigen::Map<const Eigen::VectorXd> state(state6, 6);
    Eigen::Map<const Eigen::Vector2d> q(q_pi);
    if (!state.allFinite() || !q.allFinite()) {
      return fail("p1_fusion_solve: state/q_pi 含非有限值");
    }
    load_row_major(ref_6x21_rowmajor, 6, kCols, self->reference);
    load_row_major(res_3x21_rowmajor, 3, kCols, self->residuals);
    const auto & candidate = self->backend.solve(
      state, self->reference, self->residuals, q, lambda_pi);
    if (!candidate.finite) {
      return fail("p1_fusion_solve: 求解器未产出有限候选, status=" +
        std::to_string(candidate.status));
    }
    out_u0[0] = candidate.U(0, 0);
    out_u0[1] = candidate.U(1, 0);
    if (out_solve_ms != nullptr) {
      *out_solve_ms = candidate.solver_time_ms;
    }
    return 0;
  } catch (const std::exception & exc) {
    return fail(std::string("p1_fusion_solve: ") + exc.what());
  } catch (...) {
    return fail("p1_fusion_solve: 未知异常");
  }
}

void p1_fusion_set_anchor(void * handle, const double anchor[2])
{
  auto * self = static_cast<FusionHandle *>(handle);
  if (self == nullptr || anchor == nullptr) {
    g_last_error = "p1_fusion_set_anchor: handle/anchor is NULL";
    return;
  }
  try {
    Eigen::Map<const Eigen::Vector2d> a(anchor);
    if (!a.allFinite()) {
      g_last_error = "p1_fusion_set_anchor: anchor 含非有限值";
      return;
    }
    self->backend.set_anchor(a);
  } catch (const std::exception & exc) {
    g_last_error = std::string("p1_fusion_set_anchor: ") + exc.what();
  }
}

void p1_fusion_accept(void * handle, const double anchor[2])
{
  auto * self = static_cast<FusionHandle *>(handle);
  if (self == nullptr || anchor == nullptr) {
    g_last_error = "p1_fusion_accept: handle/anchor is NULL";
    return;
  }
  try {
    Eigen::Map<const Eigen::Vector2d> a(anchor);
    if (!a.allFinite()) {
      g_last_error = "p1_fusion_accept: anchor 含非有限值";
      return;
    }
    self->backend.accept_candidate();
    self->backend.set_anchor(a);
  } catch (const std::exception & exc) {
    g_last_error = std::string("p1_fusion_accept: ") + exc.what();
  }
}

void p1_fusion_reset_warmstart(void * handle)
{
  auto * self = static_cast<FusionHandle *>(handle);
  if (self == nullptr) {
    g_last_error = "p1_fusion_reset_warmstart: handle is NULL";
    return;
  }
  try {
    self->backend.reset_warmstart();
  } catch (const std::exception & exc) {
    g_last_error = std::string("p1_fusion_reset_warmstart: ") + exc.what();
  }
}

int p1_fusion_has_warmstart(void * handle)
{
  auto * self = static_cast<FusionHandle *>(handle);
  if (self == nullptr) {
    return 0;
  }
  return self->backend.has_warmstart() ? 1 : 0;
}

const char * p1_fusion_last_error(void)
{
  return g_last_error.c_str();
}

}  // extern "C"
