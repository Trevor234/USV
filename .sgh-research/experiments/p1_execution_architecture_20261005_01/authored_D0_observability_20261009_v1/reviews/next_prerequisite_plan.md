# B4-D1 前置闭合最小计划

日期：2026-10-09。状态：计划已创建，尚未执行本计划的新shadow入口、场景修改或D1运行。承接本轮D0来源观察实施与验收。

**下一步先恢复可用工况正文，并建立受控shadow观察入口，再决定是否进行一次20s来源采集。** 当前D0专用诊断入口保留no_output+diag5硬门；静止机制结果不能直接授权F5 shadow。原≤1.2m/s域保持待冻结，20ms保持待论证工程接纳门。

## 1. 只读恢复工况与版本依据

输入：D0来源契约、B4完整183决策/163job分析、F4/F5摘要及源目录登记、现有3067父守卫和D0新封存守卫。按这些已登记路径查看Ubuntu既有F4/低速/circle产物目录和原manifest，不扫描全盘或改写旧资料。

1. 先列正文是否存在、实际大小/SHA、原context/boot/source/bin/contract/输入流身份及测量区间。区分“本地未保存”与“远端不存在”；只传有限正文/摘要，完整原bag保留原位并由严格reader读取。
2. 对潜在低速段计算六维体速sqrt(u²+v²)、实际曲率和来源时间；不能用F4的min u=1.166233单值证明六维体速在域内。分别列straight、turn、mixed及非零skew，重复horizon不作为独立样本。
3. 核对F5冻结参考/profile/fallback和真实速度为何可能不同。先说明跟踪、任务转换、单位/坐标及起步/稳态条件，不能以调低参考值自动推出实速≤1.2。
4. 已有旧正文可描述旧工况，但旧源码缺失的validation快照不能回填。没有当前可重现的域内输入条件就No-Go；另写明确的受控参考/工况修订及比较影响，不能默认扩为1.3或launch后选幸存段。

输出：existing_domain_sources.md/json，逐来源身份、恢复状态、可用段/不可用理由、可复现输入条件和仍缺分组。停止条件：回答是否有足够的域内来源和可复现输入；无依据时记录缺口，不无限追加历史查找。

## 2. 新建明确支持shadow的观察入口

输入：已封存D0源码/helper/contract，以及当前普通源码和AppliedControl publisher链。只创建新的隔离版本；当前D0、普通源、默认build/install、正式ROS消息、Witness布局和旧证据保持原身份。

1. 先做入口/模式差异表：专用constructor、full-contract loader、零/非零fault hooks、synthetic anchor、legacy AppliedControl订阅/身份、ready barrier、source/bag/Witness reader和publisher graph检查。共享loader接受shadow不等于整个入口已合格。
2. 定义独立研究观察入口的明确允许模式和拒绝门：只支持预声明shadow；execute在创建物理publisher之前拒绝；所有delay/native/prepare/tick/logger-pause hooks为0，并拒绝非零注入。必须使用冻结F5旧publisher提供的真实双路publisher命令历史；shadow不得继承no_output synthetic零锚点例外。
3. 复用D0同DecisionJSON观察 schema，保持原控制/接纳/时间公式、reason和fallback。字段负载与真实tick结束继续用独立Witness全包络记账；有界事件数不当作已证明字节/WCET上界。
4. 先针对模式拒绝、输入/history缺失、legacy身份、观察/null/full6、业务失效与关闭分支做有限测试；严格reader对新身份单列，不能放宽source/bag/owned/Witness门。只改一个constructor if不足以完成此项。

输出：shadow_entry_contract.md/json、新源码/helper/bin和工具SHA、针对测试与版本适用表。Go门：所有入口差异有处理依据、0新物理publisher、所有fault hooks0、legacy双路publisher链真实可认证、守卫无漂移、owned清理完整。旧R5压力结果只作谱系；新统一版本受影响压力/恢复/关闭资格仍单列pending。

## 3. 时间政策与一次D1的事前声明

1. 20ms首先解释为工程接纳门，分列receipt age、source lag/future、400–600ms平均RTF、短时接收空洞、1:1映射和事后proxy。保留旧job16实际接纳而future receipt proxy约65.23ms、gap约333.20ms的事实。
2. 若要声称真实时钟误差界，提供仿真主时钟/源生成时刻与延迟证据；没有这些证据就只作有假设的proxy观察，不用同一1:1公式自洽或扩大slack“证明”20ms。
3. 仅在前两节Go及可执行域/政策前置完成后，声明一次20s来源测量窗及实际monotonic起止；准备和收尾分别规定有限上限、失败回收和证据保留。旧F5是唯一双路物理publisher，新regulator只shadow；整场确有旧物理发布，不能把“新入口0出口”写成“整场0出口”。
4. 固定F5/nominal/plant/参考/源频率与mixed规则，明确这一次能够覆盖及不能覆盖的域。完整owned生命周期全保存，测量窗另列，全接受/拒绝/无job/域外/空洞全保留；不按接纳数延长，不临场改阈值、模型、权重、GP/PPO或plant。

输出：preflight_reflection、D1_predeclared_policy、源/实际bag/Witness/CPU与RTF背景/owned账本、strict source观察与全生命周期报告、postrun retro。第一轮回答声明缺口就停止；只有新具体机制或不确定项才另写计划。

## 4. 验收与当前资格

- [ ] 既有工况正文/可复现域内条件及仍缺分组已核验。
- [ ] 隔离shadow入口及模式/legacy/history/0fault/观察链验证完成。
- [ ] 时间工程政策与真实界声明范围闭合。
- [ ] 一次D1事前Go，或书面No-Go及明确所缺输入。
- [ ] 一次来源结果按声明验收或保留失败；没有“因为运行完成就冻结参数”。

后续B4需逐参数选择理由和有限域依据；再将最终统一版本的受影响压力/恢复/关闭资格及B5实际freeze证据闭合，才能推进M4唯一新物理出口与F6/P1。当前B4/M0b/B5/M4/F6/P1/execute仍未闭合。

成本与风险：正文恢复受原产物可用性影响；新入口编译与有限管线验证有时间成本；观察负载可改变调度和logger压力。先查正文/模式以避免没有域依据的整场重复采集；任何新物理工况改动必须在单独具体方案中说明与首选A公平比较的影响。
