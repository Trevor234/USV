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
 * @file fusion_capi.h
 * @brief 融合 NMPC 求解器的 C ABI（供 Python/ctypes 与离线校验使用）。
 *
 * 这是**唯一**的融合语义实现：Python 侧（训练环境、回放校验）只是这一层的
 * 调用者，不得另写一份 OCP 逻辑。语义与 AcadosBackend::solve(..., stage_residuals,
 * q_pi, lambda_pi) 完全一致：
 *   - 参考行主序 6 x (N+1)：[x, y, psi, u, v, r]
 *   - GP 残差行主序 3 x (N+1)：每阶段速度残差
 *   - q_pi/lambda_pi 只进 stage-0 代价，beta = sqrt(2*lambda_pi/dt)
 *
 * 所有函数线程安全性：单 handle 不可并发调用。
 */

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/// 创建 dynamic 模型的求解器实例。
/// p_global: 长度 30 的全局参数（19 水动力 + Q(6) + R(2) + Rd(2) + Qf_scale）。
/// 返回 0 表示成功，*out_handle 有效；非 0 时 *out_handle 为 NULL。
int p1_fusion_create(
  const double p_global[30], double lower, double upper, double max_delta,
  void ** out_handle);

/// 销毁实例（NULL 安全）。
void p1_fusion_destroy(void * handle);

/// 求解一拍。
/// state6: [x, y, psi, u, v, r]
/// ref_6x21_rowmajor: 6*(N+1) 行主序
/// res_3x21_rowmajor: 3*(N+1) 行主序
/// 返回 0 表示得到有限候选；非 0 时 out_u0 不被写入。
int p1_fusion_solve(
  void * handle, const double state6[6], const double * ref_6x21_rowmajor,
  const double * res_3x21_rowmajor, const double q_pi[2], double lambda_pi,
  double out_u0[2], double * out_solve_ms);

/// 设定上一拍实际下发控制（= AcadosBackend::set_anchor）。必须在 reset 之后调用：
/// reset_warmstart 会清零 anchor，生产路径的顺序是 reset → set_anchor → solve。
void p1_fusion_set_anchor(void * handle, const double anchor[2]);

/// 提交候选（热启动链左移）并把 anchor 置为 anchor[2]。
void p1_fusion_accept(void * handle, const double anchor[2]);

/// 受检整体重置（清 warm/anchor/候选）。
void p1_fusion_reset_warmstart(void * handle);

/// 是否有热启动链（1 = 有）。
int p1_fusion_has_warmstart(void * handle);

/// 最近一次错误描述（线程内静态缓冲；NULL 返回 "uninitialized"）。
const char * p1_fusion_last_error(void);

#ifdef __cplusplus
}  // extern "C"
#endif
