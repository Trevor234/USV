# C3.6-B：实际 Applied 资源拒绝与退出后 tail 修订

修订前节点按 create-only 保存于 [node_before_resource_tail_v1.cpp](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_6_adapter_20261013_12/review/node_before_resource_tail_v1.cpp)，96958 字节，SHA256 `f780e357255a151ab0575553187691faa74c0bd751f36e4c062ae3c644714f8b`。其他 v1 来源人口由主代理单独冻结，不覆写旧来源、失败或 expected。

新 [实际 Observer](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_6_adapter_20261013_v13/observer/src/shadow/regulator_shadow_observer.cpp) 的 Applied subscription 直接调用同文件 `receive_applied`，生产 runtime 与 source-linked 测试使用同一分支。

资源超界拒绝先在业务 mutex 下计 `legacy_received_`、`input_commit_ordinal_` 和 Applied raw callback 序列各一次；永久置生命周期与投影完整性为 false，并停止 measurement eligibility、清未提交工作。若已经 ready，仍走原永久 invalidation 路径。源记录只含字段长度、native sequence、实际 16 字节 GID、计数与有限标志，不复制或序列化超界大字符串。随后合法 sequence-one/two 不能消除这一完整人口缺口。

已认证 driver request 的原 `request_ns` 保存为 `adapter_close_request_ns_`，和 Observer 看见该文件的 `adapter_close_ns_` 分开。实际 `queued_terminal_zero_predicate` 只在 owner pidfd 已退出、原 callback GID 匹配、driver 请求已经认证、业务已经 closing、原 request 起两秒以内，且实际两路命令有限并等于零、两路调用成功、start/end 不早于 request、不晚于当前 receipt、逐路调用有序时，允许进入后续完整 payload gate。`shutdown_zero` 标签本身不足以成立。该 predicate 的 true 仍须后续原身份、序列、载荷与组件 gate 才能形成终端命令事实，不能代表系统 endpoint 退出或新 Job 许可。

新增 [test_c36_applied_boundary_v1.cpp](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_6_adapter_20261013_v13/tests/test_c36_applied_boundary_v1.cpp)，CMake target 为 `test_c36_applied_boundaries`，有 10 个用例。两个用例直接执行实际节点 resource/callback/readiness 路径，包括 startup 超界后合法序列无法恢复 ready、正常回调可 ready 而 ready 后超界永久关闭。其余用例调用节点的实际 tail predicate，覆盖非零/非有限、早于关闭、晚于 receipt、cross-channel 时序、foreign GID、pidfd alive/失败、未关闭业务、两秒边界、失败通路和标签。

tail predicate 测试的 authentication/GID/closing 输入是明确 seeded 的有限输入；它们没有启动真实退出 owner，不能替代本批 Supervisor 的实际 callback、pidfd、关闭和完整尾部证据。测试宏仅编入 source-linked GTest，生产节点没有该测试构造器或 hook。此代理未编译或启动 ROS；实际结果由主代理的新 build/运行和失败保留记录报告。组件检查与 B4/M0b/B5/M4、连续 DDS 唯一性和研究结论继续分开。
