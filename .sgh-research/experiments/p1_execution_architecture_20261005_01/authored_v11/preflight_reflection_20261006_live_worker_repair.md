# P1 活进程失联最小修复：复现后提交门禁

2026-10-06。原v10/revision3真实idle_stop run为15job/6candidate/16decision；PID/starttick保持、实际STOP状态观察9个决定，1.2s之后仍有3个新submit，未出现terminal。checker gap_reproduced=true、evidence_accounting_complete=true、issues=[]。SIGCONT后原worker正常关闭，unknown=[]。947项资产终检无漂移、controller/Gazebo=0，239项Ubuntu Python通过。旧缺口原件保留，不把它写成修复通过。

沿用前一份control-preflight-reflect锁定的方案A：GO于regulator v11/revision4诊断接收租约，worker v8/IDL/原nominal不改。新worker_capability_receipt_timeout_ns=600000000是原200ms能力发布周期3倍的诊断试值；只有本地有效能力验证提交时间，source_freshness_available=false，不能证明源发送年龄/重放抵抗/求解进展。原deadline150ms/tick200ms/active_watchdog1s都不变。

到期检查先于续租，>600ms终止，=600ms允许；valid身份/形状/实例/失败标志一致才续租及更新active状态，foreign/invalid不续租，terminal后匹配消息也不得恢复。新合同明确标revision4与policy、diagnostic_only，旧revision2/3检查仍保留支持且禁止隐藏新字段。调节器新运行必须使用明确v4策略；execute未准入。

备份旧regulator源码/CMake/安装程序，然后有限构建与相关C++/全Python。新三项失联矩阵按最后actual valid commit计算到期，>600且≤820ms；STOP live状态持续1.8s，SIGCONT后0.8s至少3决定不恢复，invalid副本完整字段对拍且不续租。只证明处理过的能力callback在actual bag有对应内容，记录器早于调节器订阅的原始能力前缀不推定为已处理，v1没有逐包序号不虚构一一消息来源。

正常、150ms迟到、原pre-native watchdog、非空pending退出和VRX shadow必要回归；正常与预期故障分别使用已有门禁。START/STOP：身份、物理端点、录制、清理或资产不一致即停、保留失败，不能改阈值求通过。EDA专项N/A。M0b/M4/F6、真正输出合同、模型切换/认证备份、GP标签/证明未完成。
