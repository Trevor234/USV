# 第79批:T2-B boundary owned(根因已定位)

11次owned尝试(全部保留);基础设施完整打通;根因=Worker ofstream缓冲延迟(~200ms),boundary_entered不可见直到capability flush。
修复=Worker event()在boundary事件后flush;需Worker源码变更+重冻结。
