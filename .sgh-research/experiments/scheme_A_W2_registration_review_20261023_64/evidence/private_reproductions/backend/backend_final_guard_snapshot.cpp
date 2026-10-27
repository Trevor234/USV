// SPDX-License-Identifier: MIT
//
// Backend-boundary tests that actually hit the registered boundary.
//
// The previous suite's "success" test bound the gate to Job 2 but only ran
// Job 1, so it exercised the non-matching path and would still pass with the
// whole wiring block deleted. These tests drive the *target* Job and ordinal
// through owned_cold::Backend::solve_owned, and the runner mutates the wiring
// block away to prove they notice.
#include <cstdint>
#include <cstring>
#include <memory>
#include <string>
#include <vector>


#include <nlohmann/json.hpp>

#include "owned_cold_backend.hpp"
#include "w2_native_boundary.hpp"

namespace {

using Json = nlohmann::json;
using w2_gate::Gate;
using w2_gate::Identity;
using w2_wire::Boundary;
using w2_wire::BoundaryConfig;
using w2_wire::Disposition;

constexpr int64_t kTargetJob = 1;   // the cold-start Job: the only one armed
constexpr uint32_t kTargetOrdinal = 1;
constexpr int64_t kStartNs = 1000000000;

/// Delivers one frame when asked, and can advance a shared clock as it does.
class ControlledReader final : public w2_gate::Reader {
 public:
  ControlledReader(Identity id, int64_t * clock, int64_t advance_ns)
  : id_(id), clock_(clock), advance_(advance_ns) {}

  long read_some(uint8_t * buf, size_t n, int64_t, int64_t * elapsed) override {
    if (delivered_) {
      if (elapsed) *elapsed = advance_;
      if (clock_) *clock_ += advance_;
      return -1;
    }
    delivered_ = true;
    uint8_t frame[w2_gate::kFrameBytes];
    w2_gate::encode_release(frame, id_);
    const size_t take = std::min(n, w2_gate::kFrameBytes);
    std::memcpy(buf, frame, take);
    // Advancing here is what makes the release "arrive late": the gate sees a
    // frame, but the clock has crossed the Job deadline while it waited.
    if (clock_) *clock_ += advance_;
    if (elapsed) *elapsed = advance_;
    return long(take);
  }

 private:
  Identity id_;
  int64_t * clock_;
  int64_t advance_;
  bool delivered_ = false;
};

/// A Job that satisfies the cold-start policy so the target Job really arms.
Json target_job(int64_t job_id, int64_t deadline_ns) {
  Json j;
  j["schema"] = "p1-solve-job-v1";
  j["run_id"] = "w2_backend_test";
  j["boot_id"] = "boot";
  j["contract_hash"] = std::string(64, 'a');
  j["nominal_hash"] = std::string(64, 'b');
  j["worker_instance"] = "instance";
  j["config_generation"] = 1;
  j["model_generation"] = 1;
  j["task_generation"] = 1;
  j["schedule_generation"] = 1;
  j["clock_epoch"] = 0;
  j["job_id"] = job_id;
  j["N"] = 20;
  j["dt"] = 0.2;
  j["deadline_ns"] = deadline_ns;
  j["target_state"] = std::vector<double>{0, 0, 0, 0, 0, 0};
  j["frozen_state"] = std::vector<double>{0, 0, 0, 0, 0, 0};
  j["anchor_n"] = std::vector<double>{0, 0};
  j["anchor_known"] = std::vector<bool>{true, true};
  j["reset_warmstart"] = false;
  std::vector<double> ref(126);
  for (int k = 0; k <= 20; ++k) {
    ref[6 * k + 0] = 0.05 * 0.2 * k;
    ref[6 * k + 3] = 0.05;
  }
  j["reference"] = ref;
  return j;
}

usv_mpc::MpcParams params() {
  usv_mpc::MpcParams p;
  p.dt = 0.2;
  p.N = 20;
  return p;
}

Json binding() {
  return Json{{"run_id", "w2_backend_test"}, {"boot_id", "boot"},
              {"contract_hash", std::string(64, 'a')},
              {"nominal_hash", std::string(64, 'b')},
              {"worker_instance", "instance"}};
}

/// One armed boundary plus the clock it shares with the backend.
struct Armed {
  Armed(int64_t deadline_ns, int64_t advance_ns, int64_t budget_ns = 1000000000)
  : reader(identity(), &clock, advance_ns), gate(&reader, identity(), budget_ns) {
    cfg.job_id = kTargetJob;
    cfg.ordinal = kTargetOrdinal;
    cfg.job_deadline_ns = deadline_ns;
    cfg.wait_budget_ns = budget_ns;
    boundary = Boundary(&gate, cfg, [this] { return clock; });
    boundary.set_clock([this] { return clock; });
    boundary.set_current_job(kTargetJob);
    backend = std::make_unique<owned_cold::Backend>(
        params(), binding(), true, [this] { return clock; });
    backend->attach_boundary(&boundary, [] { return false; });
  }

