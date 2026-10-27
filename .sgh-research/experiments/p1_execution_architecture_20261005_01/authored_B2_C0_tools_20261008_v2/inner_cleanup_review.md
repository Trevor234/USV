# C0 v2 内部 owned 清理恢复静态审查

日期：2026-10-08。结论：**最终 helper 与 v2 driver template 没有未解决的静态阻断；审查发现的已知子进程迁组漏检、持久观察后最终身份复验缺口均已在冻结版关闭。**可以完成本轮新工具测试、声明的受控 owned 组回收验证和 v2 部署。实际 C0 仍须在这些前置、原检查、资产/host 守卫均闭合之后启动。

本审查未运行测试、远程、ROS 或信号操作，没有修改源码、旧 v1 部署、旧审查或旧证据，只新增本文件。旧 v1 已部署但未 launch 的事实保留；新 v2 不应覆盖其原件。这里不是实际清理成功或 C0 通过报告。

## 1. 冻结输入

| 文件 | bytes | SHA256 |
|---|---:|---|
| `runtime/cleanup_C0_inner.py` | 18329 | `2cb39d74440bda285089e061ae282ad4b48e4d0805192cfc9746447922603b82` |
| `runtime/test_C0_inner_cleanup.py` | 12664 | `1f076891c2ef49670915913b57d839eaef6baeb693df7a09600ea4c062deb061` |
| `remote_run_v2.template.py` | 9985 | `dd0725ba3875624ace04cc651f546530b59f85e078e5e35aab66f0ed5ba810ba` |

测试文件静态包含39个 pure mocked 方法，作者报告本地39项通过。本审查没有再次执行；v2 新工具实际部署/测试、两项真实受控 owned 进程组验证应另存结果，不把 mocked backend 当成 Linux `/proc` 或真实信号覆盖。

driver template 的 POLICY_SHA、TEST_COUNT 仍为生成占位值。本审查适用于上述 template 逻辑；实际生成脚本必须替换声明值、保存新的完整文件 SHA 和政策/工具 manifest，核对模板差异仅为预声明替换。旧部署、旧工具测试与日志在 v2 前后由 `verify_previous_tools()` 单独验证不漂移。

## 2. v1 风险与 v2 时序

原外层 Supervisor 只拥有 runner 自己的进程组。runner 内部的 recorder/fixture/worker/regulator 使用独立 start_new_session，原 PGID/SID 与外层不同；直接 TERM/KILL 外 runner 不能据此证明内部组全部消失。v2 正确把内部恢复列为独立门，不能用外组为空代替内部为空。

v2 `call('runner')` 在120s外层超时后先向已授权外 runner 发送 SIGINT，再给 inner finally 20s有限 allowance。随后读取本次 D 的内部 owned ledger 做 recover，才对外 runner 执行有限 stop。首次内部结果 incomplete 时，在父 runner 退出后再次读取/恢复；两次结果分别保留，不删除首次失败。即便后续组回收成功，只要该 call 曾超时，其 timed_out 门仍令本批失败。

正常 runner 自行退出时也调用 recover，独立核对内部组为空后才允许 delivery/comparison 下一步；并非仅 timeout 路径补清理。

`recover_inner()` 包裹 BaseException，尽可能写 outer durable exception event，返回 cleanup_complete False 与 remaining unknown。driver finally 对任何已有 runner item 保留父 stop 前恢复、有限 outer stop、父 stop 后最终恢复，保存 final_inner。最终 unknown/incomplete 会写 failure 并使 C0_complete False；因此 call 提前异常不会只清外组就把本批判断为完整。

如果证据或身份不足，helper 可以拒绝信号并留下未知/残留。这是明确失败状态，不能宣称已经清理，不能启动下一批。若父退出后读到稳定、合法完整授权，可在同一有界恢复链重新验证；否则保留阻断，不通过名称扫描去追杀未知组。

## 3. 授权来源与缺失角色

expected_roles 必须恰含 regulator、worker、fixture、recorder 四角色，每项仅有独立读取的 canonical绝对POSIX exe 与小写64hex SHA；boot 必须合法 UUID且当前 boot一致；runner_pid 为严格正整数。内部 ledger 路径要求绝对路径并为 owned_process_ledger.jsonl，driver 固定从本次政策 run_id 对应的 fresh D 传入，不从主机发现结果推导授权。

ledger snapshot 要求非空且不超过4MiB、10000行，UTF-8、每行完整最终换行、无空行/重复JSON key/非有限值，有限 JSON shape。读取前后 dev/inode/size/mtime_ns 与字节长度稳定；中途改写或未关闭的并发尾部拒绝。

每个 row 有明确 type、正 monotonic_ns 和同 boot。spawn 角色不能未知/重复，identity 必须为严格正 pid/ppid/pgid/sid/start_ticks，leader.pid=pgid=sid；创建时 PPID 绑定本次 outer-owned runner_pid，executable_verified True、expected exe/SHA 与实际 identity exe/SHA均等于独立政策值。显式 launch_identity_missing/group_invalid 全局拒绝，不能因只看到一个 PID 就补授权。

内部 ledger 中 observed descendant 要归属真实已记录 spawn、同 owner PGID/SID、start_ticks不早于owner，重复 PID 不得以新 start_ticks 覆盖。四角色 leader PID 不能复用。

缺一个角色不等于它已经退出，也不等于它没有被创建。helper 可以清理已被完整授权且验证安全的 subset，但 missing_roles始终保留，evidence_complete False，cleanup_complete False；无 spawn 也不能以空组返回完整。原 helper 没有启动/ROS/R5 API。

