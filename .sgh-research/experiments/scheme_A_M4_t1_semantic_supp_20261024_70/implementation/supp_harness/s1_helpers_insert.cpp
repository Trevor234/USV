 // ---- batch 70 (S1): real prepare_loop driving; friend routing only ----
 static nav_msgs::msg::Path static_path_msg(int64_t stamp_ns=100000000000LL){
  // The exact static 201-point straight at .05 m/s that task_time_reference
  // propose() admits: point x must equal speed*(.2*k) bit-for-bit.
  nav_msgs::msg::Path m;m.header.stamp.sec=stamp_ns/1000000000;m.header.stamp.nanosec=stamp_ns%1000000000;
  m.header.frame_id="map";
  for(int k=0;k<201;++k){geometry_msgs::msg::PoseStamped p;
    p.pose.position.x=.05*(.2*k);p.pose.orientation.w=1;m.poses.push_back(p);}
  return m;
 }
 static void settle_static_reference(Regulator &r){
  // Established through the real path()/profile() callbacks so the
  // path/profile fingerprints are real 64-char digests, as propose() requires.
  path(r,static_path_msg());
  profile(r,profile_msg(201));
 }
 static Regulator::Preparation make_preparation(Regulator &r,uint64_t tick,int64_t origin_delta_ns=-100000000){
  const auto now=p1::monotonic_ns();
  r.capability_lease_->renew(now);  // keep the lease fresh across the real submit guards
  return Regulator::Preparation{r.snapshot_locked(now),tick,now+origin_delta_ns};
 }
 static void enqueue_preparation(Regulator &r,const Regulator::Preparation &p){
  std::lock_guard<std::mutex> l(r.prep_mutex_);
  r.pending_=p;r.prep_cv_.notify_one();
 }
 static void ensure_job_publisher(Regulator &r){
  // The ShadowTestTag constructor creates no job publisher; the real submit
  // tail publishes on it, so the component gets a test publisher here (same
  // disclosure as the test decision publisher; no control DataWriter).
  if(!r.job_pub_)r.job_pub_=r.create_publisher<p1::Job>("/p1_test/solve_job",rclcpp::QoS(1).reliable());
 }
 static void start_prepare_thread(Regulator &r){
  ensure_job_publisher(r);
  r.prep_=std::thread(&Regulator::prepare_loop,&r);
 }
 static bool jobs_submitted(Regulator &r){
  std::lock_guard<std::mutex> l(r.mutex_);return !r.jobs_.empty();
 }
 static p1::Job last_submitted_job(Regulator &r){
  std::lock_guard<std::mutex> l(r.mutex_);return r.jobs_.back();
 }
 static bool pending_empty(Regulator &r){
  std::lock_guard<std::mutex> l(r.prep_mutex_);return !r.pending_.has_value();
 }
 static void stop_prepare_thread(Regulator &r){
  {std::lock_guard<std::mutex> l(r.prep_mutex_);r.prep_stop_=true;}
  r.prep_cv_.notify_all();if(r.prep_.joinable())r.prep_.join();
 }
 static bool wait_jobs_submitted(Regulator &r,int timeout_ms=300){
  for(int i=0;i<timeout_ms;++i){if(jobs_submitted(r))return true;
   std::this_thread::sleep_for(std::chrono::milliseconds(1));}
  return false;
 }
 static bool wait_pending_consumed(Regulator &r,int timeout_ms=300){
  for(int i=0;i<timeout_ms;++i){if(pending_empty(r))return true;
   std::this_thread::sleep_for(std::chrono::milliseconds(1));}
  return false;
 }
 static p1::Json read_event_once(const std::string &file,const std::string &type){
  std::ifstream in(file);p1::Json last;std::string line;
  while(std::getline(in,line)){
   try{auto row=p1::Json::parse(line);
    if(row.value("type",std::string{})==type)last=std::move(row);
   }catch(const p1::Json::parse_error&){}}
  return last;
 }
 static bool register_real_result(Regulator&r,const std::string &sink,const p1::Job &j,std::string &reason){
  // Result submission against the REAL prepare_loop echo: no manual seed_echo.
  const auto invocation_ns=p1::monotonic_ns();
  r.candidate(candidate_msg(j));flush_pad(r);
  auto ev=wait_current_registration(sink,p1::job_json(j),invocation_ns);
  if(ev.is_null()){reason="<no_current_registration>";return false;}
  reason=ev.at("reason").get<std::string>();return ev.at("accepted_registration").get<bool>();
 }
