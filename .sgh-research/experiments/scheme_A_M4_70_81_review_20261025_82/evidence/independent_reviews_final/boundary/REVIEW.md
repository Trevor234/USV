# 第77—81批边界链独立审查

只读审查，未启动ROS或owned，所有反例在`/tmp`派生副本执行。日期2026-10-25。

## 结论

T2B_P01真实流支持**在原150ms截止内，目标Job2在BeforeCall保持期间执行replace，task提交后释放，发生1次C solve，原Job候选被version_mismatch拒绝**。这7项独立检查全真，见`timeline_evidence.json`。这部分是实际进展，不应因审计缺口抹掉。

“冻结13/13条款完整闭合”不成立：登记工具的精确原件复演仅12/13，13/13来自事后未登记的审计变更；且现有13项不验证Worker边界/实际C/原截止等关键义务。

## P1-1：登记审计工具已被事后修改

- 81登记`implementation/T2B_prepos_registration.json`中audit SHA为`72644f6a7cc2c058d87b242e989e9364874877973d9d03341debd8660de03946`，78当前bundle记录同SHA、17115字节。
- 78作者树当前工具实际为`170bf7476522d605a071b58f7dc112108469b42fed83f604312582f711a17bd6`、17131字节。
- 80/r4保留精确匹配登记的旧工具；两者唯一diff是`audit_t2.py:219`允许相位中新增`job_received`。
- P01 driver_result落盘16:33:09；当前审计mtime16:35:34。时间仅作辅助，SHA差异和精确重放是决定证据。
- `pinned_audit_actual_run.json`:passed=false，`trigger_phase_is_inflight_or_ready=false`，其余12真。
- `modified_audit_actual_run.json`:passed=true、13/13。

应在新派生版本声明修正，不回写旧登记。现有P01可作为新增审查口径的历史观察输入；不能继续宣称预注册工具完整通过。

## P1-2：13项未消费边界/期限/调用事实，反例假通过

`78/implementation/t2_author_r3/audit_t2.py:113–120`只读Fixture/Driver/Regulator；208–234的4个期限/失效项只比登记常量。`probe_audit.py`及`audit_probe_results.json`保留如下派生反例，全部13/13 passed：

1. 删除整个Worker/source.jsonl；
2. Worker boundary改expired、actual_native=false、C次数0；
3. 删除Regulator全部原Job提交；
4. 同job_id拒绝行换成foreign run/worker/task999；
5. 删除候选到达前所有path_version，只留未来无关换代。

必须新加原始Reg Job、Worker收件/boundary/final guard/C计数/candidate发布、Reg同完整Job拒绝及path事务关联；显式检查deadline=origin+150ms且未变，正确时间顺序、过期不可伪装任务拒绝。反例必须由对应断言拒绝。

## P1-3：Driver接受任意path_version为释放ACK

`78/implementation/t2_author_r3/t2_scenario_driver_v1.py:333–335`只要awaiting就置True，不校验任务版本增加、processed时刻或path指纹。382–402在有Fixture动作id回执后直接写释放帧。

`probe_driver_release.py`原样执行生产片段：旧task2、早于Fixture执行的path_version，也会写44字节release。实际P01恰有正确task3，但生产门不能保证下一次仍如此。应绑定目标Job旧task、动作回执和Regulator实际path/profile事务/指纹，且明确`boundary.entered < receipt <= commit < release <= guard < deadline`。

## P2-4：job_received扩展未限定boundary scope

`t2_action_contract.py:53`对整个T2B族无条件允许job_received；文档1–13、30行仍明确它只证明queued。`ordinary_job_received_probe.json`证明同样动作表改为v3后validate_table仍接受。若允许预触发，应绑定boundary scope、目标Job/ordinal及独立boundary证据，普通scope不能借此自动获得inflight判据。

## P2-5：架构“不可能”与“边界前预置”过度结论

80只有一次约199.2ms耗时拆分，无下界证明。P01 job_received至最终guard62.825ms，且Driver已先观察到boundary再评估动作：

- job_received878512849331539；boundary878512849495296（差0.163757ms）；
- Driver命令证据878512849755568，晚于boundary0.260272ms；
- Fixture动作878512896066344，晚于boundary46.571048ms；
- Reg task3提交878512897530643；guard878512912156948，截止尚余85.891629ms。

因此应写“此前文件观察/持久化链路一次超过预算；当前触发和flush时序在本次运行成功”，不能写“动作在boundary前约1ms已预置”或据此断言文件编排架构不可能。

## 冻结来源附带发现

78 freeze_rev11_report仍记录bundle51ca3d42/Driver935cd6b8，但同路径实际bundle已d588fa48/Driverf5556b04，四角色ELF当前与P01登记匹配；bundle103项当前仅audit_t2.py不匹配。79各run的registry/Driver pin不同而路径反复复用。需交身份审查，保留能恢复的各版原件，不能用当前rev11路径冒充全部历史冻结版本。

## 建议次序

1. 固定当前所有字节与历史匹配原件，纠正文档的冻结判定与观察判定；
2. 新派生版本修边界audit、精确path ACK、scope限制，加入上述具名反例及正控；
3. 用现有P01完整原始流离线重审，有效timely replace观察无需为迎合新审计机械重跑；如研究需正式预注册验收，再做一次有限新登记run；
4. scoped Epoch新代际正控、独立expired负控保持未完成，不能说整个T2B族闭合；
5. 修后再做T2C可观测性离线重放与单次登记执行，后续T2A re-evidence、T3/N3/F6/P1维持主线。
