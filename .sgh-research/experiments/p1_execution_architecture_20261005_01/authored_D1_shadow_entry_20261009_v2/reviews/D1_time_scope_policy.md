# D1 时间声明边界：工程门与观察量

日期：2026-10-09。状态：声明边界已明确；参数依据与动态运行前置仍未闭合。适用对象仅为待准备的新隔离 shadow 观察版本，不能改写旧接纳事实或授予 execute。

**20 ms 保持现有工程接纳门。** 它限制现有代码按本机 CLOCK_MONOTONIC receipt/extrapolation 计算的接纳量；当前没有证据将它解释为真实仿真主时钟误差界、端到端执行延迟上界或系统 WCET。保持原数值、原 1:1 公式及全部拒绝理由，避免改变基线比较对象。该保留理由是研究版本可比性，尚不是物理安全界的校准论证。

| 量 | 可以陈述的含义 | 不能据此推出的结论 |
|---|---|---|
| 本机 clock receipt age | 距本次收到 /clock 的 monotonic 时间；原门照常使用 | 传输前生成时刻、主时钟误差或真实 plant 接收延迟 |
| source lag / future | 源 stamp 相对当前 receipt 推算 target 的差值与原拒绝分支 | 单靠 stamp 是最新就证明状态物理新鲜 |
| 400–600 ms 区间平均 RTF | 较长区间仿真时间增量与墙钟增量之比的背景观察 | 每个20 ms局部区间严格1:1、可用RTF乘数放宽门 |
| 1:1 时间外推 | 当前确定实现和研究假设，需在来源报告明示 | 对真实时钟映射的独立证明 |
| 事后线性插值 receipt proxy | 给定未来 receipt 端点与插值假设的诊断量；用于发现接收空洞与条件不一致 | 真实主时钟边界或无延迟 ground truth |
| Witness whole tick | 包括 source JSON 生成、等待与原 tick 收尾的独立完整包络 | `whole_end - source_end` 只等于 JSON CPU 开销 |

保留旧 B4 事实：job16 实际被接纳，而事后 future receipt proxy 约 +65.23 ms，附近 receipt gap 约333.20 ms。它说明 receipt 外推与该 proxy 的条件可能不同；不能通过改阈值、删除该 job 或把 proxy 改称 ground truth 消除差异。旧完整 183 决策/163 job 包络、拒绝和无 job 全保持原身份。

未来 D1 只可声明为来源观察：完整保存全生命周期和另列事前20s monotonic测量窗；不按接纳数延长、不收尾挑段、不删域外状态。若无法观察独立仿真源生成时刻和传输延迟，输出必须写“带假设的 receipt proxy”，真实时间界资格仍 false。任何未来物理时间界主张都需要另有主时钟/生成/接收证据。

启动门仍 No-Go：当前域内可复现控制冻结来源、F5唯一旧双路publisher的精确身份/真实历史、独立shadow driver、严格source/actual-bag/Witness/owned全链与外部worker零hook argv尚待完成。本文关闭的是陈述范围，未完成M0b逐参数理由、D1动态资格、B4或execute资格。
