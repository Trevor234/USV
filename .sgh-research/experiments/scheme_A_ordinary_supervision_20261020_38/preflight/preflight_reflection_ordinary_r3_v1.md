# r3：修正Recorder准备依赖，最后一次有界确认

r2在release前终止：Recorder manifest要等Observer的declared topic Writer，而driver先等Recorder再启动Observer。错误是准备流程假设，不是Source普通监督拒绝。Worker工作线程等待recording ready，main参数服务仍可运行；Recorder gate必须保持在Observer创建后。

GO：仅删除提前等待/认证Recorder的两行，仍在原Observer创建后等待并认证Recorder。三角色参数检查及1.1s传感器预热仍前移；所有认证、图、Reader、参数不变，650ms native-ready-to-release守卫、150ms合同及同一普通监督政策不改。五ELF不重建。原两版Source/lock/失败不改。

A：修正明确依赖后最多一项新身份r3确认（最后一次）。B不选：放宽ready、删Recorder或增大旧业务deadline。C不选：按错误r2顺序重跑。若r3不满足守卫/触发/普通停止，停止追加actual run并交付真实缺口。本次不授予B4/M4/P1阶段、通用调度界或研究性能结论。