## 4. 每次信号前的真实身份复验

在第一个 signal 前，helper 对所有已有 role授权先做全局 live preflight；已知 PID复用、错误session/组、leader exe/SHA变更或不可读identity会使全局失败，不先杀其他安全角色来掩盖未知角色。

每轮 `_members()` 先检查 boot并对所有记录 PID逐个查当前identity，再读取leader并验证 pid/start_ticks/PGID/SID/exe/SHA。允许 runner退出后创建PPID合法转为init等当前parent；创建时PPID已被固定，当前PPID变化不被误判为PID复用。

随后扫描原授权PGID，要求同SID、严格pid/start_ticks与真实读取identity对应。新组成员在成为已知成员之前先 durable记录完整exe/SHA身份，才存pid/start_ticks。不能借进程名称或外组PID授权inner group。

每个 SIGINT/TERM/KILL之前再次 `_members()`；signal intention持久记录后再 `_members()`，避免证据IO耗时后的旧快照直接触发信号。冻结版还在 `_members()`末尾对记录PID和leader再次复验，覆盖这次内部新-member durable event造成的授权变化。只对该原PGID发signal，不迁到未授权的新PGID。

leader exe/SHA与独立 expected值精确绑定。descendant以同一已授权session/组及pid/start_ticks确定归属，并在每次扫描读取合法exe/SHA，保持观察记录；它们可以是recorder启动的其他真实子程序，不能无依据把四role leader的exe pin强套给所有descendant。未知/不可读exe身份会保留失败，而不是空组。

这些检查缩小了信号前的竞态窗口，不宣称用户态 `/proc`复验与killpg是一个内核原子事务；已有进程所有权、原session与创建身份是本次允许操作的依据。

## 5. 审查发现的两个阻断及关闭依据

第一项：最初 `_members()`只过滤 `row.pgid==owner.pid`。已在ledger中记录的descendant若仍存活但迁到其他PGID/SID，会被continue跳过；leader不存在、原组空时可能被误判完整。最终 `_check_known_members()`在PGID过滤前及成员事件后逐个查已知PID：复用、迁组/迁会话均明确拒绝；不会追杀新的组。对应原组空但descendant逃逸PGID、逃逸SID、PID复用到原组外三项负向定义已存在。

第二项：持久写新-member event自身可能耗时或发生identity变化；即使signal event后调用了 `_members()`，也不能只复验它进入前的leader。最终在新-member持久记录后再检查全部已知PID，并再次验leader exe/SHA/start/PGID/SID。新增负向用例在最终signal前才引入新member，再由member事件使其迁组，要求无killpg；因此覆盖真实最终复验位置，没有只依赖initial preflight后的下一次复读。

两项都在本次C0尚未launch时按既定owned边界补证，没有依据现场结果放宽identity、时间或资格政策。

## 6. 持久观察、未知尾部与有限等待

helper的authorization、new member、signal intention、role result和summary由callback同步落outer ledger且明确返回True才继续。driver callback使用sup.event后检查evidence_failed。证据失败在信号前会拒绝触碰；资源结果与证据完整性分列。异常会返回false，并由driver step/final_inner/最终run result保留；不把IO失败当作组消失。

SIGINT .5s、TERM1s、KILL后查1s按每角色monotonic截止等待，默认四角色累计等待预算最多约10s，不包含 `/proc`扫描、哈希和持久IO开销；任何单次真实系统调用延迟也不被称为WCET。外层20s inner finally allowance和父前/父后有限恢复各自记录；没有无限等到成功、无限重试或增加新launch。

helper不使用waitpid假装回收非直接child。已退出zombie不能被视为原组为空，不能用发信号使zombie“消失”；仍需父退出/reap后有限重新观察。真实Linux zombie的exe可能不可读，因此可能更早被明确标为unknown，而不是mock测试里的完整exe身份；这种情况同样不能通过。root声明的真实受控组验证需覆盖实际 `/proc`行为。

恢复结束重新snapshot ledger并核对与授权SHA一致；恢复时runner若继续append，证据完整性失败并保留changed结果。driver在父退出后有限再读稳定账本，首次与后续结果都保存。最终pass需要完整四角色证据和所有已知原组/成员为空，两者缺一不可。

未被ledger授权或观察且已经脱离原session的进程无法从此helper获得安全信号权限；本工具不宣称可以在证据丢失时找出所有潜在未知child。发生这种情况需以missing/unknown、host或其他owned异常阻止下一批，不能把“只处理了已知subset”写成全系统清理完成。

## 7. v2 集成、最终门与未完成验证

v2工具目录独立，验证55个runtime文件、policy新文件和extra文件哈希；验证旧v1 result/全runtime/extra/log不漂移。政策固定真实expected role exe/SHA/boot，外runner也使用固定Python exe/SHA启动。运行后继续原context/source/base/bag/delivery/Witness比较、实际10s、正常RC、资产/host等合取，并保存真实input/report SHA。

final_inner最终unknown/incomplete、外层cleanup失败、outer evidence_failed或任何批次timeout/其他failure均不得C0complete。后续R5、M0b正式冻结、M4/F6/P1、execute及physical release继续False。

本次静态结论不证明helper能在真实Linux上完成组回收，也不证明C0正常数据已采集。root拟加入的两项真实受控own进程组验证和v2新工具完整puretest仍须真实执行且保存原件；完成后方可按原事前声明启动C0。任何unknown残留禁止下一launch，并保留原失败批次，不能通过改policy或摘要掩盖。