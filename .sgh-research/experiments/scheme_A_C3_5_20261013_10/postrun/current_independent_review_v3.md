# C3.5 当前独立审查结论（合同 v3）

日期：2026-10-13，Asia/Shanghai。

**当前 v3 的已审正式接受代码、注册依赖与固定原件闭包通过只读复审；本范围内没有剩余 P1/P2 代码问题。** 它接受冻结 N10 的有限 shadow 组件证据，不能授予 B4/M0b/B5/M4、execute 或研究资格。

当前合同：[`acceptance_contract_v3.json`](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/preregister/acceptance_contract_v3.json)，SHA256=`927e9f0776b8deee4c1b77e730409549eba0916df1061e8cd11b1583e73281af`。机器结果：[`current_independent_review_v3.json`](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_5_20261013_10/postrun/current_independent_review_v3.json)。

## 已闭合的审查问题

首轮只固定了 14 个 job，没有固定完整 pin 人口、component 必需项、phase 矩阵、budget adapter 和 deferred 条件。可在整体合同副本中删除依赖、重新计算合同 SHA 后取得错误的 component 接受。v2 增加独立固定 external registry，登记全部外部 source/bin/raw/wire 与已封存辅助工具；Root 可变源码另以完整固定路径集合及当前实际 SHA 注册。现在所有人口及依赖逐值一致，空/少 pin、component 缩小、phase 弱化、adapter/deferred 删除均被拒绝。通用状态组合函数保持原意。

v2 的 `preregister` 字段仍可改指另一个已合法 pin。v3 将 execution scope 的绝对路径、1937 bytes 与 SHA 独立固定；该重定向反例现在被拒绝。首轮和 v2 源快照、合同、完整运行与失败反例均保留。另已显式补入三个实际间接消费文件；入口拒绝 Python 非零优化级别，子进程剔除 `PYTHONOPTIMIZE`，避免 `assert` 语义门被移除。

## 本次实际核验

- 8 组最终合同语义检查符合预期：当前原件接受，7 组旧缺项/重定向/数据集变换反例拒绝。
- 当前 410 个固定输入实际 regular/nofollow 前后读取一致，共 91,888,711 bytes：212 个 identity、196 个 record、固定 execution prereg 和当前合同各 1 个。生成子报告另计，不能计为冻结原件。
- external registry 的 402 个固定 pin 先前已单独复核，全部包含原 N10 的 193 个 source/bin 与 160 个 owned raw，逐项 SHA 一致。Root helper 引入后的当前闭包又做了上述统一复核。
- Reader 的 18 组独立临时文件/严格 JSON/状态组合组件检查通过，包括 leaf/ancestor symlink、FIFO、directory、hash/byte budget、读中修改、非有限指数、重复键和精确四状态。所有修改只在可回收 `/tmp` 夹具；实际原件未改。

Root 的 v2 `full_attempt02` 实际执行了 14 个 job，全部精确 rc=0/status=passed，四阶段均 unknown，所有资格 flags=false。本次 v3 审查只做源、合同语义和固定原件读取，没有重新启动这些完整 job，更没有 ROS/native 控制运行；不能把 v2 结果称为本审查执行了完整 v3。当前正式运行版本由 Root 的各独立 attempt 记录认定。

## 阶段依赖保持

当前 exact typed/source/storage/config/lease/readiness 和有限预算观察支持 bounded component 接受。阶段矩阵继续要求当前 anchor 执行契约、版本适用 pressure/recovery/failed-close、20s dynamic/turn/mixed、有限工程时钟与域外政策、不可变 execute 政策，以及 M4 唯一双路实际发布/部分失败/rho/gap/预算证据。

N10 的 21 次 anchor_mismatch、唯一关闭尾部约 7.95 的 shadow accepted 且 `publish_success=[false,false]`，仍不能解释为 regulator 已输出非零或已接管。Master Clock 硬界、WCET、plant ACK/实际保持区间保持 unknown；unknown 既不写成零，也不凭文档接受变成阶段通过。旧 shared-v2 四工具身份、旧压力和旧动态资格不冒充恢复或自动转移。

下一步按主计划选择真正缺失的当前执行政策/anchor/动态与关闭证据，形成新执行合同后再设计 M4。已有组件正常例不靠重复累计阶段资格。
