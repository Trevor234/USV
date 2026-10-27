 void poll_commands(){
  if(!t2_armed_||!start_)return;
  std::error_code ec;std::set<std::filesystem::path> entries;
  for(const auto &entry:std::filesystem::directory_iterator(t2_command_dir_,ec))entries.insert(entry.path());
  for(const auto &path:entries){
    const auto name=path.filename().string();
    if(name.empty()||name[0]=='.')continue;  // atomic-publish temp sidecars are not commands
    if(t2_seen_commands_.count(name))continue;
    t2_seen_commands_.insert(name);
    const auto command=c36_owned::detail::strict_json(p1_owned::read_bounded(path));
    const std::set<std::string> keys={"schema","run_id","contract_sha256","action_id","sequence","trigger"};
    p1_owned::require(command.size()==keys.size(),"T2 command exact fields");
    p1_owned::require(command.at("schema")=="M4-t2-action-command-v1"&&command.at("run_id")==run_
      &&command.at("contract_sha256")==contract_,"T2 command identity binding");
    p1_owned::require(command.at("sequence").is_number_integer()
      &&command.at("sequence").get<int64_t>()==int64_t(t2_executed_.size())+1,"T2 commands execute in declared table order");
    const auto action_id=command.at("action_id").get<std::string>();
    const p1_owned::Json *entry=nullptr;
    for(const auto &row:t2_table_.at("actions"))if(row.at("id")==action_id)entry=&row;
    p1_owned::require(entry!=nullptr,"T2 command action is not in the frozen table");
    // R0: the executor independently enforces table order and uniqueness, mirroring
    // validate_command: the commanded id must be the NEXT table entry, and no
    // action may execute twice regardless of which file carried it.
    p1_owned::require(t2_executed_.size()<t2_table_.at("actions").size(),"T2 command beyond the frozen table");
    p1_owned::require(t2_table_.at("actions").at(t2_executed_.size()).at("id")==action_id,"T2 command must be the next frozen table action");
    for(const auto &done:t2_executed_)p1_owned::require(done!=action_id,"T2 duplicate action execution");
    p1_owned::require(command.at("trigger").is_object()&&command.at("trigger").contains("phase")
      &&command.at("trigger").contains("job")&&command.at("trigger").contains("observed_ns")
      &&command.at("trigger").contains("source_role")
      &&command.at("trigger").at("phase")==entry->at("trigger").at("phase"),"T2 command trigger binds the frozen phase");
    execute_action(*entry,command.at("trigger"),p1_owned::file_sha256(path));
  }
 }
