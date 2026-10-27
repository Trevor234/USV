# 第22批预运行反思与选定计划

日期2026-10-18。直接依据第21批完整Source/Storage、missing_preparations_audit_v1.json、comparison_G_T_v1.json及实际Regulator源码。route/STA等EDA字段与本USV任务不适用；采用这里的实际时序/状态/接口证据，不虚构外部材料。

事实：94/94送达候选接受，连续最长24；六次运行中空拍均因已认证phase落在新profile/旧path之间，配对在0.622–0.994ms补齐、尚余至少144.732ms，却无重新触发，下一tick旧phase过期。首档整窗RMSE0.00979774427失败；速度超调与首次发布延迟也贡献，未证明修重试就能过速度门。

原因排序：1.有效参考配对完成后没有重试入口，有直接Source与调用点证据；2.其他eligibility依赖是否同样丢失触发，先原生反例确认；3.时间位置追赶、启动延迟和代价作用，连续链修好后才解释其独立性能影响。

选择A：只在有效path/profile提交后复用原maybe_enqueue_controlled_locked。先原生复现旧缺口，再按原mutex与phase+Applied、同版本、deadline和全部eligible条件补触发。每个phase至多一个freeze；错误身份、任务/时钟变化、过期、资源异常、关闭和未成对stamp不能新提交。

B为周期重试，C为放宽时间/修改权重；本批均不选择。原生回归必须经过实际回调和准备/提交代码，不复制条件写替代状态机；身份/RTF/anchor等显式fixture前提与实际DDS认证分列。

数值合同保持Q/R/Rd/Qf/hydro/N/dt和原150ms/200ms，增加准确重试策略字段并新诊断版本，Worker/Observer共同严格验证。实际0.05m/s首档仍20s、>=90连续接受、>=18s跨度、全候选接受、末5s均值相对误差<=5%、全窗RMSE<=0.007392495755251466、完整证据与正常回收。失败停止更高速度，任务位置指标不替代速度门。

Go/NoGo当前为NoGo，直到完整资产/工作区复核、源内回归、严格合同与默认构建/编译加载/实际静态库pin、判定器/prereg完成。随后仅允许隔离localhost FastDDS新owned实验，无物理执行或阶段/研究资格。
