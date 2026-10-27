// SPDX-License-Identifier: MIT
//
// model_transaction_v1.hpp — F6有限模型事务层 (batch 107 design).
//
// Drives the vendored acados C API directly (the production AcadosBackend
// keeps its capsule private and writes p_global only at construction — the
// F6 gap). The solve sequence follows the finite baseline's numeric setup
// (x0 pinning, runtime bounds, per-stage refs, warm/cold start,
// solve, extraction, shifted warm update) and adds the transaction layer:
//   - immutable registered versions {generation, p_global(30)}
//   - single-owner prepare/commit: UNCOMMITTED/READY -> PREPARED -> READY;
//     setter/reset failure leaves FAULTED. This is a serial contract, not a
//     proof of concurrent capsule atomicity or production fallback equivalence.
//   - version stamps on every solve: stale stamps are rejected without
//     touching the solver (call counters prove it)
//   - per-generation warm books: switching back restores that version's own
//     X/U/u_prev; a version with no book starts cold (capsule reset), which
//     is checked against a fresh installed-library instance on fixed inputs.
// Full production fallback, baked-dimension guards and mixed references remain
// integration obligations, not properties certified by this experimental layer.
#pragma once
#include <acados_c/ocp_nlp_interface.h>
#include "acados_solver_usv_dyn_nmpc.h"
#include "usv_mpc_cpp/utils.hpp"
#include <Eigen/Dense>
#include <array>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <stdexcept>
#include <thread>
#include <vector>
namespace f6 {
constexpr int NX = 8, NU = 2, NN = 20, NP = 6, NPG = 30;
struct Bounds { double T_min = -25.0, T_max = 25.0, dT_max = 80.0, dt = 0.2; };
struct Stats {
  uint64_t offered = 0, executed = 0;
  uint64_t rejected_stale_stamp = 0, rejected_preparing = 0, rejected_unknown_generation = 0;
  uint64_t rejected_immutable = 0, prepares_staged = 0, commits = 0;
  uint64_t setter_calls = 0, reset_calls = 0;
};
enum class TransactionState { UNCOMMITTED, READY, PREPARED, FAULTED };
// Optional finite-test adapter. Default functions invoke the real generated API;
// injecting a nonzero result tests wrapper policy, not a native internal fault.
struct TransactionApi {
  std::function<int(usv_dyn_nmpc_solver_capsule *, double *, int)> set_global =
      usv_dyn_nmpc_acados_set_p_global_and_precompute_dependencies;
  std::function<int(usv_dyn_nmpc_solver_capsule *, int)> reset = usv_dyn_nmpc_acados_reset;
};
class ModelTransactionSolver {
 public:
  struct SolveOut {
    bool executed = false;
    std::string reject;              // empty iff the solve ran
    int acados_status = 0;
    bool finite = true;
    Eigen::Vector2d u = Eigen::Vector2d::Zero();
    Eigen::MatrixXd X, U;            // 8x(N+1), 2xN
  };
  struct WarmBook {
    bool has = false;
    Eigen::MatrixXd X = Eigen::MatrixXd::Zero(NX, NN + 1);
    Eigen::MatrixXd U = Eigen::MatrixXd::Zero(2, NN);
    Eigen::Vector2d u_prev = Eigen::Vector2d::Zero();
  };
  explicit ModelTransactionSolver(const Bounds & b, TransactionApi api = {}) : api_(std::move(api)), b_(b) {
    if (!std::isfinite(b.T_min) || !std::isfinite(b.T_max) || !std::isfinite(b.dT_max)
        || !std::isfinite(b.dt) || b.T_min > b.T_max || b.dT_max < 0 || b.dt <= 0
        || !api_.set_global || !api_.reset) throw std::invalid_argument("invalid_bounds_or_api");
    capsule_ = usv_dyn_nmpc_acados_create_capsule();
    if (capsule_ == nullptr) throw std::runtime_error("capsule create failed");
    if (usv_dyn_nmpc_acados_create(capsule_) != 0) throw std::runtime_error("acados create failed");
    nlp_config_ = usv_dyn_nmpc_acados_get_nlp_config(capsule_);
    nlp_dims_ = usv_dyn_nmpc_acados_get_nlp_dims(capsule_);
    nlp_in_ = usv_dyn_nmpc_acados_get_nlp_in(capsule_);
    nlp_out_ = usv_dyn_nmpc_acados_get_nlp_out(capsule_);
  }
  ~ModelTransactionSolver() {
    if (capsule_) { usv_dyn_nmpc_acados_free(capsule_); usv_dyn_nmpc_acados_free_capsule(capsule_); }
  }
  ModelTransactionSolver(const ModelTransactionSolver &) = delete;
  ModelTransactionSolver & operator=(const ModelTransactionSolver &) = delete;
  // G3-style immutability: a generation registers once with fixed content.
  bool register_version(uint64_t generation, const std::array<double, NPG> & p_global) {
    if (!on_owner() || state_ == TransactionState::FAULTED || state_ == TransactionState::PREPARED) return false;
    if (!generation || !std::all_of(p_global.begin(), p_global.end(), [](double x) { return std::isfinite(x); })) return false;
    const auto it = versions_.find(generation);
    if (it != versions_.end()) {
      if (it->second != p_global) { ++stats_.rejected_immutable; return false; }
      return true;
    }
    versions_[generation] = p_global;
    warm_[generation] = WarmBook{};
    return true;
  }
  bool prepare(uint64_t generation) {
    if (!on_owner() || state_ == TransactionState::FAULTED || state_ == TransactionState::PREPARED
        || !generation || versions_.find(generation) == versions_.end()) return false;
    before_prepare_ = state_; state_ = TransactionState::PREPARED;
    staged_ = generation; ++stats_.prepares_staged; return true;
  }
  bool abort() {
    if (!on_owner() || state_ != TransactionState::PREPARED) return false;
    state_ = before_prepare_; staged_ = 0; return true;
  }
  // Only the constructing thread may invoke capsule operations. Publish the
  // committed identity after every required native step succeeds; an uncertain
  // capsule is terminal for this instance and cannot be "rolled back" by abort.
  bool commit() {
    if (!on_owner() || state_ != TransactionState::PREPARED) return false;
    const auto & pg = versions_.at(staged_);
    state_ = TransactionState::FAULTED; has_committed_ = false;
    try {
      ++stats_.setter_calls;
      if (api_.set_global(capsule_, const_cast<double *>(pg.data()), NPG) != 0) return false;
      if (!warm_.at(staged_).has) {
        ++stats_.reset_calls;
        if (api_.reset(capsule_, 1) != 0) return false;
      }
    } catch (...) { return false; }
    current_ = staged_; state_ = TransactionState::READY; has_committed_ = true; ++stats_.commits;
    return true;
  }
  SolveOut solve(uint64_t generation, const Eigen::Matrix<double, 6, 1> & x,
                 const Eigen::MatrixXd & ref) {
    SolveOut out;
    if (!on_owner()) { out.reject = "wrong_owner_thread"; return out; }
    ++stats_.offered;
    if (state_ == TransactionState::FAULTED) { out.reject = "transaction_faulted"; return out; }
    if (state_ == TransactionState::PREPARED) { ++stats_.rejected_preparing; out.reject = "solve_during_prepare"; return out; }
    if (versions_.find(generation) == versions_.end()) {
      ++stats_.rejected_unknown_generation; out.reject = "unknown_generation"; return out; }
    if (generation != current_) { ++stats_.rejected_stale_stamp; out.reject = "stale_stamp"; return out; }
    if (ref.rows() != NP || ref.cols() != NN + 1) { out.reject = "reference_shape"; return out; }
    if (!x.allFinite() || !ref.allFinite()) { out.reject = "nonfinite_state_or_reference"; return out; }
    WarmBook & w = warm_.at(generation);
    Eigen::Matrix<double, NX, 1> x0; x0 << x, w.u_prev;
    if (w.has) {
      const double shift = std::round((x(2) - w.X(2, 0)) / (2.0 * M_PI)) * (2.0 * M_PI);
      if (std::abs(shift) > 1e-3) w.X.row(2).array() += shift;
    }
    ocp_nlp_constraints_model_set(nlp_config_, nlp_dims_, nlp_in_, nlp_out_, 0, "lbx", x0.data());
    ocp_nlp_constraints_model_set(nlp_config_, nlp_dims_, nlp_in_, nlp_out_, 0, "ubx", x0.data());
    double lbu_v[2] = {b_.T_min, b_.T_min}, ubu_v[2] = {b_.T_max, b_.T_max};
    const double dT = b_.dT_max * b_.dt;
    double lh_v[2] = {-dT, -dT}, uh_v[2] = {dT, dT};
    for (int k = 0; k < NN; ++k) {
      ocp_nlp_constraints_model_set(nlp_config_, nlp_dims_, nlp_in_, nlp_out_, k, "lbu", lbu_v);
      ocp_nlp_constraints_model_set(nlp_config_, nlp_dims_, nlp_in_, nlp_out_, k, "ubu", ubu_v);
      ocp_nlp_constraints_model_set(nlp_config_, nlp_dims_, nlp_in_, nlp_out_, k, "lh", lh_v);
      ocp_nlp_constraints_model_set(nlp_config_, nlp_dims_, nlp_in_, nlp_out_, k, "uh", uh_v);
    }
    double ref_prev = x(2);
    for (int k = 0; k <= NN; ++k) {
      double ref_k[NP];
      for (int i = 0; i < 6; ++i) ref_k[i] = ref(i, k);
      ref_k[2] = ref_prev + usv_mpc::normalize_angle(ref_k[2] - ref_prev);
      ref_prev = ref_k[2];
      usv_dyn_nmpc_acados_update_params(capsule_, k, ref_k, NP);
    }
    if (w.has) {
      for (int k = 0; k <= NN; ++k)
        ocp_nlp_out_set(nlp_config_, nlp_dims_, nlp_out_, nlp_in_, k, "x", w.X.col(k).data());
      for (int k = 0; k < NN; ++k)
        ocp_nlp_out_set(nlp_config_, nlp_dims_, nlp_out_, nlp_in_, k, "u", w.U.col(k).data());
    } else {
      Eigen::Matrix<double, NX, 1> guess; guess << x, Eigen::Vector2d::Zero();
      Eigen::Vector2d uz = Eigen::Vector2d::Zero();
      for (int k = 0; k <= NN; ++k)
        ocp_nlp_out_set(nlp_config_, nlp_dims_, nlp_out_, nlp_in_, k, "x", guess.data());
      for (int k = 0; k < NN; ++k)
        ocp_nlp_out_set(nlp_config_, nlp_dims_, nlp_out_, nlp_in_, k, "u", uz.data());
    }
    out.acados_status = usv_dyn_nmpc_acados_solve(capsule_);
    out.executed = true; ++stats_.executed;
    if (out.acados_status != 0) { out.finite = false; return out; }
    double u0[NU]; ocp_nlp_out_get(nlp_config_, nlp_dims_, nlp_out_, 0, "u", u0);
    out.u << u0[0], u0[1];
    out.X = Eigen::MatrixXd(NX, NN + 1); out.U = Eigen::MatrixXd(2, NN);
    for (int k = 0; k <= NN; ++k) {
      double xk[NX]; ocp_nlp_out_get(nlp_config_, nlp_dims_, nlp_out_, k, "x", xk);
      out.X.col(k) = Eigen::Map<Eigen::Matrix<double, NX, 1>>(xk);
    }
    for (int k = 0; k < NN; ++k) {
      double uk[NU]; ocp_nlp_out_get(nlp_config_, nlp_dims_, nlp_out_, k, "u", uk);
      out.U.col(k) = Eigen::Map<Eigen::Vector2d>(uk);
    }
    if (!out.u.allFinite() || !out.X.allFinite() || !out.U.allFinite()) { out.finite = false; return out; }
    w.X.leftCols(NN) = out.X.rightCols(NN); w.X.col(NN) = out.X.col(NN);
    w.U.leftCols(NN - 1) = out.U.rightCols(NN - 1); w.U.col(NN - 1) = out.U.col(NN - 1);
    w.u_prev = out.u; w.has = true;
    return out;
  }
  uint64_t current_generation() const { require_owner(); return current_; }
  bool preparing() const { require_owner(); return state_ == TransactionState::PREPARED; }
  bool has_committed() const { require_owner(); return has_committed_; }
  TransactionState state() const { require_owner(); return state_; }
  const Stats & stats() const { require_owner(); return stats_; }
  const WarmBook & warm_of(uint64_t g) const { require_owner(); return warm_.at(g); }
 private:
  bool on_owner() const { return std::this_thread::get_id() == owner_; }
  void require_owner() const { if (!on_owner()) throw std::logic_error("wrong_owner_thread"); }
  // Destruction, like construction, belongs to owner_; moving this object is disabled.
  const std::thread::id owner_ = std::this_thread::get_id();
  TransactionApi api_;
  TransactionState state_ = TransactionState::UNCOMMITTED, before_prepare_ = TransactionState::UNCOMMITTED;
  bool has_committed_ = false;
  Bounds b_; Stats stats_;
  usv_dyn_nmpc_solver_capsule * capsule_ = nullptr;
  ocp_nlp_config * nlp_config_ = nullptr; ocp_nlp_dims * nlp_dims_ = nullptr;
  ocp_nlp_in * nlp_in_ = nullptr; ocp_nlp_out * nlp_out_ = nullptr;
  std::map<uint64_t, std::array<double, NPG>> versions_;
  std::map<uint64_t, WarmBook> warm_;
  uint64_t current_ = 0, staged_ = 0;
};
}  // namespace f6
