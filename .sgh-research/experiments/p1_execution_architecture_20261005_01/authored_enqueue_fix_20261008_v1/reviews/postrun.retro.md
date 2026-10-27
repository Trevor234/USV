# 首次 DecisionEnqueue 失败共享槽失效：本轮复盘

日期：2026-10-08。这是 ROS 控制工程批次；目录沿用 control-postrun-retro 的归档规范，不把结果称为 EDA PPA。

## 实测结果与分类

机制分类为代码退出顺序缺口：第一次 Decision Sink 返回 false 后可能零动作直接退出，原版本缺少同拍共享清理。新版本先在业务锁内停态并调用既有 invalidate_locked，再判断同拍退出。实际源链接测试调用发行 tick_loop 共用的 finish_tick；普通与诊断各10项正例通过，旧两源的关键负例各RC1，槽2/candidate/pending仍存在，证明旧缺口被检出。

诊断容量1的真实队列拒绝测试中，第一次停止来自 DecisionEnqueue/obs3，真实 phase5 槽2/候选true/pendingtrue，phase8 槽0/false/false；没有下一 Tick。两采样差639ns仅为这个合成分支记录差，不作实时上界。正式日志容量512不变；capacity1/ordinary capacity0只存在测试构造，发行构建不含测试宏或新参数。没有完整 ROS 图首次失败顺序压力实验。

唯一实际 ROS 正常对照 p1_enqueue_fix_normal_20261008_03：10.002600190s，Job/Candidate/Decision51/51/52，接受50；source generated/emitted1977/1977、drop0；真实MCAP全owned输入653条/clock、odom、imu，path/profile14，逐项对账通过。runner/base/delivery/comparison均RC0，四个owned角色RC0且无残留，旧2626资产无漂移。计数不是窗口裁剪；static零夹具、无物理publisher不证明真实plant、变化率或双路预算。

工具与夹具缺陷分类也保留：首轮重复ID导致真实去重拒绝，修正为新ID后在tests_v2重新验证，原失败XML/console/build_result不覆盖；normal封装v1缺回收身份表、v2误引旧政策路径，均在spawn之前拒绝，v3修正路径和新regulator回收pins后才运行。两次拒绝不是两个完成的正常测量窗。

## Evidence Lock 与限定

原B0/B1/C0/R5资产保留，新源码/发行bin/测试bin/Witness/实际bag/严格检查器输出/owned台账另归档。普通与诊断源SHA为7abfaf03722499bbe9d28da19d050404667682ff3918813d2133b98dadfd8477、a38d563a52570f11da9e68b5743c6c1989b26e77508620358ad3e402bd0a8a3b；新bin分别50e2af0904d5635e9a698eb98b17364f8f6b247c3668fd7d9e94c82fd4c98c1a、dc43fa95ab9f4cfefa6836016a10e90a6523fa6dd9b9c6d1f22805dbf7fb3eb6。

默认ROS工作空间source/install受旧guard保护，仍旧版；本次改动位于独立实验版本，下一资格评审明确用新路径。历史R5压力资格不自动转移到新源码。pending已空与add成功测试分别只覆盖容忍空槽/不误停；准备已pop后的最终提交门及phase去重为源码审查，不改称完整动态竞态验证。collector摘要对源完整性的保守false不是独立strict source/bag验收结果；完整性以单独门和实际输入指纹为准。

## 下一步评分与停止条件

| 选项 | 新信息收益 | 成本 | 风险/偏差 | 推荐 |
|---|---:|---:|---|---|
| B4来源与新版本资格矩阵：区分预算/样本/推导/unknown，列新源压力待重验与B5依赖 | 9/10 | 中 | 最少新增仿真，能防止历史资格错继承 | 首选 |
| 立即重复本次20正例与正常零夹具，无新变量 | 2/10 | 中 | 反复计数无新增机制 | 停止 |
| 直接覆盖默认install并进入物理execute | 1/10 | 高 | 破坏冻结且B4/B5/M4未满足 | 不晋级 |

本轮最小代码分支目标已满足，停止重复注入。B4可以开始来源整理；B5前须针对最终统一版本复核压力/恢复/关闭/部分发布等政策和证据适用性，再决定切换默认安装。M0b正式冻结、M4/F6/P1及physical execute继续false。任何下一运行都重新核对真实host、assets与所有owned身份。
