# 第75批R0至81当前协议层独立审查

范围：75 `test_r0.py`及19项实际测试；78 `t2_author_r3`（81登记实际引用）的Driver、合同、Fixture命令门、审计；仅离线，无ROS/owned。工具产物在本目录。

## 已成立

- 75原19测试独立重跑19/19；74旧的缺字段、嵌套job读取、外来action、无guard等保留反例受到有限覆盖。
- Driver `job_received`从真实嵌套Job构造完整四字段证据，`ready_window`亦由真实ready_commit构造；Fixture表序及action_id去重已落地。
- C回执已从预发标签改到close ladder实际发信号后记录的sent_ns。但sent_ns在killpg返回后读取，严格意义为调用返回后的观测时刻，宜保留调用前后区间及target观察ACK。

## 仍有实质缺口

1. P1 C接纳反例未闭合。`audit_t2.py:258-259`按ready_commit_ns过滤请求后接纳，实际接纳发生在activation_commit_ns；ready=1000/request=2000/activation=4000仍passed=True。原75反例把ready改为3000，未锁定真实维度。
2. P1 C时序观察取错。`:249-265`把shutdown decision.end_ns当stopping_observed。真实guard在1055-1056，tick_end在1122，必有end>guard。目标同tick看到停止并拒绝时，该审计反而拒绝；若停止早于tick，1096-1107先invalidate清票据，通常得到Job0而非目标guard。不能只重登记就声称C可确定性执行，应先真实Source路径离线证明及明确停止观察事件/目标guard边界。
3. P1 审计不消费全链。`:60-76`仅查Source Decision/Applied计数，`:79-110`只声明关闭和witness一个布尔，不读取Stored/typed bag/API_pair/phase/identity。`full_exit_and_storage_required`不落为实际Storage谓词。完全无Stored正控可通过。Regulator group_empty=false亦通过（只对其他3角色查group）。这不证明81实际Stored有错，但13/13不能称原合同完整独立验收。
4. P2 回执绑定只比自报SHA。合同`:253-258`不复算record.command字节SHA、不validate各record、不比较receipt.trigger==record.command.trigger，重复记录亦由set掩盖。离线将receipt的Job改999/phase改job_received/source改worker仍通过；SHA两端共同改为not-a-sha仍通过。
5. P2 Fixture独立门未与Python等价。生产`poll_commands:146-150`仅要求trigger含四字段且phase相等，没有精确字段集、正整数时间、phase/source角色、登记Job校验。抽取未改动真实C++ poll_commands（execute_action仅替换为计数stub）验证：登记Job2，命令Job999/observed=-100/source=driver/extra字段，动作仍执行。R0修了表序/唯一，但全触发绑定仍需共用合同或具名交叉负控。
6. 身份核对发现：81 registration.audit_tool SHA=72644f6a…（75旧审计）；指向78/r3当前文件SHA=170bf747…；当前audit已新增job_received白名单，登记未更新。身份审查线程复核为准。

## 下一步

先修派生审计及协议：从固定command bytes复算SHA、验证顺序和唯一记录、receipt完整trigger/行动参数绑定；Fixture同一合同负控；C按activation_commit与StopObserved真实时刻；导入全流Source/API/Stored身份与关闭门。保持旧run、旧结论和失败证据，当前13项结论收窄为有限审计的局部通过。之后再离线验证C真实目标窗口可观察性，必要时采用明确的scoped final-guard边界组件；生成新身份链后有限owned。切勿通过放宽时间链、把Job0当目标guard或把end当停止时刻完成C。

反例：`probe.py`、`probe_result.json`。Fixture真实门摘取：`fixture_gate_probe.py`、`poll_commands_extracted.hpp`、`fixture_gate_probe_result.json`。19项重跑：`r0.stdout`/`r0.stderr`。
