// SPDX-License-Identifier: MIT
// Explicit diagnostic scheduling control. Never authorizes command execution.
#pragma once
#include "owned_peer_c36_v1.hpp"
#include <optional>

namespace c38 {
using Json=p1_owned::Json;
inline constexpr int64_t gate_ttl_ns=3500000000LL;
inline constexpr size_t gate_request_max_bytes=8192;
struct Identity {
  std::string run_id,boot_id;
  int64_t driver_pid=0;
  uint64_t driver_start_ticks=0;
  std::string driver_tool_sha256,owner_manifest_sha256;
};
struct Command {
  std::string action,sha256;
  int64_t issued_ns=0,validated_ns=0;
  uint64_t seq=0;
};
enum class State { open,pause_validated,paused,resume_validated,resumed,timed_out };

inline void validate_mode_paths(const std::string &mode,const std::string &pause,
  const std::string &resume) {
  using c36_owned::detail::require;
  require(mode=="none"||mode=="applied-gate"||mode=="suppress-close-poll","C38_mode_domain");
  if(mode!="applied-gate") {
    require(pause.empty()&&resume.empty(),"C38_paths_require_applied_gate");return;
  }
  require(!pause.empty()&&!resume.empty()&&pause!=resume,"C38_distinct_explicit_paths");
  for(const auto &s:{pause,resume}) {
    require(s.size()<=4096&&s.find('\0')==std::string::npos,"C38_path_domain");
    const std::filesystem::path p(s);
    require(p.is_absolute()&&p==p.lexically_normal()&&!p.filename().empty()&&
      p.filename()!="."&&p.filename()!="..","C38_path_domain");
    const auto directory=p1_owned::open_directory(p.parent_path());
    struct stat st{};errno=0;const auto result=::fstatat(directory.get(),p.filename().c_str(),&st,AT_SYMLINK_NOFOLLOW);
    require(result==-1&&errno==ENOENT,"C38_request_path_must_be_fresh");
  }
}

class DiagnosticGate {
 public:
  explicit DiagnosticGate(Identity identity):identity_(std::move(identity)) {
    using c36_owned::detail::require;
    require(c36_owned::detail::visible_ascii(identity_.run_id,128)&&
      c36_owned::detail::visible_ascii(identity_.boot_id,64)&&identity_.driver_pid>0&&
      identity_.driver_pid<=INT_MAX&&identity_.driver_start_ticks>0&&
      p1_owned::sha256_shape(identity_.driver_tool_sha256)&&
      p1_owned::sha256_shape(identity_.owner_manifest_sha256),"C38_identity_domain");
  }
  Command validate_pause(const std::string &raw,int64_t now) {
    c36_owned::detail::require(state_==State::open,"C38_pause_state_order");
    auto command=parse(raw,"pause",1,now);
    pause_=command;state_=State::pause_validated;return command;
  }
  void pause_applied(int64_t completed_ns) {
    using c36_owned::detail::require;
    require(state_==State::pause_validated&&pause_.has_value(),"C38_pause_completion_order");
    require(completed_ns>=pause_->validated_ns&&completed_ns-pause_->issued_ns<=gate_ttl_ns,
      "C38_pause_completion_freshness");
    require(completed_ns<=INT64_MAX-gate_ttl_ns,"C38_pause_deadline_overflow");
    paused_ns_=completed_ns;deadline_ns_=completed_ns+gate_ttl_ns;state_=State::paused;
  }
  Command validate_resume(const std::string &raw,int64_t now) {
    using c36_owned::detail::require;
    require(state_==State::paused,"C38_resume_state_order");
    require(now>=paused_ns_&&now<deadline_ns_,"C38_resume_deadline");
    auto command=parse(raw,"resume",2,now);
    require(command.issued_ns>=paused_ns_&&command.issued_ns>=pause_->issued_ns,
      "C38_resume_before_actual_pause");
    resume_=command;state_=State::resume_validated;return command;
  }
  void resume_applied(int64_t completed_ns) {
    using c36_owned::detail::require;
    require(state_==State::resume_validated&&resume_.has_value(),"C38_resume_completion_order");
    require(completed_ns>=resume_->validated_ns&&completed_ns<deadline_ns_,
      "C38_resume_completion_deadline");
    state_=State::resumed;resumed_ns_=completed_ns;
  }
  bool expired(int64_t now) const {
    return (state_==State::paused||state_==State::resume_validated)&&now>=deadline_ns_;
  }
  void timeout_applied(int64_t completed_ns) {
    c36_owned::detail::require(expired(completed_ns),"C38_timeout_state_order");
    state_=State::timed_out;resumed_ns_=completed_ns;
  }
  void abandon_validation() {
    if(state_==State::pause_validated){pause_.reset();state_=State::open;}
    else if(state_==State::resume_validated){resume_.reset();state_=State::paused;}
  }
  State state()const{return state_;}
  int64_t paused_ns()const{return paused_ns_;}
  int64_t deadline_ns()const{return deadline_ns_;}
  const std::optional<Command>& pause_command()const{return pause_;}
  const std::optional<Command>& resume_command()const{return resume_;}
  Json evidence()const {
    return {{"schema","p1-C3.8-diagnostic-gate-state-v1"},{"state",state_name()},
      {"paused_ns",paused_ns_},{"deadline_ns",deadline_ns_},{"resumed_ns",resumed_ns_},
      {"ttl_ns",gate_ttl_ns},{"run_id",identity_.run_id},{"boot_id",identity_.boot_id},
      {"driver_pid",identity_.driver_pid},{"driver_start_ticks",identity_.driver_start_ticks},
      {"driver_tool_sha256",identity_.driver_tool_sha256},{"owner_manifest_sha256",identity_.owner_manifest_sha256},
      {"stage_qualified",false},{"execute_qualified",false},{"research_conclusion",false}};
  }
 private:
  Command parse(const std::string &raw,const std::string &action,uint64_t seq,int64_t now)const {
    using c36_owned::detail::require;
    require(!raw.empty()&&raw.size()<=gate_request_max_bytes,"C38_request_byte_bound");
    const auto j=c36_owned::detail::strict_json(raw);
    const std::set<std::string> keys={"schema","action","run_id","boot_id","driver_pid",
      "driver_start_ticks","driver_tool_sha256","owner_manifest_sha256","issued_ns","seq","stage_qualified"};
    require(j.size()==keys.size(),"C38_request_population");
    for(auto it=j.begin();it!=j.end();++it)require(keys.count(it.key())==1,"C38_unknown_request_key");
    for(const auto &binding:std::vector<std::pair<const char*,std::string>>{
      {"schema","p1-C3.8-applied-gate-v1"},{"action",action},{"run_id",identity_.run_id},
      {"boot_id",identity_.boot_id},{"driver_tool_sha256",identity_.driver_tool_sha256},
      {"owner_manifest_sha256",identity_.owner_manifest_sha256}})
      require(c36_owned::detail::string_field(j,binding.first,128)==binding.second,
        std::string("C38_request_identity_")+binding.first);
    require(c36_owned::detail::uint_field(j,"driver_pid",INT_MAX)==uint64_t(identity_.driver_pid)&&
      c36_owned::detail::uint_field(j,"driver_start_ticks",UINT64_MAX)==identity_.driver_start_ticks,
      "C38_request_driver_identity");
    require(c36_owned::detail::uint_field(j,"seq",2)==seq,"C38_request_sequence");
    c36_owned::detail::bool_field(j,"stage_qualified",false);
    const auto issued=c36_owned::detail::uint_field(j,"issued_ns",INT64_MAX);
    require(now>0&&issued>0&&issued<=uint64_t(now)&&now-static_cast<int64_t>(issued)<=gate_ttl_ns,
      "C38_request_freshness");
    return {action,p1_owned::sha256_bytes(raw),static_cast<int64_t>(issued),now,seq};
  }
  const char* state_name()const {
    switch(state_){case State::open:return "open";case State::pause_validated:return "pause_validated";
      case State::paused:return "paused";case State::resume_validated:return "resume_validated";
      case State::resumed:return "resumed";case State::timed_out:return "timed_out";}return "unknown";
  }
  Identity identity_;State state_=State::open;
  std::optional<Command> pause_,resume_;
  int64_t paused_ns_=0,deadline_ns_=0,resumed_ns_=0;
};
} // namespace c38
