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

#pragma once

#include <cstdio>
#include <functional>
#include <utility>
#include <type_traits>
#include <condition_variable>
#include <deque>
#include <fstream>
#include <map>
#include <mutex>
#include <string>
#include <thread>
#include <variant>
#include <filesystem>
#include <chrono>
#include <rclcpp/rclcpp.hpp>
#include <nlohmann/json.hpp>
#include "p1_owned_identity.hpp"
#include <usv_research_interfaces/msg/state_snapshot.hpp>
#include <usv_research_interfaces/msg/applied_control.hpp>
#include <usv_research_interfaces/msg/cycle_timing.hpp>
#include <usv_research_interfaces/msg/reference_prediction.hpp>

namespace usv_mpc
{
using ResearchState = usv_research_interfaces::msg::StateSnapshot;
using ResearchApplied = usv_research_interfaces::msg::AppliedControl;
using ResearchCycle = usv_research_interfaces::msg::CycleTiming;
using ResearchReference = usv_research_interfaces::msg::ReferencePrediction;

inline int64_t research_steady_ns()
{
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
}

// Bounded observation queue. Only this worker publishes research topics and
// writes summary files; it never publishes physical actuator commands.
class ResearchLogger {
public:
  ResearchLogger(
    rclcpp::Node & node, const std::string & output,
    const std::string & run, const std::string & baseline, const std::string & config,
    bool reference_enabled = false, const std::string & nominal_hash = std::string())
  : output_(output), run_(run), baseline_(baseline), config_(config)
  {
    // P0_REFERENCE_PREDICTION_V1
    reference_enabled_ = reference_enabled; nominal_hash_ = nominal_hash;
    if (reference_enabled_ && (nominal_hash_.size() != 64 ||
      nominal_hash_.find_first_not_of("0123456789abcdef") != std::string::npos))
    {throw std::runtime_error("reference telemetry requires nominal SHA256");}
    context_ = node.get_node_base_interface()->get_context();
    if (run.empty() || baseline.empty() || output.empty() || config.size() != 64) {
      throw std::runtime_error("research identity/config/output required");
    }
    if (!std::filesystem::create_directory(output_)) {
      throw std::runtime_error("research output directory already exists or parent missing");
    }
    std::ifstream boot("/proc/sys/kernel/random/boot_id");
    std::getline(boot, domain_);
    domain_ += ":steady_clock";
    producer_ = run_ + ":" + std::to_string(research_steady_ns());
    state_pub_ = node.create_publisher<ResearchState>("/research/state_snapshot", 100);
    applied_pub_ = node.create_publisher<ResearchApplied>("/research/control/applied", 100);
    cycle_pub_ = node.create_publisher<ResearchCycle>("/research/cycle_timing", 100);
    streams_["state"] = {}; streams_["applied"] = {}; streams_["cycle"] = {};
    if (reference_enabled_) {
      reference_pub_ = node.create_publisher<ResearchReference>("/research/reference_prediction",
          100);
      streams_["reference_prediction"] = {};
    }
    worker_ = std::thread([this]() {
          try {work_();} catch (const std::exception & error) {
            fprintf(stderr, "research summary write failed: %s\n", error.what());
          }
    });
  }
  ~ResearchLogger() {stop(false);}
  // Immutable startup view uses the exact producer already assigned by this
  // logger. No producer identity is reconstructed by the external driver.
  nlohmann::json startup_identity() const
  {
    return {{"run_id", run_}, {"producer_instance_id", producer_},
      {"baseline_id", baseline_}, {"config_hash", config_},
      {"steady_clock_domain", domain_}, {"nominal_config_hash", nominal_hash_}};
  }
  // These GIDs are read from this logger's actual created publisher handles.
  // External graph discovery is a separate cross-check, never the author.
  nlohmann::json owned_publisher_endpoints() const
  {
    auto endpoints = nlohmann::json::array();
    endpoints.push_back(p1_owned::publisher_endpoint(*state_pub_,
      "usv_research_interfaces/msg/StateSnapshot"));
    endpoints.push_back(p1_owned::publisher_endpoint(*applied_pub_,
      "usv_research_interfaces/msg/AppliedControl"));
    endpoints.push_back(p1_owned::publisher_endpoint(*cycle_pub_,
      "usv_research_interfaces/msg/CycleTiming"));
    if (reference_pub_) {
      endpoints.push_back(p1_owned::publisher_endpoint(*reference_pub_,
        "usv_research_interfaces/msg/ReferencePrediction"));
    }
    return endpoints;
  }
  // New diagnostic owner callback runs only after actual Applied DDS publish returns.
  // Enqueue completion never triggers it. Install once before arming.
  void set_applied_publish_observer(std::function<void(const ResearchApplied &,int64_t,int64_t)> observer) {
    std::lock_guard<std::mutex> lock(mutex_);
    if(armed_||closing_||applied_observer_)throw std::runtime_error("Applied observer must be fixed before arm");
    applied_observer_=std::move(observer);
  }
  template<class T> void identity(T & msg) const
  {
    msg.schema_version = "p0-contract-v1";
    msg.run_id = run_; msg.producer_instance_id = producer_;
    msg.baseline_id = baseline_; msg.config_hash = config_;
    msg.steady_clock_domain = domain_;
  }
  void identity(ResearchReference & msg) const
  {
    identity<ResearchReference>(msg);
    msg.schema_version = "p0-reference-prediction-v1";
  }
  template<class T> uint64_t enqueue(T msg, const std::string & stream)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!armed_ || closing_) {return 0;}
    auto & s = streams_.at(stream);
    msg.sequence = ++s.generated;
    identity(msg);
    if (s.first == 0) {s.first = msg.sequence;}
    s.last = msg.sequence;
    if (queue_.size() >= 1024) {++s.dropped; return msg.sequence;}
    queue_.emplace_back(stream, std::move(msg));
    cv_.notify_one();
    return s.last;
  }
  void arm()
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!closing_ && !armed_) {armed_ = true; start_ns_ = research_steady_ns();}
  }
  void cycle_started()
  {
    std::lock_guard<std::mutex> lock(mutex_); ++cycle_invocations_started_;
  }
  void interrupted_cycle(uint64_t sequence)
  {
    std::lock_guard<std::mutex> lock(mutex_); interrupted_cycle_sequence_ = sequence;
  }
  bool armed() const
  {
    std::lock_guard<std::mutex> lock(mutex_); return armed_ && !closing_;
  }
  void stop(bool normal)
  {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      if (closing_) {return;}
      closing_ = true; normal_ = normal; end_ns_ = research_steady_ns();
    }
    cv_.notify_one();
    if (worker_.joinable()) {worker_.join();}
  }

