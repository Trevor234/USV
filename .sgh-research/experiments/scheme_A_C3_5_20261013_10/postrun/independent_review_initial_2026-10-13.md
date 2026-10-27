# C3.5 独立审查：首轮合同与阶段依赖

日期：2026-10-13，Asia/Shanghai。只读审查 N11 正式接受实现和 N10 有界原件；没有修改业务源码、冻结资产、原预期、实际记录，也没有启动 ROS 节点。

**首轮固定合同可接受当前 14 个有界组件原件，但注册依赖与闭包人口尚缺独立语义门，修订前不能称完整正式接受合同。** 发现一个 P2 问题和三个需要直接纳入主闭包的外部输入。已及时通知 Root；首轮合同、通过结果和本次反例应保留。

## 1. P2：注册了任务，但没有固定必需依赖和闭包人口

首轮 `check_acceptance_v1.py` 的 `validate_contract` 固定了 14 个任务及各自工具、数据集、argv，但未固定 `identity_pins`、`record_pins`、`required_components`、`phase_requires`、`job_rule_adapters` 与 `deferred_rules` 的完整人口和逐值含义。`evaluate` 第 65～68 行因此会把空 pin 集声明为 identity/record passed；第 89 行则完全消费合同给出的依赖矩阵。

在原合同的内存副本上，删除全部 identity/record pins、将 component 必需项缩为 `identity_closure`、将四阶段必需项都缩为 `identity_closure`、删除预算 adapter 或删除 deferred 人口，均能通过 `validate_contract`。通用 `assess` 在 identity=passed、normal_atomic=failed 且弱化必需项的输入下返回 component=true，并将四阶段的 status/all_required_passed 标为 passed/true；qualified 仍 false。通用 `assess` 正确消费所给依赖，因此应修正式合同注册语义，不能靠修改它的通用组合含义掩盖缺项。

直接更改原合同字节并继续提供旧 SHA 会被拒绝。本问题针对“整体修改语义、重新计算候选合同 SHA”的独立接受门：SHA 证明输入字节身份，不能自行证明新依赖矩阵完整。证据：[首轮内存语义反例](./independent_review_semantic_attempt01.json)，绑定合同 SHA `6fb11afaf7c0372792ff78d2980c3b40605e16cce7b10e1c598843ea01940382` 及审查时三个 Root 源文件 SHA。

建议新修订以独立固定 registry 登记外部实际身份/记录人口和 SHA；Root 可变源码用单独完整注册集合避免自 hash 循环。固定 required、phase、adapter、deferred 的完整键和值；生成器从注册矩阵生成合同。新增修订保留首轮输入和失败反例。

## 2. 主闭包需显式包含的外部消费文件

从首轮子报告中的实际 input/path+SHA 核对，以下三条被消费但未列入主 Reader 的 identity/record pin 人口：

- `/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_v13_resource_20261007/p1_shadow_contract_v5.json`
- `/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_4_20261013_09/C_lease/preregister_v1.json`
- `/home/trevor/MPC/scheme_A_config_identity_20261011_04/preregister/formatter_corpus_contract_v1.json`

子工具各有固定 expected SHA 检查；不能称这些完全未认证。主正式闭包仍应显式纳入，提供所有实际消费固定输入在整次接受前后的统一核验。RMW header 与其余首轮子报告引用路径已在主 closure 中。

## 3. 已确认正确的边界

实际工具/数据集 argv 的变换被注册门拒绝。四状态接受门拒绝 bool、int、null、集合以及 `not-run`/大小写变体；报告结果要求精确 bool，subprocess returncode 要求精确 int，bool 冒充 0/1 被拒绝。Reader 逐目录 nofollow，读中校验 FD/最终名字身份、总文件/字节/时间预算，整次接受后重读 hash；四阶段 qualified 和所有研究资格被 bounded profile 强制 false。

本次仅运行这些内存反例，未重复 14 个完整 job。首轮全部 job 的实际运行由 Root 的 `acceptance/full_attempt01` 提供，不能将本次内存反例计作实际 ROS 运行。

## 4. 从主方案到下一阶段的必要审查清单

| 层次 | 必要条件 | 当前证据及状态边界 |
|---|---|---|
| 当前 C3.5 bounded component | exact 新工具身份、传递 helper 路径/SHA、当前 source/bin、完整 raw/typed/storage/source/config/close、四状态与完整注册矩阵 | 可重放 N10，有具体合同修订待补；不恢复旧 shared-v2 四身份 |
| B4 | 当前参数选择理由、支持域与域外拒绝、当前 anchor 执行契约、版本适用压力/恢复/failed-close | ASCII/finite 配置及 4s shadow 是有限组件；21 anchor_mismatch、唯一关闭尾部 accepted 不闭合当前动态执行合同 |
| M0b | B4、当前动态20s/turn/mixed、明确有限时钟/预算假设与域外处理、恢复/失效政策 | 工程观测与最坏 WCET/真实 Master Clock 分开；unknown 不写零，不要求凭空宣称物理硬实时 |
| B5 | M0b、统一真实 execute/close/recovery 不可变合同、source/bin/模型/配置/工具/证据绑定 | 当前合同只接受冻结 shadow 原件，不能直接升级正式执行版 |
| M4 | B5、新执行源/bin、F5 owner 退出与唯一双路 regulator owner、实际非零/部分 publish、rho/gap/budget/反馈/关闭 | 未接管；shadow proposal `publish_success=[false,false]` 不是发送命令，更不是 plant 接收 |
| F6/P1/研究 | 依次完成实际接管、有限模型/执行事务及候选一致性；后续 P2 实际备份/证书 | component true 不能授予阶段；plant ACK/actual hold interval、Master Clock 仍 unknown，研究结论仍 false |

上述依据为 C3.4 下一计划、C3.4 实现报告、主交接文档、B4 参数来源审查与冻结参考/严格检查器报告。旧压力/恢复/动态版本证据不能自动继承到 N10 或新执行版。

下一步：等待 Root 新 registry/合同修订就绪，只读复审完整注册门与统一闭包；随后检查新原件 14-job 重放和 coherent 语义负例，不改历史判定。
