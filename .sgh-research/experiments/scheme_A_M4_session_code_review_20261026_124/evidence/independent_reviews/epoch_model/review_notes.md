# 102–109代码与I-01/I-03创新登记独立复核

2026-10-26。范围：102设计、103真实ScopedEpoch头/6 case、104接线/owned流/verdict、105审计、107设计、108真实model_transaction头/6 case、109审计、119复用头、123集成清单。只读原件；私有/tmp内编译并执行了两个小型native反证以及删除ledger守卫的定向变异；无ROS/owned。

## 先讲清楚它们在做什么

Scoped Epoch解决的是“任务参考的时间锚失效后，同一run还能否以新身份重新建立锚”。冻结Epoch本身依旧是terminal后不可复活；包装层退役旧对象、保留账本，再以新对象承载下一代。已有实际owned POS流出现generation1→2、task2→6并持续接受新Job；NEG无换代正常结束。这是实质进展，不能因审计缺陷说成没有运行。

ModelTransactionSolver解决的是“保持acados生成结构不变，只更换运行时30维全局数值参数，并分别保存不同模型版本的warm-start”。108确实调用真实setter和真实acados_solve，在固定M0/M1、固定直线参考、固定状态序列上，首次切换后的控制与六维预测状态相对fresh M1得到数值差0；回切M0的下一控制也差0。证据支持数值路径可用和这些有限正例，不支持任意模型/任意输入/并发/故障路径普遍等价。

## 实质发现

### EM-01 P2：generation=0能绕过第一次提交直接执行未应用的模型

文件 `/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_n4_f6_impl_20261025_108/implementation/model_transaction_v1.hpp`：register_version L68–76未限制零；solve L95–102只比generation与current_；current_ L171默认为0。

真实离线probe：构造对象，register_version(0,M1)，从未prepare/commit，solve(0)仍executed=true且finite=true、commits=0；相对fresh M1的控制差0.24586375865476343。这意味着模型标签声明M1，实际capsule仍为构造默认模型。输出 `/tmp/review123_epoch_model/model_result.json`。修法：非零代际、显式has_committed/optional current、提交成功前拒绝全部solve；三种入口分别负控。当前108登记仅用1/2未踩中，所以不推翻其已有正例。

### EM-02 P2：ScopedEpoch公共commit接口缺少Proposal代际/预期binding认证

文件103 `.../observer/src/shadow/scoped_epoch_v1.hpp` L71–92及L136–146；119同头L75–96及L140–150。

真实probe：保存gen1首Proposal(A)并commit；失效到B、quiesce；propose(B)打开尚未commit的gen2；此时以更大job_id重放旧Proposal(A)，commit返回true，gen2 anchor回到ledger已经退役的A。原因：新Epoch尚无anchor，原Epoch::commit只看p.first/valid，不认证wrapper代际；wrapper也不认证p绑定属于本次opened binding。输出 `/tmp/review123_epoch_model/epoch_result.json`。

现Regulator只有一个prepare线程，最终s.version门又位于同一失效锁内（104 regulator_owned_execute.cpp L934–943），因此**不能据此宣称已保留owned发生候选复活**。但包装器被登记为可独立复用、且声称“不开任何复活通道”，则这是集成前必须补上的接口保证。修法：Proposal包含wrapper generation/open token及expected binding digest；在同锁commit匹配，拒绝旧token且状态不变。

### EM-03 P2：105审计有恒真条款，不能把20/20解释为G1–G6独立完整证明

`/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2bgen_audit_20261025_105/implementation/audit_t2bgen.py`：

- L74–78调用clause(cid, obligation, ok)时，真实比较布尔放进obligation，说明字符串放进ok；非空字符串永远真。把比较强制为false仍记录passed=true，已用原函数AST抽取离线复现。
- L122–125比较tuple首位是常量1和2，故无论实际绑定相不相同必然不等。104 verdict_t2bgen_v2.py L68–74同样把epoch generation纳入binding，而前置已要求[1,2]，不同绑定判据因此恒真。
- 修法：clause将ok变为keyword-only且type(ok)is bool；绑定身份独立比较run/boot/contract/nominal/五元组/path/profile，不能混进新对象自身generation；必须有反例变异。

输出 `/tmp/review123_epoch_model/audit_false_pass_result.json`。当前真实流task2→6确实不同，不因审计错误自动作废；结论应区分“实际正例存在”与“审计能可靠拒绝反例”。

### EM-04 P2：6个组件case未测试真正的退役ledger守卫

103 test_scoped_epoch_v1.cpp L110–126的E2是在**gen2仍active时**以A propose，命中原Epoch的binding不等门，未进入terminal时try_open的ledger循环。

私有副本删除ScopedEpoch L113–116整个退役ledger查重循环后，原6 case仍32/32全过。输出 `/tmp/review123_epoch_model/mutation_ledger_result.json`。所以“四负控”不能解释为防复活所有层均已受测。最小补证：A→B已commit→令B terminal/quiesce→尝试再以完整旧A绑定开代，必须以ledger原因拒绝；同时新增EM-02旧Proposal重放反例及max_generations边界。

### EM-05 P2：事务“互斥、天然原子”表述超出代码保证

