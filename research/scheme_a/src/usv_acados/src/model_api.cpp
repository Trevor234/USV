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
 * @file model_api.cpp
 * @brief 生成模型描述符与两套 C API 包装实现。
 *
 * 编译期核对生成头里的宏与 C++ 侧索引契约; 运行期核对 nlp_dims 与 Problem。
 * 两个模型的 capsule 类型不兼容, 各自 wrapper 内完成 void* 转换。
 */

#include "model_api.hpp"

// 两套生成码 (各自独立的 vendored 目录, 符号前缀不同)。
// 生成头由各 generated 目录直接加入 include path, 不位于子目录中。
#include "acados_solver_usv_dyn_nmpc.h"  // NOLINT(build/include_subdir)
#include "acados_solver_usv_kin_mpc.h"  // NOLINT(build/include_subdir)

namespace usv_acados
{
namespace detail
{

// ── 编译期契约 (B: 6 物理 + 2 增广, A: 5 物理 + 2 增广) ──────────────
// 原 usv_nmpc 的代码只断言了残差维, 这里把全部尺寸一次性钉住。
static_assert(USV_DYN_NMPC_NX == 8, "dynamic generated nx != 8");
static_assert(USV_DYN_NMPC_NU == 2, "dynamic generated nu != 2");
static_assert(USV_DYN_NMPC_NP == 6, "dynamic generated np != 6");
static_assert(USV_DYN_NMPC_NP_GLOBAL == 30, "dynamic generated np_global != 30");
static_assert(USV_DYN_NMPC_NBX0 == 8, "dynamic generated nbx_0 != 8");
static_assert(USV_DYN_NMPC_NY0 == 11, "dynamic generated ny_0 != 11");
static_assert(USV_DYN_NMPC_NY == 11, "dynamic generated ny != 11");
static_assert(USV_DYN_NMPC_NYN == 7, "dynamic generated ny_e != 7");
static_assert(USV_DYN_NMPC_NH == 2, "dynamic generated nh != 2");
static_assert(USV_DYN_NMPC_NH0 == 2, "dynamic generated nh_0 != 2");

static_assert(USV_KIN_MPC_NX == 7, "kinematic generated nx != 7");
static_assert(USV_KIN_MPC_NU == 2, "kinematic generated nu != 2");
static_assert(USV_KIN_MPC_NP == 3, "kinematic generated np != 3");
static_assert(USV_KIN_MPC_NP_GLOBAL == 8, "kinematic generated np_global != 8");
static_assert(USV_KIN_MPC_NBX0 == 7, "kinematic generated nbx_0 != 7");
static_assert(USV_KIN_MPC_NY0 == 6, "kinematic generated ny_0 != 6");
static_assert(USV_KIN_MPC_NY == 6, "kinematic generated ny != 6");
static_assert(USV_KIN_MPC_NYN == 4, "kinematic generated ny_e != 4");
static_assert(USV_KIN_MPC_NH == 2, "kinematic generated nh != 2");
static_assert(USV_KIN_MPC_NH0 == 2, "kinematic generated nh_0 != 2");

namespace
{

// ── dynamic (usv_dyn_nmpc_*) ────────────────────────────────────────
usv_dyn_nmpc_solver_capsule * dyn(void * capsule)
{
  return static_cast<usv_dyn_nmpc_solver_capsule *>(capsule);
}

void * dyn_create_capsule()
{
  return usv_dyn_nmpc_acados_create_capsule();
}

int dyn_create(void * capsule) {return usv_dyn_nmpc_acados_create(dyn(capsule));}
int dyn_free(void * capsule) {return usv_dyn_nmpc_acados_free(dyn(capsule));}
int dyn_free_capsule(void * capsule)
{
  return usv_dyn_nmpc_acados_free_capsule(dyn(capsule));
}
int dyn_reset(void * capsule, int reset_qp_mem)
{
  return usv_dyn_nmpc_acados_reset(dyn(capsule), reset_qp_mem);
}
int dyn_update_params(void * capsule, int stage, double * value, int np)
{
  return usv_dyn_nmpc_acados_update_params(dyn(capsule), stage, value, np);
}
int dyn_set_p_global(void * capsule, double * data, int len)
{
  return usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies(
    dyn(capsule), data, len);
}
int dyn_solve(void * capsule) {return usv_dyn_nmpc_acados_solve(dyn(capsule));}
ocp_nlp_config * dyn_config(void * capsule)
{
  return usv_dyn_nmpc_acados_get_nlp_config(dyn(capsule));
}
ocp_nlp_dims * dyn_dims(void * capsule)
{
  return usv_dyn_nmpc_acados_get_nlp_dims(dyn(capsule));
}
ocp_nlp_in * dyn_in(void * capsule) {return usv_dyn_nmpc_acados_get_nlp_in(dyn(capsule));}
ocp_nlp_out * dyn_out(void * capsule)
{
  return usv_dyn_nmpc_acados_get_nlp_out(dyn(capsule));
}
ocp_nlp_solver * dyn_solver(void * capsule)
{
  return usv_dyn_nmpc_acados_get_nlp_solver(dyn(capsule));
}

// ── kinematic (usv_kin_mpc_*) ───────────────────────────────────────
usv_kin_mpc_solver_capsule * kin(void * capsule)
{
  return static_cast<usv_kin_mpc_solver_capsule *>(capsule);
}

void * kin_create_capsule()
{
  return usv_kin_mpc_acados_create_capsule();
}

int kin_create(void * capsule) {return usv_kin_mpc_acados_create(kin(capsule));}
int kin_free(void * capsule) {return usv_kin_mpc_acados_free(kin(capsule));}
int kin_free_capsule(void * capsule)
{
  return usv_kin_mpc_acados_free_capsule(kin(capsule));
}
int kin_reset(void * capsule, int reset_qp_mem)
{
  return usv_kin_mpc_acados_reset(kin(capsule), reset_qp_mem);
}
int kin_update_params(void * capsule, int stage, double * value, int np)
{
  return usv_kin_mpc_acados_update_params(kin(capsule), stage, value, np);
}
int kin_set_p_global(void * capsule, double * data, int len)
{
  return usv_kin_mpc_acados_set_p_global_and_precompute_dependencies(
    kin(capsule), data, len);
}
int kin_solve(void * capsule) {return usv_kin_mpc_acados_solve(kin(capsule));}
ocp_nlp_config * kin_config(void * capsule)
{
  return usv_kin_mpc_acados_get_nlp_config(kin(capsule));
}
ocp_nlp_dims * kin_dims(void * capsule)
{
  return usv_kin_mpc_acados_get_nlp_dims(kin(capsule));
}
ocp_nlp_in * kin_in(void * capsule) {return usv_kin_mpc_acados_get_nlp_in(kin(capsule));}
ocp_nlp_out * kin_out(void * capsule)
{
  return usv_kin_mpc_acados_get_nlp_out(kin(capsule));
}
ocp_nlp_solver * kin_solver(void * capsule)
{
  return usv_kin_mpc_acados_get_nlp_solver(kin(capsule));
}

const ModelDescriptor kKinematic = {
  Model::Kinematic, "kinematic", "usv_kin_mpc",
  USV_KIN_MPC_N, 5, 2, 7, 3, 8,
  USV_KIN_MPC_NY0, USV_KIN_MPC_NY, USV_KIN_MPC_NYN,
  USV_KIN_MPC_NH0, USV_KIN_MPC_NH, 5,
};

const ModelDescriptor kDynamic = {
  Model::Dynamic, "dynamic", "usv_dyn_nmpc",
  USV_DYN_NMPC_N, 6, 2, 8, 6, 30,
  USV_DYN_NMPC_NY0, USV_DYN_NMPC_NY, USV_DYN_NMPC_NYN,
  USV_DYN_NMPC_NH0, USV_DYN_NMPC_NH, 6,
};

const CapsuleOps kKinematicOps = {
  kin_create_capsule, kin_create, kin_free, kin_free_capsule, kin_reset,
  kin_update_params, kin_set_p_global, kin_solve,
  kin_config, kin_dims, kin_in, kin_out, kin_solver,
};

const CapsuleOps kDynamicOps = {
  dyn_create_capsule, dyn_create, dyn_free, dyn_free_capsule, dyn_reset,
  dyn_update_params, dyn_set_p_global, dyn_solve,
  dyn_config, dyn_dims, dyn_in, dyn_out, dyn_solver,
};

}  // namespace

const ModelDescriptor & descriptor_for(Model model)
{
  return (model == Model::Kinematic) ? kKinematic : kDynamic;
}

const CapsuleOps & ops_for(Model model)
{
  return (model == Model::Kinematic) ? kKinematicOps : kDynamicOps;
}

}  // namespace detail
}  // namespace usv_acados
