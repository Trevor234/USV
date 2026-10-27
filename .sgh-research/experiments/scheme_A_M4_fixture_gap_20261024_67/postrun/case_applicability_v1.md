# 第67批：原M4逐case证据与差集

原9组、18条required_cases，拆为69个具名核对项。状态不是阶段资格，完整M4/F6/P1保持false。

| ID | 核对项 | 状态 | 证据代号 | 已证范围与剩余义务 |
| --- | --- | --- | --- | --- |
| compatibility_input.01 | F5输入资格/数值准入核心 | 可复用组件 | F5_mapping, current_core58 | 原F5冻结源码/XML/ELF可对应，9项同源oracle与当前7项数学源码匹配；3项日志开关原回归保留。 不声称当前legacy wrapper整文件相同，不关闭M4强制Source/Witness来冒充旧logging测试。 |
| compatibility_input.02 | F5参考构造与全部metadata | 可复用组件 | F5_mapping, current_core58 | 原F5冻结源码/XML/ELF可对应，9项同源oracle与当前7项数学源码匹配；3项日志开关原回归保留。 不声称当前legacy wrapper整文件相同，不关闭M4强制Source/Witness来冒充旧logging测试。 |
| compatibility_input.03 | F5输入映射/scale/clamp | 可复用组件 | F5_mapping, current_core58 | 原F5冻结源码/XML/ELF可对应，9项同源oracle与当前7项数学源码匹配；3项日志开关原回归保留。 不声称当前legacy wrapper整文件相同，不关闭M4强制Source/Witness来冒充旧logging测试。 |
| compatibility_input.04 | 原F5 logging off/on回归 | 可复用组件 | F5_mapping, current_core58 | 原F5冻结源码/XML/ELF可对应，9项同源oracle与当前7项数学源码匹配；3项日志开关原回归保留。 不声称当前legacy wrapper整文件相同，不关闭M4强制Source/Witness来冒充旧logging测试。 |
| compatibility_input.05 | 新target-reference独立fixture及共享数学核心 | 可复用组件 | F5_mapping, 49_components, current_core58, source_ranges | 目标参考独立解析/预测组件与共享构造器，名义hydro19及nominal hash完全相同。 来源明确为.05 nominal RK4，原F5 VRX/plant/reference整体同一性不转移。 |
| compatibility_input.06 | 输入与输出owner分离，无隐藏输出writer | 可复用owned子项 | 66_W2, 49_normal | 已运行四角色身份/端点与Stored对账；Fixture无左右控制writer。  |
| time_boundaries.01 | ready50ms | 可复用组件 | current_core58 | 实际Admission头文件的确定性注册/消费，保留原150ms截止及200ms目标。 这些是合成ready时刻，不改称实际native solve持续了对应毫秒数。 |
| time_boundaries.02 | ready150ms等号 | 可复用组件 | current_core58 | 实际Admission头文件的确定性注册/消费，保留原150ms截止及200ms目标。 这些是合成ready时刻，不改称实际native solve持续了对应毫秒数。 |
| time_boundaries.03 | ready150ms+1ns | 可复用组件 | current_core58 | 实际Admission头文件的确定性注册/消费，保留原150ms截止及200ms目标。 这些是合成ready时刻，不改称实际native solve持续了对应毫秒数。 |
| time_boundaries.04 | ready250ms | 可复用组件 | current_core58 | 实际Admission头文件的确定性注册/消费，保留原150ms截止及200ms目标。 这些是合成ready时刻，不改称实际native solve持续了对应毫秒数。 |
| time_boundaries.05 | ready400ms | 可复用组件 | current_core58 | 实际Admission头文件的确定性注册/消费，保留原150ms截止及200ms目标。 这些是合成ready时刻，不改称实际native solve持续了对应毫秒数。 |
| time_boundaries.06 | 完整注册完成点before/equal/after | 可复用组件 | current_core58, source_ranges | finalize_ready等号保留、strict-after撤销；实际candidate函数仍在工作之后重读完成时间。  |
| time_boundaries.07 | early ready不得提前激活 | 可复用组件 | current_core58 | 到200ms前不能take且只消费一次。  |
| time_boundaries.08 | wrong target/错版本/重复 | 可复用组件 | current_core58 | Ticket准入拒绝，未替代typed Candidate完整接线。  |
| time_boundaries.09 | delayed tick/错过tick不追赶 | 可复用组件 | current_core58, current_policy92 | 实际due_tick和OutputAuthority错拍/jitter规则已验证，固定槽位不滚到新目标。 current tick_loop调度外壳的受控250/400ms交错由T1源链接检查补齐。 |
| time_boundaries.10 | 不延长deadline/target | 可复用组件 | current_core58, 66_W2 | 改deadline/target即time_contract；真实W2释放后仍依原截止拒绝C。  |
| native_block_and_delivery.01 | native边界独立release | 可复用owned子项 | 66_W2 | Job2/ordinal1驻留417.85ms；独立pipe释放验证成功，原截止已过，C调用0。  |
| native_block_and_delivery.02 | 驻留期间多完整tick及真实心跳 | 可复用owned子项 | 66_W2 | tick3/4及2次续租，未失租约/触发watchdog。  |
| native_block_and_delivery.03 | active/pending/ready有界与单backend | 可复用owned子项 | 66_W2, source_ranges | 本次实际Job多重集1 delivered/2 expired/3 replaced/4 discarded；单计算线程/backend，ready最大1。  |
| native_block_and_delivery.04 | 投递延迟与native驻留分离 | 可复用owned子项 | 56_W3, historical_raw_reaudit, historical_identity, source_ranges | W3_05原始Source/Stored重审通过；投递与正常收尾片段逐字节相同；当前未arm的W2路径不等待。 复用原登记case及相同投递层，不声称本次又运行了新66二进制W3。 |
| native_block_and_delivery.05 | 生成后单次丢弃、no_candidate、恢复 | 可复用owned子项 | 56_W4, historical_raw_reaudit, historical_identity, source_ranges | W4_05原始记录重审通过；原Job3丢弃与目标tick4/恢复完整，当前同投递片段保留。 连续多次drop不在原这一子句的单次case内，另列未扩展边界，不新增为必经前置。 |
| candidate_identity_shape.01 | failed/solver_invoked=false | 需补接线验证 | source_ranges, current_core58 | 现candidate()、资源/Job/finite/echo/Ticket门可定位；Ticket级重复/版本组件成立。 T1必须驱动当前真实candidate()/Worker结果准入，逐项断言不注册/不接受及明确原因；不得用Ticket测试冒充整个Candidate路径。 |
| candidate_identity_shape.02 | invalid原生prediction shape/available=false | 需补接线验证 | source_ranges, current_core58 | 现candidate()、资源/Job/finite/echo/Ticket门可定位；Ticket级重复/版本组件成立。 T1必须驱动当前真实candidate()/Worker结果准入，逐项断言不注册/不接受及明确原因；不得用Ticket测试冒充整个Candidate路径。 |
| candidate_identity_shape.03 | 预测或首控制NaN | 需补接线验证 | source_ranges, current_core58 | 现candidate()、资源/Job/finite/echo/Ticket门可定位；Ticket级重复/版本组件成立。 T1必须驱动当前真实candidate()/Worker结果准入，逐项断言不注册/不接受及明确原因；不得用Ticket测试冒充整个Candidate路径。 |
| candidate_identity_shape.04 | 重复Candidate | 需补接线验证 | source_ranges, current_core58 | 现candidate()、资源/Job/finite/echo/Ticket门可定位；Ticket级重复/版本组件成立。 T1必须驱动当前真实candidate()/Worker结果准入，逐项断言不注册/不接受及明确原因；不得用Ticket测试冒充整个Candidate路径。 |
| candidate_identity_shape.05 | 旧/乱序Job ID | 需补接线验证 | source_ranges, current_core58 | 现candidate()、资源/Job/finite/echo/Ticket门可定位；Ticket级重复/版本组件成立。 T1必须驱动当前真实candidate()/Worker结果准入，逐项断言不注册/不接受及明确原因；不得用Ticket测试冒充整个Candidate路径。 |
| candidate_identity_shape.06 | 外来producer/Worker | 需补接线验证 | source_ranges, current_core58 | 现candidate()、资源/Job/finite/echo/Ticket门可定位；Ticket级重复/版本组件成立。 T1必须驱动当前真实candidate()/Worker结果准入，逐项断言不注册/不接受及明确原因；不得用Ticket测试冒充整个Candidate路径。 |
| candidate_identity_shape.07 | 外来boot | 需补接线验证 | source_ranges, current_core58 | 现candidate()、资源/Job/finite/echo/Ticket门可定位；Ticket级重复/版本组件成立。 T1必须驱动当前真实candidate()/Worker结果准入，逐项断言不注册/不接受及明确原因；不得用Ticket测试冒充整个Candidate路径。 |
| candidate_identity_shape.08 | 旧task/model/config/schedule/epoch版本 | 需补接线验证 | source_ranges, current_core58 | 现candidate()、资源/Job/finite/echo/Ticket门可定位；Ticket级重复/版本组件成立。 T1必须驱动当前真实candidate()/Worker结果准入，逐项断言不注册/不接受及明确原因；不得用Ticket测试冒充整个Candidate路径。 |
| task_reference.01 | freeze前clear | 需补接线验证 | F5_mapping, 49_components, 50_publication16, source_ranges, current_core58 | 共享数学/直接invalidate/旧同源callback与selector证据保留，原F5是同步语义。 T1补当前path/profile→task→pending/ready/activation交错；需要跨进程事实的最小部分再用T2已拥有的Fixture writer刺激。 |
| task_reference.02 | freeze前single point | 需补接线验证 | F5_mapping, 49_components, 50_publication16, source_ranges, current_core58 | 共享数学/直接invalidate/旧同源callback与selector证据保留，原F5是同步语义。 T1补当前path/profile→task→pending/ready/activation交错；需要跨进程事实的最小部分再用T2已拥有的Fixture writer刺激。 |
| task_reference.03 | 求解/ready期间clear | 需补接线验证 | F5_mapping, 49_components, 50_publication16, source_ranges, current_core58 | 共享数学/直接invalidate/旧同源callback与selector证据保留，原F5是同步语义。 T1补当前path/profile→task→pending/ready/activation交错；需要跨进程事实的最小部分再用T2已拥有的Fixture writer刺激。 |
| task_reference.04 | 求解期间reference replacement | 需补接线验证 | F5_mapping, 49_components, 50_publication16, source_ranges, current_core58 | 共享数学/直接invalidate/旧同源callback与selector证据保留，原F5是同步语义。 T1补当前path/profile→task→pending/ready/activation交错；需要跨进程事实的最小部分再用T2已拥有的Fixture writer刺激。 |
| task_reference.05 | 相同内容重发不改语义task | 需补接线验证 | F5_mapping, 49_components, 50_publication16, source_ranges, current_core58 | 共享数学/直接invalidate/旧同源callback与selector证据保留，原F5是同步语义。 T1补当前path/profile→task→pending/ready/activation交错；需要跨进程事实的最小部分再用T2已拥有的Fixture writer刺激。 |
| task_reference.06 | path/profile stamp或长度不匹配 | 需补接线验证 | F5_mapping, 49_components, 50_publication16, source_ranges, current_core58 | 共享数学/直接invalidate/旧同源callback与selector证据保留，原F5是同步语义。 T1补当前path/profile→task→pending/ready/activation交错；需要跨进程事实的最小部分再用T2已拥有的Fixture writer刺激。 |
| task_reference.07 | 普通new odom不无条件饿死 | 需补接线验证 | F5_mapping, 49_components, 50_publication16, source_ranges, current_core58 | 共享数学/直接invalidate/旧同源callback与selector证据保留，原F5是同步语义。 T1补当前path/profile→task→pending/ready/activation交错；需要跨进程事实的最小部分再用T2已拥有的Fixture writer刺激。 |
| state_clock.01 | odom stale/future与独立receive/sim age | 可复用组件 | current_core58, 53_components, source_ranges | 源时间/激活selector同源，当前纯组件和旧源链接激活拒绝证据可复用。 若需认证topic到callback到epoch的联合刺激，由T1/T2明确补交错，组件不称新owned故障。 |
| state_clock.02 | IMU只在mixed时适用age/skew | 可复用组件 | current_core58, 53_components, source_ranges | 源时间/激活selector同源，当前纯组件和旧源链接激活拒绝证据可复用。 若需认证topic到callback到epoch的联合刺激，由T1/T2明确补交错，组件不称新owned故障。 |
| state_clock.03 | 激活状态不匹配/finite/yaw wrap | 可复用组件 | current_core58, 53_components, source_ranges | 源时间/激活selector同源，当前纯组件和旧源链接激活拒绝证据可复用。 若需认证topic到callback到epoch的联合刺激，由T1/T2明确补交错，组件不称新owned故障。 |
| state_clock.04 | clock pause | 需补接线验证 | current_core58, 53_components, source_ranges | ClockWindow reset/jump/ratio与旧真实clock callback回退组件可复用。 T1核当前clock/tick的schedule/epoch失效及不可复活；当前Fixture不能登记这些刺激，T2只补必要跨进程子集。 |
| state_clock.05 | clock resume | 需补接线验证 | current_core58, 53_components, source_ranges | ClockWindow reset/jump/ratio与旧真实clock callback回退组件可复用。 T1核当前clock/tick的schedule/epoch失效及不可复活；当前Fixture不能登记这些刺激，T2只补必要跨进程子集。 |
| state_clock.06 | clock reset/backward | 需补接线验证 | current_core58, 53_components, source_ranges | ClockWindow reset/jump/ratio与旧真实clock callback回退组件可复用。 T1核当前clock/tick的schedule/epoch失效及不可复活；当前Fixture不能登记这些刺激，T2只补必要跨进程子集。 |
| state_clock.07 | clock大jump | 需补接线验证 | current_core58, 53_components, source_ranges | ClockWindow reset/jump/ratio与旧真实clock callback回退组件可复用。 T1核当前clock/tick的schedule/epoch失效及不可复活；当前Fixture不能登记这些刺激，T2只补必要跨进程子集。 |
| state_clock.08 | RTF低边界 | 需补接线验证 | current_core58, 53_components, source_ranges | ClockWindow reset/jump/ratio与旧真实clock callback回退组件可复用。 T1核当前clock/tick的schedule/epoch失效及不可复活；当前Fixture不能登记这些刺激，T2只补必要跨进程子集。 |
| state_clock.09 | RTF高边界 | 需补接线验证 | current_core58, 53_components, source_ranges | ClockWindow reset/jump/ratio与旧真实clock callback回退组件可复用。 T1核当前clock/tick的schedule/epoch失效及不可复活；当前Fixture不能登记这些刺激，T2只补必要跨进程子集。 |
| anchor_fallback.01 | 区间内改变后回到原值不能伪称等价 | 可复用组件 | current_core58, current_policy92, 50_publication16, 66_W2, source_ranges | 当前真实policy/header组件成立；50逐侧真实API组件及49/66完整API对账可与该层联合使用。 不将合成五次miss说成五次实际owned缺解；联合复判要保留层次与Source适用范围。 |
| anchor_fallback.02 | same-value republish保留连续历史 | 可复用组件 | current_core58, current_policy92, 50_publication16, 66_W2, source_ranges | 当前真实policy/header组件成立；50逐侧真实API组件及49/66完整API对账可与该层联合使用。 不将合成五次miss说成五次实际owned缺解；联合复判要保留层次与Source适用范围。 |
| anchor_fallback.03 | 不同左右实际API间隔分别rate | 可复用组件 | current_core58, current_policy92, 50_publication16, 66_W2, source_ranges | 当前真实policy/header组件成立；50逐侧真实API组件及49/66完整API对账可与该层联合使用。 不将合成五次miss说成五次实际owned缺解；联合复判要保留层次与Source适用范围。 |
| anchor_fallback.04 | missing/evicted history不能授权 | 可复用组件 | current_core58, current_policy92, 50_publication16, 66_W2, source_ranges | 当前真实policy/header组件成立；50逐侧真实API组件及49/66完整API对账可与该层联合使用。 不将合成五次miss说成五次实际owned缺解；联合复判要保留层次与Source适用范围。 |
| anchor_fallback.05 | 连续五次miss | 可复用组件 | current_core58, current_policy92, 50_publication16, 66_W2, source_ranges | 当前真实policy/header组件成立；50逐侧真实API组件及49/66完整API对账可与该层联合使用。 不将合成五次miss说成五次实际owned缺解；联合复判要保留层次与Source适用范围。 |
| anchor_fallback.06 | HOLD等号及重发不续期 | 可复用组件 | current_core58, current_policy92, 50_publication16, 66_W2, source_ranges | 当前真实policy/header组件成立；50逐侧真实API组件及49/66完整API对账可与该层联合使用。 不将合成五次miss说成五次实际owned缺解；联合复判要保留层次与Source适用范围。 |
| anchor_fallback.07 | HOLD之后ramp | 可复用组件 | current_core58, current_policy92, 50_publication16, 66_W2, source_ranges | 当前真实policy/header组件成立；50逐侧真实API组件及49/66完整API对账可与该层联合使用。 不将合成五次miss说成五次实际owned缺解；联合复判要保留层次与Source适用范围。 |
| anchor_fallback.08 | invalid立即绕过HOLD | 可复用组件 | current_core58, current_policy92, 50_publication16, 66_W2, source_ranges | 当前真实policy/header组件成立；50逐侧真实API组件及49/66完整API对账可与该层联合使用。 不将合成五次miss说成五次实际owned缺解；联合复判要保留层次与Source适用范围。 |
| anchor_fallback.09 | unknown侧零请求无已知零资格 | 可复用组件 | current_core58, current_policy92, 50_publication16, 66_W2, source_ranges | 当前真实policy/header组件成立；50逐侧真实API组件及49/66完整API对账可与该层联合使用。 不将合成五次miss说成五次实际owned缺解；联合复判要保留层次与Source适用范围。 |
| publication_exit.01 | shutdown before submit | 可复用owned子项 | 53_R1, source_ranges | 原R1实际owned pre-grant取消/零API，核心准备与submit函数沿用。  |
| publication_exit.02 | clear/shutdown after committed submit | 需补接线验证 | 50_publication16, 53_components, source_ranges | 旧clear直接helper及ShutdownDuringValidation组件已有；未把它扩成所有真实提交交错。 T1用同一当前Regulator接线覆盖提交前/后及最终activation拒绝；按义务层次决定T2最小case。 |
| publication_exit.03 | shutdown与ready/activation交错 | 需补接线验证 | 50_publication16, 53_components, source_ranges | 旧clear直接helper及ShutdownDuringValidation组件已有；未把它扩成所有真实提交交错。 T1用同一当前Regulator接线覆盖提交前/后及最终activation拒绝；按义务层次决定T2最小case。 |
| publication_exit.04 | left API partial failure | 可复用组件 | 50_publication16, current_policy92, source_ranges | 50真实rcl publish seam组件16例；publish与OutputAuthority逻辑保留，成功侧不可回滚。 这是实际API源链接组件，非本次新增四角色部分发布故障run。 |
| publication_exit.05 | right API partial failure | 可复用组件 | 50_publication16, current_policy92, source_ranges | 50真实rcl publish seam组件16例；publish与OutputAuthority逻辑保留，成功侧不可回滚。 这是实际API源链接组件，非本次新增四角色部分发布故障run。 |
| publication_exit.06 | Worker真实死亡 | 可复用owned子项 | 53_R2, source_ranges | 原R2实际owned死亡与有限ramp/关闭；check_worker_locked保持同源。  |
| publication_exit.07 | active watchdog与心跳/租约互斥 | 可复用owned子项 | 56_W1, historical_raw_reaudit, source_ranges | W1_05重审通过，转移时真实租约仍有效，不能再沿用53外部信号无法隔离的历史阻塞结论。  |
| publication_exit.08 | capability receipt lease到期 | 可复用owned子项 | 53_R3, current_core58, source_ranges | 原R3实际owned失租约；当前14项lease组件覆盖等号/续租/终端不可恢复。  |
| publication_exit.09 | cleanup_failed正确失败 | 当前路径未覆盖 | 66_W2 | 66证明的是健康有限关闭和group为空；自动重试0不是cleanup_failed分支已经验证。 T3对当前关闭/监督实际消费函数注入有界失败并证明无新spawn；保留真实进程与模拟失败范围，不制造不可杀进程。 |
| publication_exit.10 | 旧group未空禁止restart | 当前路径未覆盖 | 66_W2 | 66证明的是健康有限关闭和group为空；自动重试0不是cleanup_failed分支已经验证。 T3对当前关闭/监督实际消费函数注入有界失败并证明无新spawn；保留真实进程与模拟失败范围，不制造不可杀进程。 |
| actual_source_recording.01 | 隔离normal straight .05真实完整窗 | 可复用owned子项 | 49_normal, F5_mapping, source_ranges | 49实际20s正常窗/105 API pairs保留；.05来源和数值core对齐。 不把66短W2正常前缀改称新的20s正常资格。 |
| actual_source_recording.02 | controlled faults与完整Source/Stored | 可复用owned子项 | historical_raw_reaudit, 66_W2, source_ranges | 三例旧诊断重新读原始Source/Stored；66W2独立全流对账成立。  |
| actual_source_recording.03 | log queue pressure及声明drop | 当前路径未覆盖 | 49_normal, 66_W2 | 正常/故障无丢失是已知事实，不等于施加队列压力。 T3以当前enqueue/drain路径施加有界压力，分清generated/emitted/dropped/Stored，异常资格及未解释差额必须拒绝。 |
| actual_source_recording.04 | Source/emit/Stored/API计数及身份 | 可复用owned子项 | 66_W2, historical_raw_reaudit | 66完整306条Stored、11条心跳、6组API及三个旧case的原始多重集合重新核对。  |
| actual_source_recording.05 | before/after资产保护 | 可复用组件 | source_ranges, F5_mapping | 本批886项66原件、381项源码审计输入、21个普通工作区文件及最终读回将逐项核对。  |

