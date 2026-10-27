# B1 独立诊断副本与固定审计：执行前反思

日期2026-10-07。采用 control-preflight-reflect 的证据锁、假设、选项和 go/no-go；本实验为ROS控制，EDA路线/WNS/PPA字段不适用。

## 已核实事实

B0已交付，原91不同C++测试/329Python/565原始JSON/7真实拒绝/4入口拒绝及两正常无输出回归通过，完整事实SHA14593cde0018072518df034c638b94bb15bf29df8910d164b6f7e5a16a333037。最后1908项关闭守卫SHA bc0e932313852ff046b748f9cfa4292d27b5320aea5177a5ef6a20bbff8b1de8。当前生产v14源码归档、worker原v9源未改且重新构建，runtime_v30。canonical已交付7份MD hash仍匹配，参数JSON仍fd1f718398200538c5250f57694fa13c697c34f8368e22ec1d93eb8cc5cda13d。

旧B1正文要求clone v13，此前提已过期，改为完整绑定当前B0 source/bin。生产源码/bin/runtime保护，不覆盖；副本放独立实验目录，用原worker/contract5/fixture。

源码显示tick-start观察source failure会invalidate；Decision enqueue失败只写stopping，可能同拍零输出退出，未在该分支invalidate。不能预断言所有失败路径candidate/admission/pending已清。最终activation失败检查与异步source fail的时刻也分开。B1只观察原逻辑，不在witness内修正或补造状态，后续R5必须照实判失败并再做业务修复。

## 机制假设与选项

1. insufficient_evidence：失效Sink不能自己证明日志失败后实际submit/activation与stop边界；独立固定witness可提供后续审计基础。
2. flow_policy_mismatch：静止零锚点可能在failure当拍退出，缺少后续tick清状态；witness须保留边界与真实槽状态，不先改业务。
3. resource_capacity_conflict：每流容量按完整owned阶段分配，但不能由15s计算保证足够；满/未发布/写失败标incomplete，不扩容或覆盖。

| 方案 | 本轮动作 | 判断 |
|---|---|---|
| A（选择） | 独立诊断副本、固定POD原子发布witness、一次有限消费pause工具、默认关闭和边界/并发/启动拒绝测试 | 原计划B1，风险可控；未运行C0/R5 |
| B | 用失效Sink的日志缺失推断停止 | 无独立证据，拒绝 |
| C | 顺手修改失败路径并直接压力 | 混合工具与业务机制，无法保持原对照，暂不执行 |

## 事前锁与验收

GO：仅独立clone构建、纯工具测试、拒绝模式启动检查；pause单元测试最多100ms，为工具有限释放验证，不算R5实际溢出。固定256tick/128submit/128带candidate最终activation尝试/32phase，含完整published-slot协议及固定首failure；默认witness与pause关闭，无业务决策读取审计状态。sink消费暂停位于queue mutex外，有monotonic最大5s截止及一次显式arm。phase无business mutex反向锁；终端全部writer join后独立文件输出。

NO GO：本轮不运行C0/R5全业务批次、不改生产、不开放physical execute、不冻结参数。B1完成需真实构建、sizeof与总字节、默认关闭/各流溢出/并发published完整性、pause模式与有限边界、错误组合source前拒绝；runtime工具schema/记录校验与原checker分列。关键证据缺失、资产漂移、未拥有控制进程、清理失败或审计incomplete阻止晋级。受影响新增工具验收通过后进入C0，再进入真实512溢出R5，普通source/base失败原状态保留。
