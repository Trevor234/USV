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


## 2026-10-26 第126批审核性修订

以下修订替代前文同ID的**当前性质与复用范围**；前文保留为历史，不再作为现行验收结论。已证工程事实不自动构成学术新颖性。

### I-2026-10-25-01 当前认定：scoped Epoch代际生命周期

撤回混入本条的p_global模型事务与“不开任何复活通道”的普遍承诺。Epoch的绑定生命周期与模型capsule事务是两个机制。124已证实旧Proposal可误提交、ledger测试不独立。126补入实例/代际/serial/预期binding认证、wrapper侧消费状态，移除公开raw commit并接到真实Regulator的既有临界区；15个组件case、4个定向变异及实际Regulator编译通过。原6 case的32条断言保留。新token接线没有新owned运行证据，104/119旧正例不能替代它。

- 源：`/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/implementation/author/observer/src/shadow/scoped_epoch_v1.hpp`，SHA256 `39ac3a5b30a3c5ffee381974bded71ed165c19502ecc3753207b9ff21c240f77`。
- 源：`/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/implementation/author/observer/src/shadow/regulator_owned_execute.cpp`，SHA256 `5a86e3e90ff9eb6611970b360728214076b3d54b1a09691038d764f9da2c72c1`。
- 本轮证据：`/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/evidence/E09/attempt02/Epoch`。

### I-2026-10-25-02 当前认定：B2恢复stamp配对映射

“结构性消除投影回退”改为有限条件下的实际发布配对映射。126检查int64加减、显式cap和错误结果，并在Fixture发布前检查正常域与ROS时间范围；算术cap仍为4.9s，5s阈值不变。原16项算术正控保留；11项边界/限制case及2个实际helper变异通过。4ms接收错相回退和1.1s长hold回退仍成立；不能保证任意DDS时延或长hold下的正常恢复。

- 源：`/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/implementation/author/fixture/resume_stamp_mapping_v1.hpp`，SHA256 `678a73d849bc0ba41cf8aef4ad6d25f5b8fbcb5552d7098dd1f408280857fa9f`。
- 本轮证据：`/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/evidence/E09/attempt02/B2`。

### I-2026-10-25-03 当前认定：有限p_global模型事务

“逐位等价/天然原子”改为固定M0/M1、固定输入、单所有者串行调用下，u和前6维X在1e-8内的有限数值对拍；观测差值0.0不推出任意输入逐位等价。126补UNCOMMITTED/READY/PREPARED/FAULTED、非零代际、有限值/形状检查、setter/reset结果与所有者检查。19个case和3个变异通过；链接层观察真实C solve入口。失败adapter只证明包装层状态策略，未证明生成setter内部错误传播。比较对象是此次钉住的安装库，不是当前dirty生产源码。完整mixed身份、真实tick激活、生产fallback和warm失败路径仍待集成。

- 源：`/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/implementation/standalone/model/model_transaction_v1.hpp`，SHA256 `4beb4306ec94e5bc5e0e84dc735b0aec1cc2f59c1e3c93eec4ca325bd68c5bcf`。
- 本轮证据：`/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/evidence/E09/attempt02/Model`。

### I-2026-10-25-04 当前认定：有限survivor与cleanup失败事实

SIGTERM handler只设置stop，fork发生在main退出循环后的关闭路径。实现只关闭fd3—255，未处理fork失败；3s是用户态自退出目标，不能写成内核绝对硬界。C12的父rc0/组非空/cleanup_failed与C3的组空按原始Driver日志复判保留；此次无新信号、无survivor运行，不认证通用清理器。

- 本轮证据：`/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/evidence/E09/attempt02/History`。

### I-2026-10-26-05 当前认定：同Job链审计

“按流序绑定”改为按完整身份及逻辑时刻绑定。126发现早期修订仍遗漏Worker/Stored，随后补齐四类完整类型：Job44、Candidate14、Decision57、Applied39字段；实际Job7/seq18、真实C调用1次及四类全人口对账通过，缺证据/错echo/错右通道/错时序等负例被拒。Source typed-CDR摘要与Stored原始CDR不等，未声称全字节等价；完整字段按类型支持和冻结emitter复算。无旧在途仍为not_covered，不能充作拒绝证据。完整run接受是本RNW家族的有限结论，不是M4/P1资格。

- 源：`/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/implementation/audit/rnw_audit_v3.py`，SHA256 `dcfabc5e14cb2275c232e083c5fe1de3786e572d4b07462a1c1d5a6d77e7a8ee`。
- 源：`/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/implementation/audit/stored_control_reader_v1.py`，SHA256 `3bc69209f2c4ac5b7543c263e4b3f5c542aed744ed4217a7c1b6fe5e4786add5`。
- 本轮证据：`/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/evidence/E09/attempt02/RNW`。

### I-2026-10-25-06 当前认定：Q1d确定性压力与Q2身份修复

Q1d受控阻塞下capacity+1性质保留，不能外推为Q2身份正确。旧Q2保留350/303重复身份反例；126按值捕获base，逐producer及局部序号做offered/accepted/rejected分区、发布与落盘多重集对账。5个case、ASAN/LSAN和实际引用捕获变异通过；ptrace中的LSAN工具失败原件保留，未关闭sanitizer换取通过。

- 源：`/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/implementation/tests/test_t3_queue_pressure_v2.cpp`，SHA256 `6de27d3e87af78f48e0c710a80598beaadbca638ea4cf0bbe8396f1e293835d9`。
- 本轮证据：`/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/evidence/E09/attempt02/Q`。

D-2026-10-26-01仍未实施/未证明；D-2026-10-26-02仍未写作。M4/F6/P1/plant/硬实时全false，生产B维持MANUAL+RC覆写。

过程符合性单列：126的E04接替前发生封存文件误写并恢复，保留为历史FAIL_STOP；当前hash一致不能改写该事实，功能回归通过不等于125执行合同全部签收。
