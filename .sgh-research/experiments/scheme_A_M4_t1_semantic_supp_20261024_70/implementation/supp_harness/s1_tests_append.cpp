
// == S1 supplementary evidence (batch 70) ==================================
// Scope: isolated boolean rejection gates, native-shape constructive evidence,
// the REAL prepare_loop submission path with its shutdown/version guards, the
// in-flight reference-change window, and a real activation after ordinary new
// odom. The tested code remains the unmodified 67th-batch Regulator source
// compiled in through P1_REGULATOR_SOURCE; no admission rule is copied here.
TEST_F(T1Wiring,CandidateSuccessFalseAloneRejected){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  auto failed=C33MatrixAccess::candidate_msg(j,1.0,true,true,false);  // ONLY success=false
  failed.job.job_id=2;
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,failed.job,failed,reason));
  EXPECT_EQ(reason,"solver_failed");
  EXPECT_TRUE(C33MatrixAccess::candidate_present(*reg));  // the accepted registration is untouched
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,1));
}
TEST_F(T1Wiring,CandidateSolverNotInvokedAloneRejected){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  auto not_invoked=C33MatrixAccess::candidate_msg(j,1.0,true,false,true);  // ONLY solver_invoked=false
  not_invoked.job.job_id=2;
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,not_invoked.job,not_invoked,reason));
  EXPECT_EQ(reason,"solver_failed");
  EXPECT_TRUE(C33MatrixAccess::candidate_present(*reg));
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,1));
}
TEST_F(T1Wiring,NativePredictionShapeFixedByConstruction){
  // Native result dimensions are fixed by the wire contract itself: 126 for
  // x_prediction (21 columns x 6 states), 40 for u_prediction (20 x 2), 2 for
  // first_control, 126 for the Job reference block. A wrong-dimension native
  // result cannot be represented on the wire; this is constructive evidence,
  // not a claim that a bad-shape native experiment ran. The Job horizon/dt
  // branch stays a separate metadata gate.
  static_assert(sizeof(p1::Candidate{}.x_prediction)==126*sizeof(double),"x_prediction fixed at 126");
  static_assert(sizeof(p1::Candidate{}.u_prediction)==40*sizeof(double),"u_prediction fixed at 40");
  static_assert(sizeof(p1::Candidate{}.first_control)==2*sizeof(double),"first_control fixed at 2");
  static_assert(sizeof(p1::Job{}.reference)==126*sizeof(double),"job reference fixed at 126");
  const auto j=C33MatrixAccess::job_msg(*reg,{});
  const auto c=C33MatrixAccess::candidate_msg(j);
  EXPECT_EQ(c.x_prediction.size(),size_t(126));
  EXPECT_EQ(c.u_prediction.size(),size_t(40));
  EXPECT_EQ(c.first_control.size(),size_t(2));
  auto meta=j;meta.job_id=2;meta.horizon_steps=10;  // Job metadata, NOT native result shape
  std::string reason;
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,meta,C33MatrixAccess::candidate_msg(meta),reason));
  EXPECT_EQ(reason,"shape_or_time_contract");
}
TEST_F(T1Wiring,RealPrepareLoopSubmitsJob){
  C33MatrixAccess::settle_static_reference(*reg);
  const auto prep=C33MatrixAccess::make_preparation(*reg,C33MatrixAccess::current_tick(*reg));
  C33MatrixAccess::enqueue_preparation(*reg,prep);
  C33MatrixAccess::start_prepare_thread(*reg);
  const bool submitted=C33MatrixAccess::wait_jobs_submitted(*reg);
  C33MatrixAccess::stop_prepare_thread(*reg);
  EXPECT_TRUE(submitted);                                     // real jobs_ push through the submit commit
  C33MatrixAccess::flush_pad(*reg);
  const auto ev=wait_event(sink_file,"job",1);
  ASSERT_FALSE(ev.is_null());
  const auto &job=ev.at("job");
  EXPECT_GT(job.at("job_id").get<uint64_t>(),uint64_t(0));
  EXPECT_EQ(job.at("N").get<uint32_t>(),uint32_t(20));
  EXPECT_DOUBLE_EQ(job.at("dt").get<double>(),.2);
  EXPECT_GT(job.at("deadline_ns").get<int64_t>(),ev.at("submit_commit_ns").get<int64_t>());
  const auto pub=C33MatrixAccess::read_event_once(sink_file,"job_publish_result");
  ASSERT_FALSE(pub.is_null());
  EXPECT_TRUE(pub.at("success").get<bool>());
  const auto epoch=C33MatrixAccess::read_event_once(sink_file,"reference_epoch_committed");
  ASSERT_FALSE(epoch.is_null());
  // The REAL echo written by prepare_loop admits a result WITHOUT seed_echo.
  const p1::Job real=C33MatrixAccess::last_submitted_job(*reg);
  EXPECT_EQ(real.job_id,job.at("job_id").get<uint64_t>());
  std::string reason;
  EXPECT_TRUE(C33MatrixAccess::register_real_result(*reg,sink_file,real,reason))<<"reason="<<reason;
  EXPECT_EQ(reason,"");
  EXPECT_TRUE(C33MatrixAccess::candidate_present(*reg));
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,1));
}
TEST_F(T1Wiring,RealSubmitBlockedByShutdownBeforeSubmit){
  C33MatrixAccess::settle_static_reference(*reg);
  const auto prep=C33MatrixAccess::make_preparation(*reg,C33MatrixAccess::current_tick(*reg));
  C33MatrixAccess::enqueue_preparation(*reg,prep);
  C33MatrixAccess::stop(*reg);                                // shutdown lands before the real submit guards
  C33MatrixAccess::start_prepare_thread(*reg);
  const bool consumed=C33MatrixAccess::wait_pending_consumed(*reg);
  std::this_thread::sleep_for(std::chrono::milliseconds(30));
  C33MatrixAccess::stop_prepare_thread(*reg);
  EXPECT_TRUE(consumed);
  C33MatrixAccess::flush_pad(*reg);
  const auto ev=wait_event(sink_file,"job_not_submitted",1);
  ASSERT_FALSE(ev.is_null());
  EXPECT_EQ(ev.at("reason").get<std::string>(),"shutdown_before_submit");
  EXPECT_FALSE(C33MatrixAccess::jobs_submitted(*reg));        // no echo, no submit
  EXPECT_TRUE(C33MatrixAccess::read_event_once(sink_file,"job").is_null());
}
TEST_F(T1Wiring,RealSubmitBlockedByVersionChangeBeforeSubmit){
  C33MatrixAccess::settle_static_reference(*reg);
  const auto prep=C33MatrixAccess::make_preparation(*reg,C33MatrixAccess::current_tick(*reg));
  C33MatrixAccess::path(*reg,C33MatrixAccess::path_msg(5));   // reference change inside the in-flight window
  C33MatrixAccess::profile(*reg,C33MatrixAccess::profile_msg(5));  // complete the new pair for the positive control
  const uint64_t new_task=C33MatrixAccess::current_task(*reg);
  EXPECT_GT(new_task,prep.s.version.task);                    // the preparation is now stale
  C33MatrixAccess::enqueue_preparation(*reg,prep);
  C33MatrixAccess::start_prepare_thread(*reg);
  const bool consumed=C33MatrixAccess::wait_pending_consumed(*reg);
  std::this_thread::sleep_for(std::chrono::milliseconds(30));
  C33MatrixAccess::stop_prepare_thread(*reg);
  EXPECT_TRUE(consumed);
  C33MatrixAccess::flush_pad(*reg);
  const auto ev=wait_event(sink_file,"job_not_submitted",1);
  ASSERT_FALSE(ev.is_null());
  const auto blocked=ev.at("reason").get<std::string>();
  EXPECT_TRUE(blocked=="version_changed_before_submit"||
              blocked=="version_changed_at_submit_completion")<<"blocked="<<blocked;
  EXPECT_FALSE(C33MatrixAccess::jobs_submitted(*reg));
  // The stale in-flight result cannot register afterwards either (distinct
  // job_id: a rejected submit leaves its seeded echo in jobs_).
  auto stale=C33MatrixAccess::job_msg(*reg,{.id=2,.task=prep.s.version.task});
  std::string reason;
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,stale,C33MatrixAccess::candidate_msg(stale),reason));
  EXPECT_EQ(reason,"version_mismatch");
  // Positive control: the new task generation registers and really activates.
  auto fresh=C33MatrixAccess::job_msg(*reg,{.id=3,.task=new_task});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,fresh,C33MatrixAccess::candidate_msg(fresh),reason))<<reason;
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,1));
  std::this_thread::sleep_for(std::chrono::milliseconds(210));
  const auto result=C33MatrixAccess::activate_taken(*reg);
  EXPECT_TRUE(result.accepted)<<result.reason;
  EXPECT_EQ(result.control_source,"candidate");
}
TEST_F(T1Wiring,ReferenceOrdinaryNewOdomActivation){
  std::string reason;auto j=C33MatrixAccess::job_msg(*reg,{});
  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,j,C33MatrixAccess::candidate_msg(j),reason))<<reason;
  const uint64_t task0=C33MatrixAccess::current_task(*reg);
  C33MatrixAccess::odom(*reg,SIM+5000000);                    // ordinary fresh odom
  EXPECT_EQ(C33MatrixAccess::current_task(*reg),task0);       // no version change
  std::this_thread::sleep_for(std::chrono::milliseconds(210));
  const auto result=C33MatrixAccess::activate_taken(*reg);    // REAL activation attempt
  EXPECT_TRUE(result.accepted)<<result.reason;
  EXPECT_EQ(result.control_source,"candidate");
  // Version rejection dimensions per the frozen contract: model is isolated in
  // candidate_identity_shape.08, clock epoch in the state_clock cases; the
  // remaining task/config/schedule dimensions reject explicitly here.
  const std::array<C33MatrixAccess::JobSeed,3> dims{
    C33MatrixAccess::JobSeed{.id=2,.task=task0+1},
    C33MatrixAccess::JobSeed{.id=3,.config=2},
    C33MatrixAccess::JobSeed{.id=4,.schedule=2}};
  for(const auto &seed:dims){
    auto stale=C33MatrixAccess::job_msg(*reg,seed);
    EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,stale,C33MatrixAccess::candidate_msg(stale),reason));
    EXPECT_EQ(reason,"version_mismatch");
  }
}
