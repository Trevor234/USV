// Appended to the submitted Backend test source in a private build only.
namespace {
bool review_force_native_error = false;
unsigned review_real_c_calls = 0;
bool *review_stop_during_preparation = nullptr;
int64_t *review_clock_during_preparation = nullptr;
int64_t review_clock_after_preparation = 0;
}

extern "C" int __real_usv_dyn_nmpc_acados_solve(usv_dyn_nmpc_solver_capsule *);
extern "C" int __wrap_usv_dyn_nmpc_acados_solve(usv_dyn_nmpc_solver_capsule *capsule) {
  ++review_real_c_calls;
  const int status = __real_usv_dyn_nmpc_acados_solve(capsule);
  return review_force_native_error ? 55 : status;
}
extern "C" int __real_usv_dyn_nmpc_acados_update_params(
    usv_dyn_nmpc_solver_capsule *, int, double *, int);
extern "C" int __wrap_usv_dyn_nmpc_acados_update_params(
    usv_dyn_nmpc_solver_capsule *capsule, int stage, double *values, int count) {
  const int status = __real_usv_dyn_nmpc_acados_update_params(capsule, stage, values, count);
  if (review_stop_during_preparation) *review_stop_during_preparation = true;
  if (review_clock_during_preparation)
    *review_clock_during_preparation = review_clock_after_preparation;
  return status;
}

TEST(W2Review, SuccessPolicySnapshotMatchesTheBoundary) {
  Armed a(kStartNs + 1000000000, 1000000);
  a.backend->set_applied_control(Eigen::Vector2d::Zero());
  EXPECT_NO_THROW(a.backend->solve_owned(target_job(kTargetJob, a.cfg.job_deadline_ns)));
  ASSERT_TRUE(a.boundary.record().actual_native_invoked);
  EXPECT_TRUE(a.backend->last_policy_event().at("w2_boundary").at("actual_native_invoked").get<bool>());
}

TEST(W2Review, NativeFailureRetainsTheActualCEntryFact) {
  Armed a(kStartNs + 1000000000, 1000000);
  review_real_c_calls = 0;
  review_force_native_error = true;
  a.backend->set_applied_control(Eigen::Vector2d::Zero());
  EXPECT_THROW(a.backend->solve_owned(target_job(kTargetJob, a.cfg.job_deadline_ns)), std::runtime_error);
  review_force_native_error = false;
  std::cout << "REVIEW_NATIVE_ERROR_FACTS " << Json{
      {"real_C_solve_calls", review_real_c_calls},
      {"boundary", w2_boundary_json(a.boundary.record())},
      {"policy", a.backend->last_policy_event()}}.dump() << std::endl;
  ASSERT_EQ(review_real_c_calls, 1u);
  EXPECT_TRUE(a.boundary.record().actual_native_invoked);
  EXPECT_TRUE(a.backend->last_policy_event().contains("w2_boundary"));
}

TEST(W2Review, StopRaisedDuringPreparationPreventsTheCEntry) {
  Armed a(kStartNs + 1000000000, 1000000);
  bool stop = false;
  a.backend->attach_boundary(&a.boundary, [&stop] { return stop; });
  review_real_c_calls = 0;
  review_stop_during_preparation = &stop;
  a.backend->set_applied_control(Eigen::Vector2d::Zero());
  bool threw = false;
  try { a.backend->solve_owned(target_job(kTargetJob, a.cfg.job_deadline_ns)); }
  catch (const std::runtime_error &) { threw = true; }
  review_stop_during_preparation = nullptr;
  std::cout << "REVIEW_PREPARATION_STOP_FACTS " << Json{
      {"stop", stop}, {"real_C_solve_calls", review_real_c_calls}, {"threw", threw},
      {"boundary", w2_boundary_json(a.boundary.record())}}.dump() << std::endl;
  EXPECT_TRUE(threw);
  EXPECT_EQ(review_real_c_calls, 0u);
}

TEST(W2Review, DeadlineCrossedDuringPreparationPreventsTheCEntry) {
  const int64_t deadline = kStartNs + 150000000;
  Armed a(deadline, 1000000);
  review_real_c_calls = 0;
  review_clock_during_preparation = &a.clock;
  review_clock_after_preparation = deadline + 1;
  a.backend->set_applied_control(Eigen::Vector2d::Zero());
  EXPECT_THROW(a.backend->solve_owned(target_job(kTargetJob, deadline)), std::runtime_error);
  review_clock_during_preparation = nullptr;
  std::cout << "REVIEW_PREPARATION_DEADLINE_FACTS " << Json{
      {"deadline_ns", deadline}, {"clock_ns", a.clock},
      {"real_C_solve_calls", review_real_c_calls},
      {"boundary", w2_boundary_json(a.boundary.record())}}.dump() << std::endl;
  EXPECT_EQ(review_real_c_calls, 0u);
}
