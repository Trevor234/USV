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
 * @file kinematic_mpc_solver.cpp
 * @brief 运动学 MPC 工厂实现。
 *
 * 对应 Python: 无 (Python 的后端选择在 mpc_node._init_mpc_solvers)。
 * A 的 C++ 版只有 CasADi 后端; acados 运动学 codegen 留 TODO。
 */

#include "usv_mpc_cpp/kinematic_mpc_solver.hpp"

#include <cstdio>
#include <stdexcept>

#ifdef USV_MPC_HAS_CASADI
#include "usv_mpc_cpp/casadi_kinematic_backend.hpp"
#endif

namespace usv_mpc
{

std::unique_ptr<KinematicMpc> make_kinematic_mpc(const KinematicMpcParams & params)
{
  // A 的 C++ 版只有 CasADi 后端。acados 运动学 codegen 签名 (usv_kin_*) 与
  // 方案 B 的 usv_dyn_nmpc_* 不同, 需单独 codegen, 工作量大, 留 TODO
  // (见 docs/acados_migration.md)。
#ifdef USV_MPC_HAS_CASADI
  return std::make_unique<CasadiKinematicBackend>(params);
#else
  std::fprintf(stderr,
               "[usv_mpc_kinematic_cpp] CasADi C++ 后端未编译进本构建 "
               "(pip wheel 旧 C++ ABI), 方案 A 请用 Python usv_mpc\n");
  throw std::runtime_error("make_kinematic_mpc: no solver backend available");
#endif
}

}  // namespace usv_mpc
