# 批100 postrun：T3-C族（cleanup_failed / group边界）裁决

裁决：**全部通过**（`t3c_run_verdict_v1.json` passed=true；C12与C3各恰1次运行，自动重试0，原件保留）。

## C12 = T3-C1 + T3-C2（survivor fixture变体，同一run双断言组）

| 断言 | 结果 | 关键证据 |
|---|---|---|
| 驱动有界完成 | ✅ | elapsed 6.1s，4角色close |
| 具名cleanup_failed事件 | ✅ | role=fixture、group_empty=false、check_deadline_ns=1000000000、returncode=0 |
| cleanup_failed_roles字段 | ✅ | ['fixture'] |
| 真实信号梯 | ✅ | [SIGINT(2.5s超时),SIGTERM(1.0s)]——INT被变体忽略越过第一级，TERM触发fork+自身退出，KILL未发出 |
| 其余角色健康 | ✅ | regulator/worker/recorder 全 rc=0、group_empty=true |
| survivor有界可杀 | ✅ | pid记录于fixture/t3_survivor.json，等待2.2s后组探测ProcessLookupError（3s硬deadline内自灭） |
| run判定失败 | ✅ | driver_result passed=false（group非空→common_ok=false，不得伪造清理成功） |
| 恰4次spawn/无重启 | ✅ | role_spawned事件恰4（每角色1次），事件流无restart/respawn/retry类事件 |

## C3 = 负控（原厂fixture二进制）

4角色 rc=0、梯=[SIGINT]、全 group_empty=true、无cleanup_failed——复现批66健康关闭范围，证明C12失败确由注入引起。T3 driver最小diff在健康路径惰性（不改变行为）。

## 静态证据

- `evidence/freeze/driver_diff.txt`（28行diff）：仅两处cleanup_failed插入；spawn调用点逐行相同（4处定址）。
- 离线预检（registration_preflight_t2）双登记全过：registry/driver/bundle/ELF逐SHA、regulator源码字节不变（225e975c...）。

## 与批98设计的偏差（已声明）

- **survivor角色：recorder→fixture**。原因：recorder是批66外置pinned二进制（p1_owned_recorder，非树内源码），不可重建变体；fixture为树内最简角色。语义不变：注入仍在被测关闭链的真实角色进程组内。
- **fault_injection_enabled保持false**：预检冻结该字段语义=运行时v3合同故障机制关闭（属实）；T3注入以登记内显式`t3_close_injection`字段+差异二进制SHA声明，不隐藏。

## 冻结身份

bundle 340b7b2a...（105文件）、T3 driver 3f1a587f...、survivor ELF 2df865fe...、原厂fixture ELF 5bca21e0...。
