# 第102批：T2-B新代际正控——scoped Epoch生命周期设计

日期：2026-10-25。设计批：无代码修改、无run、无资格变化。

目标：为T2-B"新代际正控"（同run内path变更后新代提交/接纳）给出可实施、可组件验证、不触碰冻结静态任务政策的scoped Epoch生命周期设计，供实施批（103组件→104接线+owned→105审计）执行。

---

## 一、义务溯源（权威原文）

**R74-07**（[批74独立审查](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2_review_20261024_74/documents/方案A_第74批_70至73批独立代码审查与后续实施计划_2026-10-24.md) §R74-07，P2）：

> "已建立Epoch后，path/profile绑定改变会先invalidate为terminal，随后即使换成201点，propose仍先返回epoch_terminal。……不能只改101为201就承诺'旧结果拒绝后新代际恢复'。T2-B必须拆清目标：最小在途旧代拒绝可以单独证明；**新代提交/接纳属于额外生命周期义务**。若完整家族要求新代正控，就需要**明确的scoped Epoch换代设计和组件验证**，不能从70的构造Candidate正控借来owned资格。**现阶段不得无依据修改普通静态任务政策**。"

批74离线证明（直接编译冻结Epoch header）：首次201点proposal/commit成功；fresh 101拒绝；**活动Epoch失效后201/101均为epoch_terminal**。

后续绑定：批81 L275、批86复核（新代际正控❌未覆盖）、批96执行报告优先级1（"不能简单改101→201或换run_id"）、批97快速启动任务1。

---

## 二、结构事实（冻结代码，批91树）

`observer/src/shadow/task_time_profile_v1.hpp` 的 `Epoch` 类：

| 事实 | 位置 | 内容 |
|---|---|---|
| terminal即永久 | `terminal(){return !invalid_.empty();}` | `invalid_` 一旦置位无任何清除/重置路径；`propose`首查`epoch_terminal`，`commit`拒绝 |
| 绑定变更即失效 | `invalidate_if_changed` | path/profile指纹或五元组版本变化→`epoch_binding_changed`→terminal |
| 每run单实例 | Regulator成员 `reference_epoch_`（`regulator_owned_execute.cpp` L1302） | 单个Epoch对象承载整个run |
| 失效即全局quiesce | `invalidate_locked()` L578 | 同一业务锁内：activation history清空、adapter cancel、admission invalidate、candidate reset、pending reset |
| 失效后拒提交 | L911 | `propose`失败且epoch active→invalidate+`unusable_locked`→run停止推进 |

**结论**：换代不可能在现有单实例内发生——这不是缺陷而是当前"每run一次first_successful_job"政策（`epoch_policy="first_successful_job_submit_completion_target_sim_v1"`）的构造性结果。新代际正控=政策扩展，须以**新政策版本**显式声明，不得改写旧政策含义。

---

## 三、方案选择

### 选定：方案B——scoped generation包装层（Epoch类零改动）

新增 `scoped_epoch_v1.hpp`：包装器持有 `{当前Epoch实例, 只追加换代账本ledger, 代计数generation}`。**每个代际是一个完整的、不可变terminal的原版Epoch对象**；换代=在满足前置条件（§四）时构造新Epoch对象替换当前引用，旧实例整体入账本。

Regulator侧：`reference_epoch_` 成员类型换为包装器（`observer/src/shadow/regulator_owned_execute.cpp` 最小diff：成员类型、L907快照、propose/commit转发、换代事件）；`invalidate_locked` 语义不变（quiesce仍由它一次完成）。

### 否决方案（记录理由）

| 方案 | 否决理由 |
|---|---|
| A：修改Epoch类允许reset/清`invalid_` | 触碰冻结类语义；失效即终态是防复活的构造保证，类内开洞复活风险最高 |
| 101→201改点数 | R74-07已离线证伪：terminal后无论101/201均epoch_terminal；且201点属静态任务政策内容，无依据不得改 |
| 换run_id开新run | 明确禁止（R74-07/批96）：伪造跨代连续性，正控语义作废 |

---

## 四、换代状态机与前置条件（"scoped"的全部含义）

新代开启**仅**在以下条件全部成立时由包装器自动执行（首次propose遇到`epoch_terminal`时评估；条件不满足则保持今日行为——不提交、不恢复）：

