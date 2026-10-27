// SPDX-License-Identifier: MIT
#pragma once

#include <array>
#include <cstddef>
#include "usv_mpc_cpp/mpc_solver.hpp"

namespace usv_mpc::p_global
{
inline constexpr std::size_t count = 30;
inline constexpr std::size_t hydro_count = 19;
inline constexpr std::size_t q_offset = 19, r_offset = 25, rd_offset = 27, qf_offset = 29;
using Packed = std::array<double, count>;

// Packing is a value-preserving layout operation. Validation belongs to the
// caller/checked application boundary; this function does not change inputs.
inline Packed pack(const MpcParams & p)
{
  Packed pg{};
  const auto & h = p.hydro;
  pg[0] = h.mass; pg[1] = h.Iz; pg[2] = h.xg; pg[3] = h.d_thruster;
  pg[4] = h.Xu_dot; pg[5] = h.Yv_dot; pg[6] = h.Yr_dot; pg[7] = h.Nv_dot;
  pg[8] = h.Nr_dot; pg[9] = h.Xu; pg[10] = h.Yv; pg[11] = h.Yr;
  pg[12] = h.Nv; pg[13] = h.Nr; pg[14] = h.Xuu; pg[15] = h.Yvv;
  pg[16] = h.Yrr; pg[17] = h.Nvv; pg[18] = h.Nrr;
  for (std::size_t i = 0; i < 6; ++i) pg[q_offset + i] = p.Q_diag(i);
  for (std::size_t i = 0; i < 2; ++i) {
    pg[r_offset + i] = p.R_diag(i);
    pg[rd_offset + i] = p.Rd_diag(i);
  }
  pg[qf_offset] = p.Qf_scale;
  return pg;
}
}  // namespace usv_mpc::p_global
