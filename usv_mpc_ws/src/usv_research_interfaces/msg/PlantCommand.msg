# 方案 A 受控仿真的唯一执行输入（v2，类型化；不得以 Float64/Twist/字符串代替）。
# 规范：推力单位固定为 [N]，时刻固定为 CLOCK_MONOTONIC 纳秒。
#
# v2 相对 v1 的差别都在"能不能对账"上：
#   * 显式声明**申请执行窗口** [apply_begin, apply_end)；plant 只在该半开区间内
#     施加该推力，区间外一律零推力（hold 到期不靠隐式约定）；
#   * 只带 regulator 自己的时钟仿真时刻，不再回显 plant 的 sim_ns；
#   * 五轴版本与候选 Job 身份保留，供检查器逐项联合核对。
string<=64 schema_version
string<=128 run_id
string<=64 boot_id
string<=64 contract_hash
# 发布该命令的 regulator 实例；plant 不做自报推导。
string<=64 producer_instance_id
# 一拍一命令；sequence 严格递增（迟到/重复刺激也在同一序列空间内）。
uint64 sequence
uint64 tick
# 申请执行窗口（半开）。长度必须等于合同周期 T。
int64 apply_begin_steady_ns
int64 apply_end_steady_ns
# 该命令必须在此时刻前被 plant 接收，否则 late（零执行）。
int64 deadline_steady_ns
# regulator 侧的时钟仿真时刻（诊断用，不参与 plant 的时间推进）。
int64 regulator_clock_sim_ns
# 最终下发推力（N，每通道独立；已过 regulator 的限幅与门禁）。
float64[2] thrust_n
# 五轴版本：plant 回执"我执行的是哪一个版本"，检查器逐轴比对。
uint64 task_generation
uint64 model_generation
uint64 config_generation
uint64 schedule_generation
uint64 clock_epoch
# 该命令所依据的候选身份（0 = 无候选，例如回退/保持命令）。
uint64 candidate_job_id
string<=64 candidate_worker_instance
uint64 candidate_solve_end_ns
