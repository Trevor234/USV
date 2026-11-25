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
 * @file mpc_solver.cpp
 * @brief 求解器工厂:优先 acados,失败回退 CasADi。
 *
 * codegen 在共用包 usv_acados
 * (usv_acados/scripts/regenerate_acados_codegen.py --model dynamic)。
 */

#include "usv_nmpc/mpc_solver.hpp"

#include <cstdio>
#include <stdexcept>

#include "usv_nmpc/acados_backend.hpp"
#ifdef USV_MPC_HAS_CASADI
#include "usv_nmpc/casadi_backend.hpp"
#endif

namespace usv_mpc
{

#ifdef USV_MPC_HAS_CASADI
std::unique_ptr<DynamicMpc> make_casadi_dynamic_mpc(const MpcParams & params)
{
  return std::make_unique<CasadiBackend>(params);
}
#endif

std::unique_ptr<DynamicMpc> make_dynamic_mpc(const MpcParams & params)
{
  // 1. 尝试 acados (codegen 已 vendored 并静态链接进本包)
  try {
    return std::make_unique<AcadosBackend>(params);
  } catch (const std::exception & e) {
    std::fprintf(stderr,
                 "[usv_nmpc] acados 后端构造失败,回退 CasADi: %s\n",
                 e.what());
  }

#ifdef USV_MPC_HAS_CASADI
  // 2. 回退 CasADi (仅当构建时 ABI 探针通过, 见 CMakeLists)
  return make_casadi_dynamic_mpc(params);
#else
  std::fprintf(stderr,
               "[usv_nmpc] CasADi fallback 未编译进本构建, 无可用求解器后端\n");
  throw std::runtime_error("make_dynamic_mpc: no solver backend available");
#endif
}

}  // namespace usv_mpc
