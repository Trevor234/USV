// SPDX-License-Identifier: MIT
#pragma once
#include "m4_owned_runtime.hpp"
namespace m4_owned {
// Independent process authentication only. This object supplies no Reader GID,
// storage readiness, or authority to publish. Full ready_manifest() is separate.
class RecorderProcessPin {
 public:
  RecorderProcessPin(Json pin,const std::string &run,const std::string &contract):pin_(std::move(pin)){
    const std::set<std::string> keys={"schema","role","run_id","boot_id","contract_sha256","pid","process_start_ticks","exe",
      "binary_sha256","source_bundle_sha256","argv","pgid","sid","manifest_path","topics_sha256","process_only","recording_ready"};
    p1_owned::require(pin_.is_object()&&pin_.size()==keys.size(),"Recorder process pin exact population");
    for(const auto &k:keys)p1_owned::require(pin_.contains(k),"Recorder process pin missing field");
    p1_owned::require(pin_.at("schema")=="M4-recorder-owned-process-only/v1"&&pin_.at("role")=="recorder"&&pin_.at("run_id")==run&&
      pin_.at("boot_id")==p1_owned::boot_id()&&pin_.at("contract_sha256")==contract,"Recorder process identity");
    c36_owned::detail::bool_field(pin_,"process_only",true);c36_owned::detail::bool_field(pin_,"recording_ready",false);
    p1_owned::require(pin_.at("binary_sha256")=="d1b91109081c84d4427510d752e926249a0779c44e84b36509bbfa1dac800002"&&
      pin_.at("source_bundle_sha256")=="61da30907164a3e55ba3aa41e5609d9b80562982133c52cc6135d8283bb99c08","Recorder known unchanged executable/source");
    for(const auto &k:{"contract_sha256","binary_sha256","source_bundle_sha256","topics_sha256"})
      p1_owned::require(pin_.at(k).is_string()&&p1_owned::sha256_shape(pin_.at(k)),"Recorder process SHA fields");
    path_=c36_owned::detail::string_field(pin_,"manifest_path",4096);
    p1_owned::require(std::filesystem::path(path_).is_absolute(),"Recorder future manifest absolute");
    pins_.pid=c36_owned::detail::uint_field(pin_,"pid",INT_MAX);pins_.process_start_ticks=c36_owned::detail::uint_field(pin_,"process_start_ticks",INT64_MAX);
    pins_.boot_id=pin_.at("boot_id");pins_.exe=c36_owned::detail::string_field(pin_,"exe",4096);pins_.binary_sha256=pin_.at("binary_sha256");
    p1_owned::require(pins_.pid>0&&pins_.process_start_ticks>0&&pin_.at("pgid")==pins_.pid&&pin_.at("sid")==pins_.pid,"Recorder independent owned group");
    const auto &argv=pin_.at("argv");p1_owned::require(argv.is_array()&&argv.size()>=3&&argv.size()<=64,"Recorder actual bounded argv");
    std::map<std::string,std::string> flags;
    for(size_t i=1;i<argv.size();i+=2){
      p1_owned::require(i+1<argv.size()&&argv[i].is_string()&&argv[i+1].is_string(),"Recorder actual paired argv");
      const auto key=argv[i].get<std::string>(),value=argv[i+1].get<std::string>();
      p1_owned::require(value.size()<=4096&&flags.emplace(key,value).second,"Recorder argv duplicate/bound");
    }
    p1_owned::require(flags.at("--run-id")==run&&flags.at("--contract-sha256")==contract&&flags.at("--topics-sha256")==pin_.at("topics_sha256")&&
      flags.at("--manifest")==path_&&flags.at("--storage-id")=="sqlite3"&&flags.at("--prepare-budget-ms")=="10000","Recorder CLI contract/topics/output");
    process_=c36_owned::detail::authenticate_process(pins_,pin_);
    pidfd_.reset(int(::syscall(SYS_pidfd_open,pins_.pid,0)));p1_owned::require(pidfd_.get()>=0&&alive(),"Recorder process pidfd");
    const auto after=c36_owned::detail::authenticate_process(pins_,pin_);
    p1_owned::require(after.argv==process_.argv&&after.start==process_.start,"Recorder process stable across authentication");
  }
  bool alive()const{pollfd f{pidfd_.get(),POLLIN,0};return ::poll(&f,1,0)==0;}
  const std::string &path()const{return path_;}
  Json process_evidence()const{return {{"process_only",true},{"recording_ready",false},{"pin",pin_},{"pidfd_alive",alive()},{"post_pin_exec_continuity","unknown"}};}
  Json ready_manifest_pin()const{
    p1_owned::require(alive(),"Recorder exited before complete manifest");
    const auto raw=c36_owned::detail::read_manifest(path_);const auto m=c36_owned::detail::strict_json(raw);
    for(const auto &key:{"pid","process_start_ticks","exe","binary_sha256","source_bundle_sha256","argv","pgid","sid"})
      p1_owned::require(m.at(key)==pin_.at(key),"Recorder full manifest independent process pin mismatch");
    p1_owned::require(m.at("role")=="recorder"&&m.at("run_id")==pin_.at("run_id")&&m.at("boot_id")==pin_.at("boot_id")&&
      m.at("contract_sha256")==pin_.at("contract_sha256")&&m.at("topic_declaration_sha256")==pin_.at("topics_sha256"),"Recorder full ready identity/topics");
    c36_owned::detail::bool_field(m,"true_recorder_storage",true);c36_owned::detail::bool_field(m,"discovery_stopped",true);
    Json result={{"manifest_path",path_},{"manifest_sha256",p1_owned::sha256_bytes(raw)}};
    for(const auto &key:{"pid","process_start_ticks","exe","binary_sha256","source_bundle_sha256","effective_parameters_sha256"})result[key]=m.at(key);
    return result;
  }
 private:
  Json pin_;std::string path_;c36_owned::PeerPins pins_;c36_owned::detail::Process process_;c36_owned::detail::Fd pidfd_;
};
} // namespace m4_owned