- **G1 终态在册**：当前代terminal且`invalid_reason`非空（含binding_changed等既有原因）。
- **G2 已quiesce**：`invalidate_locked()`的全部效果已发生（activation history reset、adapter cancel、admission invalidate、candidate reset、pending reset——业务锁内一次完成，复用现有函数，不新增清理路径）。
- **G3 真实新绑定**：新binding的path/profile指纹与**账本内每一代**的binding都不同。同内容重发不构成新代（保持task_reference.05"相同内容重发不改语义task"既有语义，永不触发换代）。
- **G4 静态域不放松**：新代proposal仍通过原版`static_reference_population/content/speed`域检查（201点、{.05,.1,.3,.6}速度域逐点校验）——一字不改。
- **G5 跨代单调**：新代首个commit的job_id > 账本内所有代的last_job_id（job id本就run内单调，此为显式断言）；新anchor的target_sim在新绑定域内有效。
- **G6 账本只追加**：每代记录{generation, binding指纹, first_job_id, last_job_id, last_target_sim_ns, terminal_reason, anchor快照}；不可改写。

### 复活防护论证（不削弱T2-A"旧候选不复活"）

旧代候选在换代后仍被拒绝的机制与今日完全相同：(1) quiesce已清admission/candidate/pending；(2) 候选版本门校验绑定等价性（现有代码）；(3) 账本G3使旧binding永不能再成为任何代的当前绑定（propose对当前binding不等即拒，对账本binding不查询不复活）；(4) G5保证job_id不回滚。**换代不新增任何旧结果复活通道，只新增"新绑定可开新代"这一条受G1-G6约束的通路。**

---

## 五、事件与审计schema

- `reference_epoch_generation_opened`：{policy:"scoped_generation_first_target_task_time_profile_v2", generation, previous:{generation, terminal_reason, binding指纹, first_job_id, last_job_id, last_target_sim_ns}, new_binding, opened_ns}——换代即发，缺此事件的第二anchor视为违规。
- `reference_epoch_ledger`：run关闭时全账本快照。
- 逐代仍发既有`reference_epoch_committed`（first字段以**该代**为参照，事件加generation字段）。
- 审计条款（fail-closed）：G1-G6逐条绑定事件流；旧代job与新代job的id严格分界；换代前后静态域检查参数逐字节相同；无换代时的行为与今日bit一致（负控）。

---

## 六、正控场景设计（两级，遵守R74-07"组件验证"要求）

### Stage 1（批103，组件级，无ROS）：`test_scoped_epoch_v1.cpp`

直接编译冻结`task_time_profile_v1.hpp`+新`scoped_epoch_v1.hpp`（同批99 native模式）。用例：

| Case | 刺激 | 判定 |
|---|---|---|
| E1 换代正控 | binding A(201pt/.05)首propose/commit→改binding B(不同path指纹,201pt/.05)→invalidate_if_changed→以B再propose | ①A代terminal(epoch_binding_changed) ②B在旧对象上propose=epoch_terminal ③包装器满足G1-G6→开B代→B propose/commit成功、first=true(对B代)、新anchor ④账本含A代完整记录 ⑤job_id单调断言 |
| E2 复活负控 | E1后以A的binding再propose | 拒绝（当前binding不等）；账本A代不可复活；无任何anchor回退 |
| E3 同内容不换代 | 活动代重发相同binding | 不触发换代（无generation_opened事件），保持task_reference.05语义 |
| E4 静态域不放松 | 新代binding用201点外（如101点）或非法速度 | 新代开启被G4拒绝（沿用原域检查拒绝原因），不因换代绕过 |
| E5 无换代负控 | 无binding变化全程 | 行为与今日单代Epoch逐断言一致（含terminal后拒绝） |
| E6 quiesce前置 | terminal后未完成quiesce标记时propose新binding | 不开新代（G2不满足），保持不提交 |

### Stage 2（批104，owned）：T2B-GEN（T2-B boundary族扩展）

同run：path A→gen1 job提交→冻结replace动作换path B（有效静态域）→旧代在途拒绝（已证范围复述不重跑）→**gen2首job提交/接纳**→ledger完整→run正常收尾。登记为boundary scope（v4合同路径，fault声明+scoped policy声明），普通scope行为不变。预检登记/单次有限/自动重试0/失败原件保留，沿T2治理。

---

## 七、治理与不声称

- **组件≠owned**（R74-07原文）：Stage 1结论限组件级，不借owned资格；Stage 2才产生owned证据。
- 不修改普通静态任务政策（G4）；普通scope（v3合同）路径bit不变（E5/Stage2负控证明）。
- 组件/阶段资格/研究结论分别判定；M4/F6/P1/plant/硬实时false不变；生产B仍MANUAL+RC覆写。

## 八、实施批计划

| 批 | 内容 |
|---|---|
| 103 | `scoped_epoch_v1.hpp`+组件harness E1-E6（预登记→native构建→单次运行） |
| 104 | Regulator最小diff接线（成员/快照/转发/事件）+T2B-GEN owned run（boundary登记）+无换代负控run |
| 105 | `audit_t2b_gen.py`逐条款审计（G1-G6/复活负控/域不变/账本）+批86登记状态更新 |
