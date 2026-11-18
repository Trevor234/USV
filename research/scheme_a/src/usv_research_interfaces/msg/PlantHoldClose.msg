# hold 窗口的闭合事实（v2）：plant 明确声明"某个执行窗口的非零推力已经结束"及终点状态。
#
# 三种来源必须可分辨：
#   expired    —— 窗口自然到期，且没有后继命令接续（缺口内零推力）；
#   superseded —— 后继命令接管（推力切换到新窗口）；
#   stop       —— 进程收到 stop，在子步边界提前收尾（close < executed_end）。
string<=64 schema_version
string<=128 run_id
string<=64 boot_id
string<=64 contract_hash
uint64 execution_index
int64 plant_steady_origin_ns
int64 close_steady_ns
int64 close_sim_ns
int64 state_sample_sim_ns
# 被闭合窗口原本的结束时刻（用于证明 stop 确实提前截断）。
int64 executed_end_steady_ns
string<=64 clock_identity
uint64 clock_epoch
string<=16 reason
float64[6] state
