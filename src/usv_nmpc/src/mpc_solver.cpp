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
 * @brief 求解器工厂: 仅使用 acados 后端。
 *
 * codegen 逻辑见 scripts/regenerate_acados_codegen.py。
 */

#include "usv_nmpc/mpc_solver.hpp"

#include <memory>

#include "usv_nmpc/acados_backend.hpp"

namespace usv_mpc {

std::unique_ptr<DynamicMpc> make_dynamic_mpc(const MpcParams& params) {
  // 仅使用 acados (codegen 已 vendored 并静态链接进本包);
  // 构造失败 (如 N/dt 与 codegen 不一致或权重非法) 直接抛异常中止启动。
  return std::make_unique<AcadosBackend>(params);
}

}  // namespace usv_mpc
