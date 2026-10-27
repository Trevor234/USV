# T2-B架构性时序约束

## 实测分解
| 段 | 耗时 |
|---|---|
| Python观察循环(3文件I/O+4进程poll) | ~140ms |
| 命令写入(temp+fsync+renameat2+dirsync) | ~52ms |
| 动作执行(Fixture+Regulator path_version) | ~7ms |
| boundary释放 | <1ms |
| **合计** | **~200ms** |
| Job deadline | 150ms |

## 结论
外部Driver基于文件I/O的编排**架构上不可能**在150ms内完成及时在途场景。

## 修复方案
**推荐A**: 触发改`job_received`(boundary进入前~1ms)预置path动作;boundary_entered作为在途证据(不作为触发);释放后在C调用产生原Job echo的候选→Regulator以版本原因拒绝。语义保留完整,时序约束消除。