108 model_transaction_v1.hpp L68–102、L165–171无mutex/atomic/owner-thread检测；prepare/commit/solve共享bool、maps、capsule。现有F6-2只是同线程prepare后串行调用solve被拒，证明的是有限状态门；F6-3是在测试循环中安排切换，没有真实tick/token接口。

生成C源码 `/home/trevor/USV/usv_mpc_ws/src/usv_mpc_cpp/acados_generated/acados_solver_usv_dyn_nmpc.c` L1029–1046显示setter修改fun->args指针，令fun->res指向capsule global_data，再执行CasADi函数；没有锁/回滚/原子发布语义，且忽略casadi_fun返回并固定返回0。setter与precompute封装在一个函数，不等于并发原子事务。

建议契约明确“单Worker所有者线程独占capsule；版本提交与solve在该线程按队列串行执行”，而非盲加锁或允许运行时线程任意重入。之后才把控制面prepare请求通过不可变消息交给所有者消费。提交失败必须有abort/terminal quarantine，reset返回值也需检查（L91–93先标current后忽略reset结果）。

### EM-06 P2：F6的mixed与完整行为等价尚未覆盖

107设计说prepare绑定p_global与逐阶段p、拒绝mixed戳；108接口只有register_version(generation,p_global)，solve(generation,state,ref)。ref无版本戳/哈希，F6-4 L164–178只拒绝stale、unknown与同代不同p_global；不能验证模型/参考混配。接入Worker时应绑定完整Job模型身份与reference身份，结果Candidate回带模型身份，Regulator在激活点验同一Job。

“逐位等价”也需收窄：F6-1 L107–110检查max_abs_diff<TOL(1e-8)，保存的数值碰巧0；比较的是u及X.topRows(6)，不是完整capsule内存或全X8/U轨迹逐位memcmp。F6-5 L199–202回切只比较下一u，不比较X/U/warm账本全部元素。可以写“固定正例数值差为0”，不宜写“任意模型切换逐位等价”。

108 wrapper失败路径L140–154直接返回finite=false；生产AcadosBackend失败路径 `/home/trevor/USV/usv_mpc_ws/src/usv_mpc_cpp/src/acados_backend.cpp` L255–262、L284–292、L310–317调用safe_fallback并更新fail_count。因此复制成功求解路径后不能直接替换生产类而声称现行全部行为不变；应共享参数setter/packing，保留生产失败策略、warm管理、异常与计时逻辑。

### EM-07 P3：创新与兼容性表述要分清

- `.sgh-research/research-innovations.md` L8把p_global不可变注册和prepare/commit两相写进Epoch条目；ScopedEpoch没有模型事务接口，应拆开I-01/I-03。
- 原102 G3写“每代指纹都不同”；实际Binding::operator==包含五元组，104与119合法使用同path/profile但新task/schedule。Probe已证同指纹只变schedule即可开gen2。这是RNW所需政策扩展，应写“完整binding身份不重复”，不能拿“指纹不重复”证明。
- 104 regulator接线L914–918无runtime scope开关，整个派生ELF替换为新生命周期；NEG只是无变更轨迹不换代，未对旧ELF重放同一输入比较，也未证明旧静态政策在变更时仍保持拒绝。生产集成应显式opt-in新policy/schema，旧policy负控保留terminal语义。
- 102设计的run-close reference_epoch_ledger事件未接入；104 POS/NEG均0条，1314–1323仅发opened事件且不含完整previous anchor/binding快照。内部ledger是有界私有vector，但审计无法只靠run-close账本完整重算全部代，应补schema/收尾事件或正式修改审计证据合同。

## 代码质量评价

优点：Epoch旧类未改，封装小且容易定位状态机；相同锁保护失效与最终提交，真正owned正例确有持续接纳；模型事务直接驱动真实C API并与生产backend对拍，成功路径并非mock。失败原件、先设计后组件再owned/审计、资格分层保存良好。

不足：验证器有恒真比较和参数位置错误；负控有“测试在更外层就拒绝，内层守卫删除仍绿”的覆盖盲点；复用组件的输入身份与生命周期边界不严；模型接口与文档比实际代码多承诺了mixed、并发互斥、固定tick激活和完整等价。总体是**有价值的实验验证实现，尚不是直接拷贝进生产的完成组件**。

## 最小生产集成计划

1. 先修纯审计与组件契约：EM-01/02/03/04作为少量确定性负控，补generation token/非零已提交状态/严格bool断言；修创新登记表述，不动旧证据。
2. Epoch候选单独设计opt-in政策与参数schema，明确full binding、允许重开原因、8代上限、完整账本事件和source失败策略。新派生树内只落这一项，旧policy在变更时仍拒绝，新policy才恢复；无需因此重复所有历史owned。
3. model事务候选先抽取生产Backend共享数值setter与参数packing，定义唯一所有者线程、prepare/commit/abort、完整Job身份和激活tick。新增初始未提交、零/NaN、mixed、提交/reset失败及失败fallback对拍；原成功6 case保留为有限正例回归。
4. 两候选分开freeze、分别负控，不捆绑B2映射与模型事务。组件通过后才有意义做各自最小owned。GP数据采集/plant/硬实时没有因此变成组件修复前置，现所有阶段资格仍false。