private:
  struct Count {uint64_t generated = 0, emitted = 0, dropped = 0, first = 0, last = 0;};
  using Event = std::variant<ResearchState, ResearchApplied, ResearchCycle, ResearchReference>;
  void work_()
  {
    for (;; ) {
      std::pair<std::string, Event> item;
      {
        std::unique_lock<std::mutex> lock(mutex_);
        cv_.wait(lock, [this]() {return closing_ || !queue_.empty();});
        if (queue_.empty() && closing_) {break;}
        item = std::move(queue_.front()); queue_.pop_front();
      }
      try {
        if (!context_->is_valid()) {throw std::runtime_error("research context invalid");}
        int64_t applied_start=0,applied_end=0;
        std::visit([this,&applied_start,&applied_end](const auto & msg) {
            using T = std::decay_t<decltype(msg)>;
            if constexpr (std::is_same_v<T, ResearchState>) {state_pub_->publish(msg);}
            if constexpr (std::is_same_v<T, ResearchApplied>) {applied_start=research_steady_ns();applied_pub_->publish(msg);applied_end=research_steady_ns();}
            if constexpr (std::is_same_v<T, ResearchCycle>) {cycle_pub_->publish(msg);}
            if constexpr (std::is_same_v<T, ResearchReference>) {reference_pub_->publish(msg);}
        }, item.second);
        {std::lock_guard<std::mutex> lock(mutex_); ++streams_.at(item.first).emitted;}
        // Auxiliary phase failure is separately counted; an already emitted Applied
        // is never retrospectively relabeled as a failed DDS publication.
        if(applied_observer_&&std::holds_alternative<ResearchApplied>(item.second)) {
          try{applied_observer_(std::get<ResearchApplied>(item.second),applied_start,applied_end);}
          catch(const std::exception &e){fprintf(stderr,"controlled Applied observer failed: %s\n",e.what());std::lock_guard<std::mutex> lock(mutex_);++observer_errors_;}
        }
      } catch (const std::exception &) {
        std::lock_guard<std::mutex> lock(mutex_); ++publish_errors_;
      }
    }
    nlohmann::json j;
    j["schema_version"] = "p0-contract-v1"; j["run_id"] = run_;
    j["producer_instance_id"] = producer_; j["baseline_id"] = baseline_;
    j["config_hash"] = config_; j["steady_clock_domain"] = domain_;
    j["start_steady_ns"] = start_ns_; j["end_steady_ns"] = end_ns_;
    j["normal_end"] = normal_ && armed_ && publish_errors_ == 0 && observer_errors_ == 0 && interrupted_cycle_sequence_ == 0;
    j["auxiliary_applied_observer_errors"] = observer_errors_;
    j["flushed"] = queue_.empty() && publish_errors_ == 0;
    j["publish_errors"] = publish_errors_;
    j["cycle_invocations_started"] = cycle_invocations_started_;
    j["interrupted_cycle_sequence"] = interrupted_cycle_sequence_;
    uint64_t dropped = 0;
    for (const auto & [name, s] : streams_) {
      j["streams"][name] = {{"generated", s.generated}, {"emitted", s.emitted},
        {"dropped", s.dropped}, {"first_sequence", s.first}, {"last_sequence", s.last}};
      dropped += s.dropped;
    }
    j["queue_dropped_total"] = dropped;
    j["reference_prediction"] = {{"enabled", reference_enabled_},
      {"schema_version", "p0-reference-prediction-v1"}, {"nominal_config_hash", nominal_hash_},
      {"prediction_policy", "accepted_post_deadline_only"}, {"record_policy", "solve_invoked_only"},
      {"matrix_layout", "k_major"}, {"queue_capacity_events", 1024}};
    std::ofstream file(output_ + "/session_summary.json.tmp"); file << j.dump(2); file.close();
    std::filesystem::rename(output_ + "/session_summary.json.tmp",
        output_ + "/session_summary.json");
  }
  std::string output_, run_, baseline_, config_, producer_, domain_;
  mutable std::mutex mutex_;
  std::condition_variable cv_;
  std::deque<std::pair<std::string, Event>> queue_;
  std::map<std::string, Count> streams_;
  std::thread worker_;
  bool armed_ = false, closing_ = false, normal_ = false;
  int64_t start_ns_ = 0, end_ns_ = 0;
  std::function<void(const ResearchApplied &,int64_t,int64_t)> applied_observer_;
  uint64_t observer_errors_=0;
  uint64_t publish_errors_ = 0;
  uint64_t cycle_invocations_started_ = 0, interrupted_cycle_sequence_ = 0;
  rclcpp::Context::SharedPtr context_;
  rclcpp::Publisher<ResearchState>::SharedPtr state_pub_;
  rclcpp::Publisher<ResearchApplied>::SharedPtr applied_pub_;
  rclcpp::Publisher<ResearchCycle>::SharedPtr cycle_pub_;
  rclcpp::Publisher<ResearchReference>::SharedPtr reference_pub_;
  bool reference_enabled_ = false;
  std::string nominal_hash_;
};
}  // namespace usv_mpc
