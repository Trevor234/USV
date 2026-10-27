# 第125批：严格执行计划

2026-10-26。本批交付计划，未执行整改。

- 主文件：[严格执行顺序与逐步验收计划](documents/方案A_第125批_严格执行顺序与逐步验收计划_2026-10-26.md)。
- 机器可读约束：`postrun/execution_plan_v1.json`；勾选表：`postrun/execution_checklist_v1.tsv`。
- 依据：第124批代码复审、10项具名问题、真实正例、反例和固定合同。
- 固定执行顺序：E00基线 → E01 Q2 → E02 RNW审计 → E03实际准入 → E04审计105 → E05 Epoch → E06模型事务 → E07 B2 → E08 T3声明 → E09组合回归 → E10登记修订 → E11分项集成评审输入 → E12封存交付。
- E00—E12均为NOT_STARTED。后续“执行本计划”默认仅启动本计划约定的离线段，不自动进入生产落位或新owned。
- 本批研究实现修改0、生产修改0、创新登记簿修改0、ROS初始化0、owned运行0。
- 现有未提交改动、冻结文件和失败证据保留；M4/F6/P1/plant/硬实时全false。实船B维持MANUAL+RC覆写。

计划与基线核对结果见`evidence/final_verification_v1.json`。MPC交付是否完成，以`evidence/delivery_receipt_readback_v1.json`为准，不能从文档存在推断步骤执行完成。

下一动作：收到执行指令后，先按E00建立唯一新执行包、冻结输入和白名单；不得直接跳到代码修改或owned运行。
