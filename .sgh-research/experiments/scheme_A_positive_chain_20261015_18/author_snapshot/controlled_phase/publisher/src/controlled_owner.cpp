// SPDX-License-Identifier: MIT
#include "usv_mpc_cpp/mpc_node.hpp"
namespace usv_mpc {
void MpcControllerNode::controlled_log_(nlohmann::json row) {
 std::lock_guard<std::mutex> lock(controlled_source_mutex_);
 row["source_written_ns"]=research_steady_ns();row["stage_qualified"]=false;row["execute_qualified"]=false;
 controlled_source_<<row.dump()<<'\n';controlled_source_.flush();
 p1_owned::require(bool(controlled_source_),"controlled owner Source write failed");
}
void MpcControllerNode::controlled_init_() {
 controlled_mode_=get_parameter("controlled_phase_mode").as_string();
 controlled_observer_manifest_=get_parameter("controlled_observer_manifest_file").as_string();
 controlled_observer_binary_=get_parameter("controlled_observer_binary_sha256").as_string();
 controlled_observer_source_=get_parameter("controlled_observer_source_bundle_sha256").as_string();
 controlled_observer_run_=get_parameter("controlled_observer_run_id").as_string();
 p1_owned::require(controlled::mode_valid(controlled_mode_)&&get_parameter("research_baseline_id").as_string()==controlled::baseline,"controlled owner mode or baseline");
 p1_owned::require(std::filesystem::path(controlled_observer_manifest_).is_absolute()&&p1_owned::sha256_shape(controlled_observer_binary_)&&p1_owned::sha256_shape(controlled_observer_source_)&&!controlled_observer_run_.empty(),"controlled observer expected code/run pins");
 controlled_source_.open(get_parameter("research_output_dir").as_string()+"/controlled_source.jsonl",std::ios::out|std::ios::app);
 p1_owned::require(bool(controlled_source_),"controlled owner Source unavailable");
 controlled_phase_pub_=create_publisher<std_msgs::msg::String>("/p1/controlled_owner_phase",rclcpp::QoS(100).reliable());
 rclcpp::SubscriptionOptions options;options.callback_group=control_cb_group_;
 controlled_decision_sub_=create_subscription<usv_research_interfaces::msg::ExecutionDecision>("/p1/execution_decision",rclcpp::QoS(100).reliable(),
  [this](usv_research_interfaces::msg::ExecutionDecision::ConstSharedPtr m,const rclcpp::MessageInfo &info){controlled_decision_(*m,info);},options);
 controlled_job_sub_=create_subscription<usv_research_interfaces::msg::SolveJob>("/p1/solve_job",rclcpp::QoS(100).reliable(),
  [this](usv_research_interfaces::msg::SolveJob::ConstSharedPtr m,const rclcpp::MessageInfo &info){controlled_job_(*m,info);},options);
 research_->set_applied_publish_observer([this](const ResearchApplied &m,int64_t begin,int64_t end){controlled_applied_emitted_(m,begin,end);});
 controlled_log_({{"type","controlled_owner_created"},{"mode",controlled_mode_},{"baseline_id",controlled::baseline},
  {"autonomous_solver_invoked",false},{"pulse_offset_ns",controlled::pulse_offset_ns},{"pulse_n",controlled::pulse_n},
  {"phase_publication_policy","actual successful physical calls then actual Applied DDS publish completion then phase publish"}});
}
bool MpcControllerNode::controlled_bind_observer_() {
 if(controlled_decision_peer_)return controlled_decision_peer_->alive()&&controlled_job_peer_->alive();
 if(!std::filesystem::exists(controlled_observer_manifest_))return false;
 controlled::ExpectedPeer expected{controlled_observer_manifest_,"observer",controlled_observer_run_,get_parameter("p1_owned_contract_sha256").as_string(),controlled_observer_binary_,controlled_observer_source_,"/p1/execution_decision","usv_research_interfaces/msg/ExecutionDecision"};
 auto decision=std::make_unique<controlled::ExactPeer>(expected);
 expected.topic="/p1/solve_job";expected.type="usv_research_interfaces/msg/SolveJob";
 auto job=std::make_unique<controlled::ExactPeer>(expected);
 p1_owned::require(decision->manifest()==job->manifest(),"controlled Observer peers differ");
 controlled_log_({{"type","controlled_observer_peer_bound"},{"decision",decision->evidence()},{"job",job->evidence()}});
 controlled_decision_peer_=std::move(decision);controlled_job_peer_=std::move(job);return true;
}
void MpcControllerNode::controlled_decision_(const usv_research_interfaces::msg::ExecutionDecision &d,const rclcpp::MessageInfo &info) {
 const auto entry=research_steady_ns();auto raw=controlled::receipt(d,info,++controlled_decision_receipts_,entry,"/p1/execution_decision","usv_research_interfaces/msg/ExecutionDecision");
 std::string reason=controlled_decision_peer_?controlled_decision_peer_->reason(info):"peer_not_bound";
 if(reason.empty()&&!controlled::decision_domain(d,controlled_observer_run_,get_parameter("p1_owned_contract_sha256").as_string(),entry))reason="decision_domain";
 if(reason.empty()&&d.sequence<=controlled_decision_sequence_)reason="decision_duplicate_or_reordered";
 if(reason.empty()&&controlled_decisions_.size()>=16)reason="decision_queue_bound";
 controlled_log_({{"type","controlled_decision_receipt"},{"raw_input",raw},{"reason",reason},{"admitted",reason.empty()},{"decision_sequence",d.sequence},{"tick",d.tick},{"job_id",d.job_id},{"accepted",d.candidate_accepted},{"final_n",d.final_n}});
 if(!reason.empty())return;
 controlled_decision_sequence_=d.sequence;controlled_decisions_.push_back(d);
}
void MpcControllerNode::controlled_job_(const usv_research_interfaces::msg::SolveJob &j,const rclcpp::MessageInfo &info) {
 const auto entry=research_steady_ns();auto raw=controlled::receipt(j,info,++controlled_job_receipts_,entry,"/p1/solve_job","usv_research_interfaces/msg/SolveJob");
 std::string reason=controlled_job_peer_?controlled_job_peer_->reason(info):"peer_not_bound";
 if(reason.empty()&&!controlled::job_domain(j,controlled_observer_run_,get_parameter("p1_owned_contract_sha256").as_string(),entry))reason="job_domain_or_late_for_pulse";
 const bool selected=reason.empty()&&controlled_mode_=="B"&&!controlled_pulse_job_;
 if(selected)controlled_pulse_job_=j;
 controlled_log_({{"type","controlled_job_receipt"},{"raw_input",raw},{"reason",reason},{"pulse_selected",selected},{"job_id",j.job_id},{"target_tick",j.target_tick},{"freeze_ns",j.freeze_steady_ns},{"origin_ns",j.tick_origin_steady_ns},{"pulse_due_ns",j.tick_origin_steady_ns+controlled::pulse_offset_ns},{"target_ns",j.target_steady_ns}});
}
void MpcControllerNode::controlled_cycle_() {
 if(!p1_poll_release_()||!controlled_bind_observer_()||shutting_down_)return;
 {std::lock_guard<std::mutex> lock(controlled_pending_mutex_);if(!controlled_pending_.empty())return;}
 if(!controlled_initial_) {
  std::lock_guard<std::mutex> output(control_output_mutex_);research_control_source_="controlled_initial_zero";active_research_cycle_=0;
  publish_dynamic_output_(Eigen::Vector2d::Zero());controlled_initial_=true;return;
 }
 const auto now=research_steady_ns();
 if(controlled_mode_=="B"&&controlled_pulse_job_&&!controlled_pulse_fired_&&now>=controlled_pulse_job_->tick_origin_steady_ns+controlled::pulse_offset_ns) {
  p1_owned::require(now<controlled_pulse_job_->target_steady_ns,"controlled B pulse missed target window");
  std::lock_guard<std::mutex> output(control_output_mutex_);research_control_source_="controlled_B_pulse";active_research_cycle_=0;
  const auto actual=publish_dynamic_output_(Eigen::Vector2d::Constant(controlled::pulse_n));controlled_held_={actual[0],actual[1]};controlled_pulse_fired_=true;
  controlled_log_({{"type","controlled_B_pulse_physical_return"},{"job_id",controlled_pulse_job_->job_id},{"target_tick",controlled_pulse_job_->target_tick},
   {"origin_ns",controlled_pulse_job_->tick_origin_steady_ns},{"freeze_ns",controlled_pulse_job_->freeze_steady_ns},{"due_ns",controlled_pulse_job_->tick_origin_steady_ns+controlled::pulse_offset_ns},{"physical_return_ns",research_steady_ns()},{"applied_sequence",latest_applied_sequence_.load()},{"actual_command_n",{controlled_held_[0],controlled_held_[1]}}});return;
 }
 if(controlled_decisions_.empty())return;
 auto d=controlled_decisions_.front();controlled_decisions_.pop_front();
 p1_owned::require(research_steady_ns()<d.tick_planned_ns+controlled::period_ns,"controlled queued Decision expired before physical publication");
 Eigen::Vector2d command=Eigen::Vector2d::Zero();
 if(controlled_mode_=="C")command<<d.final_n[0],d.final_n[1];
 if(controlled_mode_=="B"&&controlled_pulse_fired_&&!controlled_pulse_restored_) {
  if(d.tick>=controlled_pulse_job_->target_tick)controlled_pulse_restored_=true;
  else command<<controlled_held_[0],controlled_held_[1];
 }
 {std::lock_guard<std::mutex> lock(controlled_pending_mutex_);controlled_pending_.emplace(d.sequence,d);}
 std::lock_guard<std::mutex> output(control_output_mutex_);
 if(shutting_down_)return;
 research_control_source_=controlled_mode_=="A2"?"controlled_A2_decision":controlled_mode_=="B"?"controlled_B_decision":"controlled_C_decision";active_research_cycle_=d.sequence;
 const auto actual=publish_dynamic_output_(command);controlled_held_={actual[0],actual[1]};active_research_cycle_=0;
 controlled_log_({{"type","controlled_decision_physical_return"},{"decision_sequence",d.sequence},{"tick",d.tick},{"requested_n",{command[0],command[1]}},{"actual_n",{controlled_held_[0],controlled_held_[1]}},{"physical_return_ns",research_steady_ns()},{"applied_sequence",latest_applied_sequence_.load()},{"pulse_restored",controlled_pulse_restored_}});
}
void MpcControllerNode::controlled_applied_emitted_(const ResearchApplied &a,int64_t begin,int64_t end) {
 ++controlled_applied_emitted_count_;
 rclcpp::Serialization<ResearchApplied> codec;rclcpp::SerializedMessage bytes;codec.serialize_message(&a,&bytes);auto &raw=bytes.get_rcl_serialized_message();
 controlled_log_({{"type","controlled_Applied_emitted"},{"applied_sequence",a.sequence},{"cycle_sequence",a.cycle_sequence},{"control_source",a.control_source},{"final_n",a.final_n},
  {"applied_publish_start_ns",begin},{"applied_publish_end_ns",end},{"left_start_ns",a.left_publish_start_steady_ns},{"left_end_ns",a.left_publish_end_steady_ns},{"right_start_ns",a.right_publish_start_steady_ns},{"right_end_ns",a.right_publish_end_steady_ns},
  {"cdr_bytes",raw.buffer_length},{"cdr_sha256",p1_owned::sha256_bytes(std::string(reinterpret_cast<char*>(raw.buffer),raw.buffer_length))},{"cdr_hex",p1_owned::hex(raw.buffer,raw.buffer_length)}});
 if(a.control_source!="controlled_"+controlled_mode_+"_decision")return;
 usv_research_interfaces::msg::ExecutionDecision d;
 {std::lock_guard<std::mutex> lock(controlled_pending_mutex_);auto it=controlled_pending_.find(a.cycle_sequence);p1_owned::require(it!=controlled_pending_.end(),"controlled actual Applied missing Decision correlation");d=it->second;}
 if(research_steady_ns()>=d.tick_planned_ns+150000000){controlled_log_({{"type","controlled_phase_refused"},{"reason","late_for_unchanged_150ms_freeze_budget"},{"decision_sequence",d.sequence},{"applied_sequence",a.sequence},{"applied_publish_end_ns",end}});throw std::runtime_error("controlled phase late for unchanged freeze budget");}
 auto phase=controlled::phase(research_->startup_identity(),get_parameter("p1_owned_contract_sha256").as_string(),d,a,research_steady_ns());
 p1_owned::require(end<=phase.at("emitted_ns").get<int64_t>(),"controlled phase before actual Applied completion");
 std_msgs::msg::String wire;wire.data=phase.dump();const auto phase_begin=research_steady_ns();controlled_phase_pub_->publish(wire);const auto phase_end=research_steady_ns();++controlled_phase_emitted_count_;
 controlled_log_({{"type","controlled_phase_emitted"},{"phase",phase},{"applied_publish_start_ns",begin},{"applied_publish_end_ns",end},{"phase_publish_start_ns",phase_begin},{"phase_publish_end_ns",phase_end},{"wire_sha256",p1_owned::sha256_bytes(wire.data)}});
 {std::lock_guard<std::mutex> lock(controlled_pending_mutex_);controlled_pending_.erase(a.cycle_sequence);}
}
} // namespace usv_mpc
