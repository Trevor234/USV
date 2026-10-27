# 研究创新登记簿（单一累计）

创建：2026-10-26（批123）。规则：已证事实与衍生想法严格分开；每条附证据指针；不逐论文建文件。

## 已证事实支撑的创新（有证据链，可测试复用）

### I-2026-10-25-01 scoped Epoch代际生命周期（同run绑定变更恢复）
- **内容**：不可变版本注册{generation, p_global/binding}+prepare/commit两相（互斥，无半提交态）+只追加换代账本+G1-G6前置（终态在册/同锁quiesce/账本全异/域不放松/跨代job单调/账本有界）。冻结Epoch类零改动——每代是完整的不可变terminal实例，生命周期在包装层。
- **关键性质**：允许mid-run绑定变更恢复而不开任何旧结果复活通道（quiesce清场+版本门+账本不可回锚）。
- **证据**：批102设计→103组件E1-E6 6/6（四负控）→104 owned 13/13（同run gen1→gen2、job 1-27继续、NEG普通路径bit不变）→105审计20/20；后续119 S4经它实现resume NW接纳。
- **复用**：`experiments/scheme_A_M4_t2b_gen_impl_20261025_103/.../scoped_epoch_v1.hpp`（104/119树含regulator接线diff）。

### I-2026-10-25-02 B2'恢复stamp配对映射（单调恢复的投影连续性）
- **内容**：`S_next = S_last_published + min(T_next − T_last_published_target, cap<5s)`——(S_last,T_last)取最后**实际发布**配对（非命令时间/非接收时间），恢复首步仅应用一次。结构性消除"静默期输出投影外推→恢复后源域回拉→工程历史逆序→fail-closed停摆"链条（L844触发类）。
- **证据**：批118矩阵16/16（无hold路径与原公式逐位一致+三变异被捕获）→批119 owned R4覆盖。
- **复用**：`..._rnw_s2_b2_20261025_118/.../resume_stamp_mapping_v1.hpp`（生产/测试共用）。

### I-2026-10-25-03 acados运行时p_global setter路径事务（单capsule模型切换）
- **内容**：`set_p_global_and_precompute_dependencies`+reset在已使用capsule上切换模型版本，与全新构造实例**逐位等价（diff=0.0）**——有限模型事务不需codegen、不需实例重建；precompute与setter捆绑=天然原子单元。
- **证据**：批108 F6-1（生产AcadosBackend对拍）6/6→批109审计11/11（含生产库SHA基线）。
- **复用**：`..._n4_f6_impl_20261025_108/implementation/model_transaction_v1.hpp`。

### I-2026-10-25-04 角色侧survivor注入（cleanup失败监督的真实进程组事实）
- **内容**：被测角色的SIGTERM处理器fork一个忽略INT/TERM、自带硬deadline、关闭继承fd的可杀survivor后自身退出——使`killpg(pid,0)`探测到**真实的**组非空（非模拟），全程不制造不可杀进程。
- **证据**：批100 C12（真实信号梯[INT超时,TERM]→具名cleanup_failed→无新spawn）→批101审计复算。
- **复用**：`..._t3c_impl_20261025_100/.../synthetic_source_m4_t3_survivor.cpp`模式。

### I-2026-10-26-05 同Job完整链纯审计判据（反事件计数假通过）
- **内容**：接纳正事实的判据=同一Job的完整真实链（submit→accepted候选注册→accepted Decision∧control_source=candidate→真实API pair→Applied），按流序绑定；事件存在性/计数/rc0永不构成通过。旧候选拒绝与"无在途"分开（空集合不冒充证据）。
- **证据**：批115复审证明旧runner假通过风险→批117矩阵18/18（含两次真实失败run负控）→批121审计重放复现。
- **复用**：`..._rnw_s1_pure_20261025_117/implementation/rnw_audit_v1.py`。

### I-2026-10-25-06 阻塞publisher确定性队列压力测试
- **内容**：picked计数器证明drain已阻塞在锁外publish→洪泛时队列填充完全无竞争→accepted=capacity+1精确可断言。
- **证据**：批99 Q1d 14/14。

## 衍生想法（未验证，待立项）

### D-2026-10-26-01 B0输出线程拥有的时钟纪元过渡（批115 S3草案）
真实clock epoch跳变后的恢复：失效意图由clock线程提交、输出线程在pair边界处理、steady API事实不可撤回、sim历史独立资格失效/重建、确定性交错反例集。**未实施未证明**；仅当纪元跳变恢复成为需求时立项。

### D-2026-10-26-02 复审驱动的纠偏-执行闭环作为方法论素材
本会话resume NW弧：初探归因（批113/114）→独立复审证伪（批115：跨run混比/L844真因/接口错配）→S0-S4纪律执行→闭合+链审计。五弧证据链（T3/T2-B/N3/F6/RNW）+该闭环或可成论文方法论/案例素材——**未写作**。

## 无新创新日志
（暂无——本登记簿创建于批123，此前会话未按此簿登记；历史批次的创新若需补录另行整理。）