## 证据代号与固定来源

| 代号 | 来源 | SHA256 |
| --- | --- | --- |
| 47_policy92 | [entry_policy_cases_v2.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47/verification/entry_policy_cases_v2.json) | `8cbcfd0ec1fb2614f291b57bfde2528b16a4cd543854bae139cd2f39dcc90402` |
| 49_components | [component_verification_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_recorder_bootstrap_20261021_49/verification/component_verification_v1.json) | `7767da5319231e5cb777222538f9ddfa4047a4d3b75332d40defa9088212cb9f` |
| 49_source_core | [source_core_reuse_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_recorder_bootstrap_20261021_49/verification/source_core_reuse_v1.json) | `dedcf37cf79d23be349a881106041f40757674c3682134d1568625b2e2a6c83e` |
| 49_normal | [actual_normal_audit_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_recorder_bootstrap_20261021_49/postrun/actual_normal_audit_v1.json) | `78f2c3eb79185af640c318eb41713344ce4211670f44b5d006313a9fbc6ad6fc` |
| 49_F5_scope | [F5_and_calibrated_nominal_scope_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_recorder_bootstrap_20261021_49/evidence/F5_and_calibrated_nominal_scope_v1.json) | `fb1fec031c9346d3d70affec716ca584681efdaa11053b8fa553380170a21913` |
| 50_publication16 | [publication_fault_audit_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_publication_faults_20261021_50/postrun/publication_fault_audit_v1.json) | `72fba6e7a8c7b5661a87502a6ff718cb823cb14a7cf11df4e624db60b7c0fff3` |
| 53_components | [component_verification_v5.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_owned_faults_20261021_53/verification/component_verification_v5.json) | `40b067af08f5fd74c25a2e72774f3700b0c197fe45d2652e85a1268dc3ec6dd5` |
| 53_R1 | [R1_audit_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_owned_faults_20261021_53/postrun/R1_audit_v1.json) | `44ba0d2a0733250bb0e9e8e5f3535dfa867f844fa33d1ab8d2287acaeda85b77` |
| 53_R2 | [R2_audit_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_owned_faults_20261021_53/postrun/R2_audit_v1.json) | `151ef1207121e9ce532bf986ee80e5a504081f5526c5ba7d3053297450058e58` |
| 53_R3 | [R3_audit_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_owned_faults_20261021_53/postrun/R3_audit_v1.json) | `7c6122fbe2209c5451cc856b625f379d4113a910632b14ca39ec398432351139` |
| 53_matrix | [M4_fault_coverage_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_owned_faults_20261021_53/postrun/M4_fault_coverage_v1.json) | `6c9e00e3b986d9f1927bfe5fc6fb585ab757cda35aabbea7860e4460ce344f00` |
| 56_W1 | [W1_audit_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/postrun/W1_audit_v1.json) | `126650fece008b3b37c64d62c12f7cf111044be016cb989460e9034da015472d` |
| 56_W3 | [W3_audit_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/postrun/W3_audit_v1.json) | `316e75f61d5adebabc9650fc008e5dd586ba78d572247a4cef0e770e2e6c2447` |
| 56_W4 | [W4_audit_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_diagnostic_worker_20261021_56/postrun/W4_audit_v1.json) | `02a60742fcf438037d54a36f99e35329ed604186299eae080bb36c1a2a5e6f8a` |
| 66_W2 | [owned_audit_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_owned_takeover_20261023_66/evidence/owned_audit_v1.json) | `511422cf61f1fc665fdf8076ae102e883b6db92c89db412fa81619cd364beab7` |
| source_ranges | [source_applicability_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_fixture_gap_20261024_67/evidence/source_applicability_v1.json) | `2590391888ad907fe14d6a5c0bb22e9f1663d0b7eae976aae91d04adfdf108c6` |
| F5_mapping | [F5_fixture_applicability_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_fixture_gap_20261024_67/evidence/F5_fixture_applicability_v1.json) | `558e5916edcbe7bd270ed805e33e8b001d592d88603241403546d9027c31fc18` |
| current_policy92 | [verification_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_fixture_gap_20261024_67/evidence/policy92_replay/verification_v1.json) | `283bd374421f1f20e65a5b6c0da46df57bd05479521eebd6d4f7bf08848b619a` |
| current_core58 | [verification_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_fixture_gap_20261024_67/evidence/core_components_attempt02/verification_v1.json) | `a15cc5951b41bc2191c1368c03009615cfe3878260aad58ae2a7e3aff7c6423b` |
| historical_identity | [historical_case_identity_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_fixture_gap_20261024_67/evidence/historical_case_identity_v1.json) | `870463290580bba653fec9d77f5af6d481f0ae0089af674cc35a5c9aff855eec` |
| historical_raw_reaudit | [verification_v1.json](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_fixture_gap_20261024_67/evidence/historical_reaudit/verification_v1.json) | `b8327483c1b085a8fcf09cf4bb31837090c8ef1879996dea4c9f2279e361c06c` |

