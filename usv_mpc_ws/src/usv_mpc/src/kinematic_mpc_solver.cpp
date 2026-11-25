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
 * @brief 运动学 MPC 工厂实现: 仅使用 acados 后端。
 */

#include "usv_mpc/kinematic_mpc_solver.hpp"

#include "usv_mpc/acados_kinematic_backend.hpp"

namespace usv_mpc
{

std::unique_ptr<KinematicMpc> make_kinematic_mpc(const KinematicMpcParams & params)
{
  // usv_mpc 专一使用 acados 后端 (无 CasADi/IPOPT 回退路径)。
  return std::make_unique<AcadosKinematicBackend>(params);
}

}  // namespace usv_mpc
