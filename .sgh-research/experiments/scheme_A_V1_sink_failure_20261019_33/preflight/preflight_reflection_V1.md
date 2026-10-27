# V1事前反思与Go

事实：原shadow入口无可用日志暂停；已新增显式诊断profile和容量512真实队列触发，三组/23断言通过；旧execute禁用、数值合同和五个传统hook零值保持。

根因排序：1. 缺少受限故障入口；2. shadow发布链和Source失败后的关闭语义需分账；3. 旧版本压力结果不能授予新版本资格。

选择A：一个owned localhost故障run。B仅Native不足以确认运行链；C使用无界CPU/磁盘压力会混淆因果，未采用。Go仅限登记的diag profile、run和预算。

验收以preregistration各条件及实际Source/Witness/Storage闭合为准。正常Source不完整和Observer退出2是预期事实，不能把原normal passed改成true；故障局部清理不等于全部正常关闭政策资格。

预算在提交前独立调整为准备20s、故障观察5s、关闭15s、整体观察45s，外部55s INT兜底只用于保留失败及owned清理，不表示更长时长可自动合格。每批只一次实际run。

EDA STA/PPA/route不适用。来源为原交接4.3/6、D31与D32计划、当前新源码与编译/Native证据；没有性能或概率安全推论。