## 原条款逐字绑定

- `compatibility_input[0]`：F5 source/reference/mapping qualified old regression and logging off/on → compatibility_input.01, compatibility_input.02, compatibility_input.03, compatibility_input.04
- `compatibility_input[1]`：new target-reference independent fixture, no implicit physical writer → compatibility_input.05, compatibility_input.06
- `time_boundaries[0]`：50/150/250/400ms; ready before/equal/after deadline → time_boundaries.01, time_boundaries.02, time_boundaries.03, time_boundaries.04, time_boundaries.05, time_boundaries.06, time_boundaries.10
- `time_boundaries[1]`：early ready, wrong target, delayed tick → time_boundaries.07, time_boundaries.08, time_boundaries.09
- `native_block_and_delivery[0]`：worker held at native boundary until independent release → native_block_and_delivery.01, native_block_and_delivery.02, native_block_and_delivery.03
- `native_block_and_delivery[1]`：separate result delivery delay/drop → native_block_and_delivery.04, native_block_and_delivery.05
- `candidate_identity_shape[0]`：failed, invalid shape, NaN, duplicate, old/reordered IDs → candidate_identity_shape.01, candidate_identity_shape.02, candidate_identity_shape.03, candidate_identity_shape.04, candidate_identity_shape.05
- `candidate_identity_shape[1]`：foreign producer/boot/version → candidate_identity_shape.06, candidate_identity_shape.07, candidate_identity_shape.08
- `task_reference[0]`：clear/single point before freeze, clear/replacement during solve → task_reference.01, task_reference.02, task_reference.03, task_reference.04
- `task_reference[1]`：same content republish, path/profile mismatch, ordinary new odom → task_reference.05, task_reference.06, task_reference.07
- `state_clock[0]`：source stale/future, mixed skew, activation mismatch → state_clock.01, state_clock.02, state_clock.03
- `state_clock[1]`：pause/resume/reset/jump and RTF band → state_clock.04, state_clock.05, state_clock.06, state_clock.07, state_clock.08, state_clock.09
- `anchor_fallback[0]`：mid-interval change/same-value republish/different API intervals/missing history → anchor_fallback.01, anchor_fallback.02, anchor_fallback.03, anchor_fallback.04
- `anchor_fallback[1]`：five misses, HOLD equality/after, invalid bypass, unknown side → anchor_fallback.05, anchor_fallback.06, anchor_fallback.07, anchor_fallback.08, anchor_fallback.09
- `publication_exit[0]`：clear/shutdown before/after submit; left/right partial API outcomes → publication_exit.01, publication_exit.02, publication_exit.03, publication_exit.04, publication_exit.05
- `publication_exit[1]`：worker death, active watchdog, capability lease and cleanup failed → publication_exit.06, publication_exit.07, publication_exit.08, publication_exit.09, publication_exit.10
- `actual_source_recording[0]`：new isolated normal straight0.05 then controlled faults → actual_source_recording.01, actual_source_recording.02
- `actual_source_recording[1]`：log queue pressure, source/emit/bag counts and before/after assets → actual_source_recording.03, actual_source_recording.04, actual_source_recording.05
