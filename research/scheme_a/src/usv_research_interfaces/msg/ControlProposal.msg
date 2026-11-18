# Bounded PPO first-step control preference proposal (Scheme A WP5/WP7).
string<=64 schema_version
string<=128 run_id
string<=64 boot_id
string<=64 obs_contract_version
string<=64 ppo_model_sha256
uint64 sequence
uint64 target_tick
int64 stamp_sim_ns
int64 stamp_steady_ns
int64 valid_until_sim_ns
float64[2] q_pi
float64 inference_ms
bool valid
string<=64 reason
