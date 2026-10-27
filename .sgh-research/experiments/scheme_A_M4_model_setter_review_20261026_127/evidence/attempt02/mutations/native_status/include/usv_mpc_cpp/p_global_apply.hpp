// SPDX-License-Identifier: MIT
#pragma once

#include <algorithm>
#include <cmath>
#include <utility>
#include "acados_solver_usv_dyn_nmpc.h"
#include "usv_mpc_cpp/p_global_pack.hpp"

namespace usv_mpc::p_global
{
static_assert(USV_DYN_NMPC_NP_GLOBAL == count, "generated p_global layout differs");
using Capsule = usv_dyn_nmpc_solver_capsule;
using NativeSetter = int (*)(Capsule *, double *, int);
enum class ApplyCode { applied, null_capsule, null_setter, nonfinite_parameters, native_error };
struct ApplyResult {
  ApplyCode code = ApplyCode::null_capsule;
  int native_status = 0;
  bool native_called = false;
  bool ok() const { return code == ApplyCode::applied; }
};

// The caller owns capsule lifetime and serializes all capsule access. Returning
// zero from the generated setter is only its reported result: its present C
// implementation does not propagate every internal precompute failure.
// This helper neither resets warm state nor commits a model generation.
template<class Setter>
ApplyResult apply_with(Capsule * capsule, const Packed & values, Setter && setter)
{
  if (!capsule) return {ApplyCode::null_capsule, 0, false};
  if (!std::all_of(values.begin(), values.end(), [](double x) { return std::isfinite(x); }))
    return {ApplyCode::nonfinite_parameters, 0, false};
  auto writable = values;
  const int status = std::forward<Setter>(setter)(capsule, writable.data(), int(count));
  return {ApplyCode::applied, status, true};
}

inline ApplyResult apply(Capsule * capsule, const Packed & values,
                        NativeSetter setter = usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies)
{
  if (!setter) return {ApplyCode::null_setter, 0, false};
  return apply_with(capsule, values, setter);
}
}  // namespace usv_mpc::p_global
