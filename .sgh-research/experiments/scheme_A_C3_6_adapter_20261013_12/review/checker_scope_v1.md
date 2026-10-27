# C3.6 adapter 真实运行离线检查器范围 v1

新工具：`authored_D1_C3_6_adapter_20261013_v13/check_c36_adapter_run.py`。调用形式：

```bash
python3 -B check_c36_adapter_run.py --run-dir /绝对路径/run --output /新建路径/check_c36_adapter_run.json
```

输出 create-only；默认输出完整 JSON。任何缺失输入、无闭合 Source、非有限/重复键 JSON、CDR 解码失败或人口 join 不守恒均失败。正常输入声明须定位当前 run；不接受其它 run 的成功汇总替换当前证据。

## 读取与重构

- `inputs.json`、`result.json`、`checker_inputs.json`、全部五角色 owned manifest、live parameter typed 回执、peer pins、driver close request/ack、terminal tail ack、进程事件 ledger。
- 完整 SQLite/metadata/transport、Observer/Worker Source、Publisher session 与固定 Witness；无测量窗口裁剪。复用继承的实际 ROS storage reader 及独立 full typed/Witness joins，报告依赖 SHA。
- 每条实际 Applied 回调的 MessageInfo GID、完整 CDR 重序列化及其 SHA，独立 ROS 解码，与每条实际 SQLite 全部 typed 字段比较；transport 与 SQLite 另做原 CDR SHA 全序列对齐。回调 CDR 是 typed 重序列化，不声明原始 UDP padding。
- 每条实际 Applied、组件观察、legacy anchor 的完整同序列人口；已收受完整 Applied 重构每个 Job 的冻结 anchor 与完整 held history。完整 immutable Job 跨 Job、Worker Candidate 与 registration echo 比较；完整 native prediction 及 first control 的基本一致性。
- 导入/ready/inspect 的 preliminary 线性点与最终 submit/ready/activation 完成点分别对齐；deadline、关闭资格及 Witness 使用最终完成点。不要求固定的 Job、接受或拒绝数量。
- 每条组件 evidence 要求 active publish transaction、实际 regulator publish、plant acceptance 均 false；冻结 anchor 只能沿已认证 Applied 变化。关闭观察取消 pending，最终 join 后必须 closed。
- 正常阳性 run 要求所有 Applied callback GID 精确对应已钉住 owned Publisher；关闭后的退出进程 queued terminal tail 仅允许精确 GID、shutdown_zero 与driver request 后 2 秒，且两个有限 command 必须精确 0、两路成功、两个 call start 不早于 request、左右调用有序且 call end 不晚于 receipt。出现 auth/resource/legacy 非收受人口不得被裁剪掉而继续 pass。
- driver close observation/ack 必须保留 unknown owner close intent/endpoint exit；ack 在实际 ledger Publisher SIGINT 之前。新提交/接受必须在 observer 观察 driver close 之前。
- 所有角色的有效配置完整 typed 值与预声明配置、canonical 参数摘要、外部 live 参数回执相符；normal hooks 和 immutable 协议由原 owned driver 认证，与新 helper 的完整配置比对共同约束。
- author source bundle 的每个文件、binary 当前 SHA 与 run 输入钉子一致；整 run 输入检查前后 SHA 一致。

## 明确边界

这是单次 4 秒 bounded owned shadow fixture 的组件人口检查。Applied callback GID 新认证，不把继承 Worker capability/PIDfd/lease/echo 保护描述为新增 Worker callback GID 认证。现有 old whole-pair Applied admission 通过后才进入新 Adapter；实际 per-channel partial/unattempted executor 尚未接入。真实 plant、MasterClock、continuous DDS uniqueness、post-pin exec continuity、WCET、owner close intent 与 adapter close 时 endpoint 退出均保持 unknown。阶段资格及研究结论保持 false。

已完成 Python AST/导入检查、3 例重复键/非有限 JSON 拒绝，以及使用 N10 原闭合数据的纯内存 business 字段格式演练（469 项 check，未模拟真实 adapter 或构成新 run 通过证据）。真实运行验收需由本批执行结果填充，本文不提前宣称通过。

`callback_reason` 的 pidfd 守卫点与后续 `owner_process_alive` 诊断是不同 poll；空 authentication reason 代表守卫点 live，后续 bool 可为 false，报告保留其数量，不反推前一点无认证。inspect 的诊断与最终 fresh owner guard 同样分时；不宣称两点之间连续存活。
