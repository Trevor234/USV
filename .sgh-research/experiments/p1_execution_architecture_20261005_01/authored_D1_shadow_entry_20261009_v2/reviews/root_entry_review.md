# 根任务对隔离 shadow 入口的源码审查

日期：2026-10-09。实现由子任务创建，根任务在有限构建前检查实际 D0→D1 diff、helper、三target测试和CMake，提出并核对定点修订。该文件是根任务审查，不冒称额外第三方独立审查。

核对生产source `c5b3b1f419d0835b06851f332b49f2f1eb43fa766dae19f85999de74aaf05452`，v2测试 `06a20fbd43e460774bcdfb1573b3a26ceec0f26f1dcb41bf0b7c759b3fe3e66d`。D0父source保持 `9265108fe2abed1b2d27a7cdb670e7529740286124fc74da60ca059402d0f7db`。

实际 diff 确认：mode默认空且先拒绝非shadow；完整diag5之后额外强制五hook int64零、mandatory Witness/完整SHA/进程/新互异绝对路径、exact legacy身份及当前boot clock domain。应用publisher/Sink均在门后；物理publisher创建、synthetic runtime anchor和pause-arm订阅已从新constructor移除。旧D0、普通source、default install、合同、Worker、IDL、Witness未改。新runtime无测试宏；no_output/5000ms仅存在继承测试翻译单元。

whole-pair门在原mutex内、合入前校验身份、双路成功、三个epoch、publish start/end及跨路顺序、有限原范围命令、sim不倒退、receipt基本顺序；不合半包。真实已接纳producer变化走原unusable_locked终止路径，清slots/pending/ready/cache并保存before证据；后续正确包不得重入。gap清历史后只合当前真实pair，不补缺号；shadow缺双路pre-odom history时原predict失败。原控制/nominal/接纳/时间公式、D0 schema、Decision finish/enqueue与Witness布局按谱系逐段保持。

根审查修订了三处验证问题：FreshPaths误用未变异对象；actualctor负例可能只因晚期SHA失败而假阳性；mode默认shadow不足以验证显式声明。现分别验证变异p、检查具体拒绝reason、missing-mode拒绝。冻结baseline不能参数override，baseline扰动明确helper-only。v1编译随后发现同源行GTest label冲突；v2仅拆行，两份测试去空白全文一致，v1保留；未弱化断言或加permissive。

审查允许有限native构建/41case；它不证明生产完整constructor成功/ready/graph/真实F5执行链。外部worker实际argv零、new strict shadow source/actual-bag/Witness/owned driver、当前域、时间参数依据、受影响pressure/recovery/close仍pending。fresh path是创建前校验，继承Sink append不具有新增atomic O_EXCL保证；未来driver必须独占隔离产物目录。entry对畸形记录的有限拒绝/SourceFailure属于原研究失败机制，未给任意坏流量下日志成功或WCET保证。D1动态No-Go、execute false。
