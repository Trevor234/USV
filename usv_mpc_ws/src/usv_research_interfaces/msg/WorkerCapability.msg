string<=64 schema_version
string<=128 run_id
string<=64 boot_id
string<=64 contract_hash
string<=64 nominal_hash
string<=64 worker_instance
string<=32 clock_name
string<=16 backend
string<=32 matrix_layout
uint32 horizon_steps
float64 prediction_dt
int64 pid
int64 startup_ns
uint64 completed_jobs
uint64 active_job
uint32 pending_count
bool fault_injection_enabled
bool fatal
string<=256 reason
# v2: 模型运行时就绪事实。三者都是实测值，不是声明值：
#   model_runtime_ready —— 事务已采用构造事实且模型一致；
#   model_plan_sha256   —— 实际加载的计划文件字节摘要（未加载为空）；
#   applied_generation  —— 事务当前已应用的代（0 = 未应用）。
bool model_runtime_ready
string<=64 model_plan_sha256
uint64 applied_generation
