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
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.

// 方案 A 的模型常量。这些数值必须与 acados 生成码烘焙的尺寸一致；引擎在构造时
// 逐项核对，任何一处不一致都抛 std::runtime_error 而不是静默继续。
#pragma once

namespace usv_nmpc
{

/// dynamic 生成的全局参数维数 (p_global)。
inline constexpr int kDynamicPGlobal = 30;
/// kinematic 生成的全局参数维数。
inline constexpr int kKinematicPGlobal = 8;

/// dynamic 生成的状态/控制维数。
inline constexpr int kDynamicNPhys = 6;
inline constexpr int kDynamicNu = 2;
/// dynamic 生成码烘焙的时域长度与步长 (模型切换必须逐位匹配)。
inline constexpr int kDynamicN = 20;
inline constexpr double kDynamicDt = 0.2;
/// 生成模型每步的控制幅值与变化率上界 (用于约束一致性核对)。
inline constexpr double kDynamicTMin = -25.0;
inline constexpr double kDynamicTMax = 25.0;
inline constexpr double kDynamicDTMax = 80.0;

/// p_global 的 30 维布局 (与生成脚本 regenerate_acados_codegen.py 一致)：
/// 19 水动力 + 6 Q + 2 R + 2 Rd + 1 Qf_scale。
inline constexpr int kPGN_Hydro = 19;
inline constexpr int kPGN_Q = 6;
inline constexpr int kPGN_R = 2;
inline constexpr int kPGN_Rd = 2;
inline constexpr int kPGN_Qf = 1;
inline constexpr int kPGOFF_Q = kPGN_Hydro;
inline constexpr int kPGOFF_R = kPGOFF_Q + kPGN_Q;
inline constexpr int kPGOFF_Rd = kPGOFF_R + kPGN_R;
inline constexpr int kPGOFF_Qf = kPGOFF_Rd + kPGN_Rd;

/// 把水动力结构体写进 p_global 前 19 维。与 acados_backend.cpp 的 fill_hydro
/// 逐项一致；两处都在时以本头为准（生成脚本的输出顺序冻结在测试里）。
template<class Hydro>
inline void fill_hydro_p_global(double * pg, const Hydro & h)
{
  pg[0] = h.mass;     pg[1] = h.Iz;       pg[2] = h.xg;     pg[3] = h.d_thruster;
  pg[4] = h.Xu_dot;   pg[5] = h.Yv_dot;   pg[6] = h.Yr_dot; pg[7] = h.Nv_dot;
  pg[8] = h.Nr_dot;   pg[9] = h.Xu;       pg[10] = h.Yv;    pg[11] = h.Yr;
  pg[12] = h.Nv;      pg[13] = h.Nr;      pg[14] = h.Xuu;   pg[15] = h.Yvv;
  pg[16] = h.Yrr;     pg[17] = h.Nvv;     pg[18] = h.Nrr;
}

}  // namespace usv_nmpc
