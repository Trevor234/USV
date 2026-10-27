# 第49批有限修复与新确认：GO

2026-10-21 Asia/Shanghai。承接48唯一实际启动失败及源码证据：Driver等full Recorder manifest，Recorder等future Regulator Writers，Regulator又等Recorder pin。48 run保持失败，实际只有3角色、Regulator/Job/Candidate/推力API均0；不重试旧注册。

采用control-preflight-reflect/theory-veto及postrun流程。EDA route/STA等不适用。根因排序：生命周期互等；process-owned与recording-ready混为一步；启动依赖未经真实四角色验证。已排除NMPC数值或阈值问题：原52/38/14组件通过且Solver没有Job。

A（选择）：真实Recorder进程/exe/argv/Source先认证（process-only、recording_ready=false），新Regulator创建出口但0API；实际full Recorder manifest/Reader/storage/GID闭合后再准入sources/一次grant/firstAPI。复用旧Recorder ELF，改Driver和Regulator lifecycle，不改合同/数值/模型/RTI/参考。B重复旧顺序或加wait时长无新增机制，不执行。C把process-only伪造为full-ready，禁止。

验收：实际Recorder未ready进程的独立认证与篡改反例；完整Recording-ready前无API；最终原生52、源码关联38、实际入口14检查及真实source/bin/config/工具绑定；原正常Source20s、Driver45s、不自动重试。仅1个新的独立注册确认；所有失败保留。构建每目标180s、具体修复上限2；组件120s；owned退出/组空完整。

verdict=GO for finite source change and one independently preregistered confirmation; blocking_reasons=[]。与48相比控制变量是生命周期拆分，非同配置重复失败。confidence高/impact高/cost中/risk中。前提沿47 trusted prepared graph、near1:1工程外推、19参数名义点模型与Linux有限调度；无plant/WCET/一般域/GP资格。M4故障/F6/P1保持后续。STOP：source/argv/身份失配、full-ready前API、双owner或外部Reader、超期或cleanup_failed。NO-GO不越过，保留并继续无依赖离线工作。
