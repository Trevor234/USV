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
 * @file model_api.hpp
 * @brief 生成模型描述符与两套 C API 的类型安全薄包装 (私有头)。
 *
 * 只有本包的 model_api.cpp 需要包含生成头。函数指针表把 void* 在包装层转成
 * 对应 capsule 类型 —— 一种 capsule 绝不会被强转成另一种。
 */

#pragma once

// 生成求解器 C API 头 (acados_c) 是 C system header, 必须排在 C++ system 之前。
#include <acados_c/ocp_nlp_interface.h>

#include "usv_acados/acados_backend.hpp"

namespace usv_acados
{
namespace detail
{

/// 生成码烘焙的维度契约。
struct ModelDescriptor
{
  Model model;
  const char * name;       // 诊断用标签 ("kinematic"/"dynamic")
  const char * symbol;     // 生成码符号前缀
  int N;                   // 烘焙时域
  int n_phys;              // 物理状态维
  int nu;                  // 控制维
  int n_aug;               // 增广状态维 (n_phys + nu)
  int n_ref;               // 参考维 (kinematic 3 / dynamic 6)
  int np;                  // 每阶段参数维 (kinematic 3 / dynamic 12)
  int np_global;           // 全局参数维
  int ny_0;                // stage 0 残差维
  int ny;                  // stage 残差维
  int ny_e;                // 终端残差维
  int nh_0;                // stage 0 非线性约束维
  int nh;                  // 非线性约束维
  /// 增广状态尾部 anchor 起始下标 (== n_phys)。
  int anchor_offset;
};

/// 生成 C API 的函数指针表 (每种模型一份, 由 model_api.cpp 填充)。
struct CapsuleOps
{
  void * (*create_capsule)();
  int (*create)(void *);
  int (*free)(void *);
  int (*free_capsule)(void *);
  int (*reset)(void *, int);
  int (*update_params)(void *, int, double *, int);
  int (*set_p_global)(void *, double *, int);
  int (*solve)(void *);
  ocp_nlp_config * (*get_config)(void *);
  ocp_nlp_dims * (*get_dims)(void *);
  ocp_nlp_in * (*get_in)(void *);
  ocp_nlp_out * (*get_out)(void *);
  ocp_nlp_solver * (*get_solver)(void *);
};

const ModelDescriptor & descriptor_for(Model model);
const CapsuleOps & ops_for(Model model);

}  // namespace detail
}  // namespace usv_acados
