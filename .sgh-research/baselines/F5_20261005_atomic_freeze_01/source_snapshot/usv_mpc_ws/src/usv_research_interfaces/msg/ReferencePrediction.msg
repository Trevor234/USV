# Actual solve inputs and accepted prediction; publisher-side observation only.
# Independent extension. StateSnapshot/AppliedControl/CycleTiming stay v1.
string schema_version
string run_id
string producer_instance_id
string baseline_id
string config_hash
string steady_clock_domain
uint64 sequence
uint64 clock_epoch
int64 sim_time_ns
int64 clock_receive_steady_ns
int64 clock_age_ns
string clock_status
uint64 cycle_sequence
uint64 applied_sequence
int64 state_copy_steady_ns
int64 reference_ready_steady_ns
int64 solve_start_steady_ns
int64 solve_end_steady_ns
int64 freeze_steady_ns
float64[6] controller_state_6
string state_kind
uint64 received_odom_sequence
uint64 received_imu_sequence
int64 odom_stamp_ns
int64 imu_stamp_ns
# Versions count every callback, including callbacks clearing empty/malformed data.
# They identify received container versions, not valid or accepted messages.
uint64 path_received_sequence
uint64 profile_received_sequence
int64 path_stamp_ns
int64 profile_stamp_ns
bool profile_stamp_known
uint64 path_size
uint64 profile_size
int32 nearest_index
int32 start_index
int32 configured_start_offset
int32 effective_start_offset
bool profile_synced
string profile_sync_reason
string reference_mode
bool profile_t0_known
float64 profile_t0
# config_hash binds all run config; this hash binds effective nominal model only.
string nominal_config_hash
string backend
uint32 horizon_steps
float64 prediction_dt
# k_major = k=0 column first, each column in state/control component order.
# Reference is the exact already-built matrix supplied to solve(), 6*(N+1).
string matrix_layout
uint32 reference_rows
uint32 reference_cols
float64[] reference_data
bool solve_success
bool deadline_miss
string rejection_reason
# Only successful post-deadline-gate finite, correctly sized info.X_pred/U_pred.
# False => all prediction shapes are zero and arrays empty; no candidate copy.
bool prediction_available
string prediction_reason
uint32 x_pred_rows
uint32 x_pred_cols
float64[] x_pred_data
uint32 u_pred_rows
uint32 u_pred_cols
float64[] u_pred_data
