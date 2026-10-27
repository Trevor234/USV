# V2事前反思与运行决定

事实：第34批封存245文件且MPC二次SHA读回完成，只有独立Sink故障关闭的离线验证，没有新实跑资格。当前源码确认active watchdog=1s、receipt lease=600ms，150ms截止/200ms tick不变。工作线程与能力发布executor分离；WorkerCapability v1无每包sequence/send time。

根因/假设排序：

1. 启动旧钩子非零与原释放条件冲突。不能将非零Worker钩子写成external_worker_zero_hooks=true；新增独立、不可变、显式非执行诊断策略，旧两个钩子为0，释放检查代码保持原字节。策略只在首个Job完成后取一次1700ms屏障；这仍是native调用前工作线程阻塞。
2. 能力回调可持续而计算不进展。V2-A应在lease仍有效时由active watchdog首先终结Worker准入；不能把主线程能力发布当solve进展。
3. Worker/DDS仍发布而Observer回调不执行。V2-B单独暂停Worker回调约900ms，首次终结应为receipt lease到期；恢复回调同run不复活，不能声称源包freshness。

选定最小A/B：先lease(`v2_lease_01`)，再active(`v2_active_02`)，同一Worker新ELF及其余四个已有ELF；同合同、Case C、0.05m/s参考和localhost domain196。两种诊断参数分别配置，并记录全typed配置；不作算法性能对比。新run重建全部owned角色、Worker instance、PID-start和lease，不沿用旧run释放状态。

入口证据：本地43359路径/5440520275字节初次保护通过；Worker构建一次通过，纯Native策略22断言通过；独立时间边界12项通过，Python CLI只读导入通过；全部作者/ELF/源码bundle/编译输入/动态库在`prerun_source_lock_v1.json`锁定。实际端点、完整参数与冻结拒绝仍由每run实际准备流程认证后才释放。

判定：首次worker_unusable_transition原因与严格`>`时间分别核对；同run终结后不得新submit/accepted activation或续租；实际Source/Witness/Stored/Fixture/owner GID和进程账本独立关联；tick不得skip，观察窗口start/activation jitter≤20ms、start gap≤240ms只作有限工程检查。V1 Sink注入关闭，Observer旧五钩子0，Observer不得有实际双路publisher。

预算：每run≤45s，prepare≤20s、定向观察≤8s、close≤15s；raw≤128MiB。55s外部INT/后续KILL仅作保护，不算通过。构建≤120s/步骤，新增Native≤20s。单次构建最多初次+两次修复，失败日志/源码快照不覆盖。若相同门连续两次失败且无新机制证据，停止重复运行并给具体下一步。

GO：上述组件入口成立后只运行两个预定有限诊断。运行或审计失败原样保存；只允许针对实际新缺口修复，不改变已经锁定的事前判定标准。当前无stage/execute/true_plant/research资格。

控制实验技能的EDA route/WNS/PPA条目不适用于本ROS控制实验，标为不适用，不填造数值。理论依据来自当前固定源码/合同与原方案A阶段边界，不依赖外部版本推测。
