# v2 独立差异审查与 v3 离线复核合同

2026-10-10。只读原件，未启动 ROS。owned 最小计划要求全准备与末帧不裁剪，未知子进程/PID复用/boot改变/IO歧义不能报 clean。以下是源码审查，未将组件 positive 升级为阶段资格。

- prepare_fixture.py:206、214 的 finally 落盘/解析未隔离异常，可跳过剩余清理；:215 固定 250ms 没有证实最终 Applied 已到 observer/transport。:222 在 Supervisor.close 前记录 ledger_failed，:226 passed 未包含 ledger/unverified children，:228 held negative 未含清理、零 physical/Applied、terminal。
- Supervisor.spawn:136 已登记后 :143 exe 不符抛出，driver :79 尚未登记自身 owned，关闭遍历可能遗漏；members:161-165 自动接纳未知 child，后续清空并不证明全生命周期 clean。
- check_owned_fixture.py:186-187 publisher 四 stream 缺字段被跳过；:202-213 仅 physical 数量，未验证值/顺序；:135-179 没有完整 Applied↔legacy_anchor、capability↔admission、Worker received-job 链；:263 registration 未与 immutable job/payload 对拍。
- :295 published_counts 缺 topic 会跳过；:312-317 legacy_ready 仅 once 事件，无 44 字段、postpair、年龄、history 重放。Witness 基础门保证结构/审计闭合，保留 failed/stopping/unknown 事实，不自动保证正常生命周期。输入未整体绑定 preparation/result/ledger/native receipts/独立配置根。
- 保留 actual-storage Reader、每 topic 全 CDR hash 序列/GID、job/candidate/decision typed projection 与部分 Witness join 的现有组件证据。首次 release 3s 为 acceptance expiry，不当作提交后的持续 lease；缺验收前 expiry、receipt IO 后 expiry、重复/替换 release、late init 的实际 driver 负例仍待单列。

positive07 实际 capability storage/transport 63 条，observer admission 48 条。准备与关闭 tail 不能裁掉凑全双射；Worker 没有逐次 capability publisher 源记录或消息唯一序列。因此只验证每条真实 admission 的完整 payload 来源、顺序和 lease；全人口与 publisher-source-count 保持 false。

新文件 validate_readiness_v3.py 仅完成独立离线组件复核。独立身份来自事前锁定的 driver inputs/preparation/build/source/Witness 根，不能从受检 ready/Applied 自学。不得签 strict 共同整链 pass，原 schema-v2 全门/独立 nominal/完整 raw callback provenance/连续资源生命周期明确未完成。合同详见 readiness_v3_contract.json。