  static Identity identity() {
    return Identity{1, uint64_t(kTargetJob), kTargetOrdinal, 0x77};
  }

  int64_t clock = kStartNs;
  ControlledReader reader;
  Gate gate;
  BoundaryConfig cfg;
  Boundary boundary;
  std::unique_ptr<owned_cold::Backend> backend;
};

}  // namespace


#include <iostream>
int main() {
  Json rows=Json::array();
  {
    const auto deadline=kStartNs+1000000000;
    Armed a(deadline,1000000);
    a.backend=std::make_unique<owned_cold::Backend>(params(),binding(),true,[&]{
      if(a.boundary.record().disposition==Disposition::kAllowed)a.clock=deadline+1;
      return a.clock;
    });
    a.backend->attach_boundary(&a.boundary,[]{return false;});
    a.backend->set_applied_control(Eigen::Vector2d::Zero());
    std::string caught;
    try{a.backend->solve_owned(target_job(kTargetJob,deadline));}catch(const std::exception&e){caught=e.what();}
    const auto policy=a.backend->last_policy_event();
    rows.push_back({{"case","deadline_after_verified_allowed_release"},{"exception",caught},{"clock_ns",a.clock},{"record",w2_boundary_json(a.boundary.record())},{"policy",policy},{"record_matches_actual_refusal",a.boundary.record().disposition==Disposition::kExpired}});
  }
  {
    const auto deadline=kStartNs+1000000000;
    Armed a(deadline,1000000);
    a.backend->attach_boundary(&a.boundary,[&]{return a.boundary.record().disposition==Disposition::kAllowed;});
    a.backend->set_applied_control(Eigen::Vector2d::Zero());
    std::string caught;
    try{a.backend->solve_owned(target_job(kTargetJob,deadline));}catch(const std::exception&e){caught=e.what();}
    rows.push_back({{"case","stop_after_verified_allowed_release"},{"exception",caught},{"record",w2_boundary_json(a.boundary.record())},{"policy",a.backend->last_policy_event()},{"record_matches_actual_refusal",a.boundary.record().disposition==Disposition::kStopped}});
  }
  {
    const auto deadline=kStartNs+150000000;
    Armed a(deadline,200000000);
    a.backend->set_applied_control(Eigen::Vector2d::Zero());
    std::string caught;
    try{a.backend->solve_owned(target_job(kTargetJob,deadline));}catch(const std::exception&e){caught=e.what();}
    rows.push_back({{"case","registered_long_wait_positive_control"},{"exception",caught},{"record",w2_boundary_json(a.boundary.record())},{"policy",a.backend->last_policy_event()},{"record_matches_actual_refusal",a.boundary.record().disposition==Disposition::kExpired}});
  }
  std::cout<<rows.dump(2)<<std::endl;
  return 0;
}
