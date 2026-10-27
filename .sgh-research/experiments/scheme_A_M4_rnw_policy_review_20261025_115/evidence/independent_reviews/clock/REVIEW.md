# 114 时间证据独立复核

只读历史；未启动 ROS/owned；离线脚本和 C++ 输出在同目录。

## R114-C1：31.91 ms 不是本 run 的接收时钟回退

114 文档把 attempt-2 seq15 左侧 API 的工程投影 sim `102588031850`，与 attempt-1 恢复后第二个 clock 的 `102619942560` 比较了。后者在 attempt-1 Source 行 567；它不在 attempt-2 Source 中。两数既跨 run，也跨字段语义，而且后者不是静默前末 stamp。

attempt-2 原始 Source：
- 行 355 静默前末 clock：sim=101782845634，receive=900490802698840。
- 行 563 恢复首 clock：sim=102580295878，receive=900492341920388。
- 差值 sim=+797450244 ns，receive=+1539221548 ns。
- 97 条 clock 全部 epoch=0；raw CDR 再解码与每条 sim 字段一致；无回退。
- attempt-1 另有 104 条 clock，同样无回退、epoch 全0。

因此本 run 未触发源码 L630 的 s<sim_ 或 >5s 分支。计划的“首恢复 stamp >= 末接收 stamp”在当前失败 run 本来就通过，无法锁定当前缺陷。

## R114-C2：工程投影回退真实存在，但签名不需要竞态

attempt-2：
- Source 行 537 seq14 右侧工程 sim=103129840890。
- Source 行 566 seq15 左侧工程 sim=102588031850。
- 回退 541809040 ns（左到左为 541761190 ns）。
- Source 行 568 一致性失败已记录 history known=[false,true]，authority=[true,true]，两侧 seq/time 均属于 seq15。

生产源码 `regulator_owned_execute.cpp`：
1. L962 将当前接收 clock 线性投影到实际 publish start。
2. L967 先对 side0 调 `apply_channel_result`，使 side0 known=true、seq15、time15。
3. L968 调 `push_history_locked`。
4. L844 检测工程 sim 比 history.back().sim_ns 小，同步清两侧 known，并清 history；该左侧事件直接 return，不入 history。
5. side1 顺序完成同样的 apply，此时 history 已空，不回退，得到 [false,true]。
6. L1248 检查并记录真实分歧。

精确提取 L844 的生产函数正文，搭配真正的 `publication_result_v1.hpp`，进行无 ROS 单线程 C++ 重放，匹配 [false,true]、seq=[15,15]、observed API starts，并记录唯一一次 `held_history_time_regression`。无回退正控为 [true,true]。该探针使用最小状态和 stub invalidation collaborators，不冒称完整 Regulator 调用测试或运行时分支事件。

Source 没有专门的 held-history-reset 分支事件；所以区分：工程 sim 回退、锚快照是直接观测，L844 是与源码及精确函数重放一致的机制归因。不能把尚未观测的 clock 线程交错写成唯一运行时因果。

## 对计划的影响

- B0 只改 L630，不会命中本次失效路径；不得立即按两处最小 diff 执行 owned。
- B2 可作为显式墙时映射连续性的候选，但论据应针对工程投影历史回退，不能继续称“消除已发生的接收 clock 回退”。
- stamp 必须绑定它对应的 publish target steady 时间；hold 命令时刻不等于末次发布时刻。本 run 二者相差 11.439084 ms。实际动作间隔 1527.323783 ms。
- 新断言应检查工程 history 事件前后、跨侧和重基语义；同时独立保留实际 API 权威 n/seq/time 不被 clock/rebase 失效抹掉，guard 仍拒绝真实分歧。
