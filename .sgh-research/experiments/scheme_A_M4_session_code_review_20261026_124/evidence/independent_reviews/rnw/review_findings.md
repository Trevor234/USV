# 117–121 RNW / B2 弧独立只读审查

2026-10-26；不启动 ROS，不新增 owned run，不改旧资产。证据与脚本在本目录。

## 已成立的工程进展

1. 117 的 pure audit + admission 可离线运行，私有副本重放 **18/18**。它已能拒绝 false candidate、fallback-only、无 candidate 注册、partial API，以及保留的两次真实失败 run。把验收从“事件数”推进为 Job / Decision sequence 的关联，是有效进展。
2. 118 的原生 helper suite 私有目录重放 **16/16**，测试与 Fixture 共用 header，未发生模型/控制律修改；无 hold 路径逐位一致有正控。最后“实际 publish 的 stamp + writer target”配对比“命令执行时刻”合理，避免恢复首拍 double counting。
3. 119 真实正例成立：Source line 661 open gen 2；line 663 commit gen 2 / first Job 7；line 664 Job 7 schedule 3；line 666 candidate echo run / boot / schedule 一致，accepted_registration=true；line 700 API sequence 18 returned=[true,true]；line 701 Applied sequence 18 control_source=candidate；line 702 accepted Decision sequence 18、Job 7。注意 Source 行序中 API/Applied 先落盘、Decision 最后落盘，因果审计应使用事件时间/commit 字段，不能机械要求最终 Decision JSON 行早于 API 行。
4. Worker line 89 对 Job 7 记录实际 C solve 1 次，backend entries started/completed=1，成功；line 91 publish success。该正例不是纯 fallback 假接纳。
5. 当前 registry/audit/table/Driver/角色 ELF 及 bundle 选定 **15 pin** 全一致；119 源 bundle **108/108** 逐文件一致。117 与119 audit SHA 相同。旧失败 run 原件在位。

## 需修正的问题

### R-RNW-01 [P1] 必要条件未进入顶层通过门

位置：119 `implementation/rnw_audit_v1.py:194–202`（117 同码）；`run_s4.py:35–37`、121 `audit_rnw_chain.py:104–116` 继承它。

`audit_rnw_run` 把 close、pause、generation 标为条款后，顶层 `passed` 只检查 R4。私有复制真实119流后，以下反例仍 `passed=True`：删除 driver close / spawn 文件；删除所有 clock；把 generation-open 改为99 / 非法 terminal reason。相应条款已为 false，却不影响最终通过。

修法：单独定义 required clauses 与 honest optional / N/A，所有 required 必须 true；`old_candidate_disposition` 的无在途应给结构化 `not_applicable_absent` / 明确 covered=false，不以要求它通过为由制造证据。顶层输出同时给 `r4_observed`、`run_accepted`、`stage_qualified`，不混用。

### R-RNW-02 [P1] “同 Job 完整链”仍只匹配 job_id / sequence，未绑定完整身份与因果

位置：119 `rnw_audit_v1.py:115–154`；117 同码。

现实现从 open 后全集查存在性：Job / candidate 仅比较 job_id，Decision 只同 id，API / Applied 只同 sequence。没有完整 echo 相等、run/boot/version/schedule/gen2绑定、提交先于注册、ready/activation/API/Applied 时序或重复终局检测。实际 Job 7 的 R4 子集：把 candidate 改成 foreign run + schedule1 仍通过；把链事件反序仍通过。

这不推翻本次真实正例；它推翻“通用复用判据已按流序绑定、事件存在性永不构成通过”的强声明。修复应按真实 schema 比较 Job 身份、绑定 reference_epoch.generation=2 与 schedule，校验 logical commit 时间，避免拿最终 Decision 落盘行序作错误门。

### R-RNW-03 [P1，未来入口 / P2本次合法表] S1硬准入与真实Driver入口分叉

位置：119 `t2_author/t2b_gen_admission.py:51–90`、`registration_preflight` 使用它；117 `rnw_admission_v2.py:26–82` 是另外一份实现。

已实测 actual owned admission 接受 all-false clauses、缺 hold、resume before hold；117 pure admission 分别具名拒绝。119 `freeze_s4.py` 在生成本次表时确实调用 hard.validate_table，因此本次合法冻结输入并未漏检。风险是复用 Driver 创建另一张登记时，spawn 前唯一真实入口仍无法保证同样纪律。

修法：RNW family 的实际 registration_preflight 共用 hardened function，删除重复规则，测试从真实入口调用；单独反例证明不能绕过 freeze helper 启动。

### R-RNW-04 [P2] B2“结构性消除回退”超过已证边界

位置：118/119 `fixture/resume_stamp_mapping_v1.hpp:13–18,38–42`，118 `test_resume_mapping_v1.cpp:61–66`；创新 I-02。

cap 4.9s 已注明长 hold 不在范围，但登记簿正文没有这个限定。6s hold 时 helper 恢复 stamp 相对冻结期间工程投影仍可回退1.1s。此外即便 elapsed1.5s < cap，writer target 配对没有消除接收延迟差：旧接收延迟1ms、首恢复接收延迟15ms，恢复前输出投影101.509s，恢复后101.505s，回退4ms。此为真实 helper + 源码相同 `sim + (publish_start − clock_receive)` 投影公式的离线代数探针，非 ROS 运行；对应 `regulator_owned_execute.cpp:962,968,844` 的历史连续性问题。

修法：保留已测 silent hold → resume owned 正例，将通用保证限定为配对映射 / 接收抖动假设下的连续性；增加接收延迟差、tick相位、cap边缘反例，明确超域 fail-closed 与下一状态；不以放松 L844 或输出权限门掩盖时钟映射问题。B2是 Fixture clock writer 改动，实船外部 clock 不自动获得此修复。

### R-RNW-05 [P2复用前] 宣称溢出防护，但 int64 加减无检查

位置：header `:38,40,42`；测试 `:152–158` 用9e17，远离 INT64_MAX≈9.22e18。

UBSan 私有编译精确复现 `published_stamp=INT64_MAX−10, elapsed=100` 在 line40 signed overflow。当前固定100s / 有限run不触及该界，不能据此说本次run有溢出。复用前应检验输入域及加减溢出，返回明确失败；替换“large positive value”测试为精确上下界与错误分支测试。无需为研究正例扩写不相关的测试矩阵。

## 121审计评价

13/13可表示脚本列出的13项通过：S0有限重算、S1可复现、S2身份与结果断言名一致、部分S4身份与R4重算、旧目录存在。它没有形成对上述审计器/Driver入口缺口的独立证明；R4重算仍调用同一117函数。其文首称“re-executes S1/S2 matrices”，实际只重跑S1，S2读取现有result；本审查已另行私有重跑S2原生套件16/16。应区分独立证据重算与重复调用同一不充分判据。

## 建议下一顺序

1. 离线收敛审计顶层必选门、Job完整身份/因果、真实入口硬准入；以本次RNW3为正控，以私有反例为负控。禁止修改旧冻结审计/结论，使用派生版本追加裁决。
2. 收窄创新 I-02 / I-05 的复用与已证性质表述，保留真实positive和既有失败证据；不会将M4/F6/P1置true。
3. 明确 clock writer所有者与超域/接收抖动政策后，再分项评审B2 Fixture集成；B0时钟纪元恢复保持独立支线。
4. 如当前已有证据可满足新审计，则先离线复判，不自动多跑owned；仅新增行为需要冻结新的ELF与单次有限owned。
