# plant 对一条 PlantCommand 的回执（v2）。
# 每种处置互斥，且必须能分别对账：
#   ok        —— 在 deadline 前接收并在申请窗口内实际施加；
#   rejected  —— 被本地准入拒绝（schema/身份/窗口/推力/重复/待执行/重叠）；
#   late      —— 接收晚于 deadline 或窗口已关闭（零执行）；
#   duplicate —— 同一 sequence 的重复回执，不重复执行；
#   bootstrap —— 构造时发布的初始事实（sequence 0，零执行，给出真实原点）。
#
# 执行区间只描述**实际**发生的事：executed_begin/end_steady_ns 是 plant 的
# 真实推进区间；非 ok 时两者为 0，且 thrust_n 必须为零向量。
string<=64 schema_version
string<=128 run_id
string<=64 boot_id
string<=64 contract_hash
# 回执必须能溯源到**是哪条命令**引起的：刺激注入的命令不得被当成
# regulator 自己的执行链（否则会伪造出序号断档）。
string<=64 producer_instance_id
uint64 sequence
uint64 tick
string<=16 disposition
string<=128 reason
# 真实执行的唯一序号（ok 时从 1 起连续；其它处置为 0）。
uint64 execution_index
# 申请窗口（来自命令，回执只回显，用于核对"声明 = 执行"）。
int64 apply_begin_steady_ns
int64 apply_end_steady_ns
# 该命令被判定时使用的期限（被拒/迟到同样声明，便于逐条对齐命令）。
int64 deadline_steady_ns
# 实际施加区间与 hold 末端（hold_end = executed_begin + T）。
int64 executed_begin_steady_ns
int64 executed_end_steady_ns
int64 hold_end_steady_ns
# plant 的**唯一**仿真时间原点：sim = steady - plant_steady_origin_ns。
int64 plant_steady_origin_ns
int64 receive_steady_ns
int64 executed_steady_ns
# 实际施加的推力（N）。非 ok 时为零并仍须报告，便于对账。
float64[2] thrust_n
# 执行后的物理状态 [x,y,psi,u,v,r] 与该状态的仿真时刻。
float64[6] state
int64 sim_ns
# 该拍实际使用的五轴版本（来自命令，回执不得自报其它值）。
uint64 task_generation
uint64 model_generation
uint64 config_generation
uint64 schedule_generation
uint64 clock_epoch
