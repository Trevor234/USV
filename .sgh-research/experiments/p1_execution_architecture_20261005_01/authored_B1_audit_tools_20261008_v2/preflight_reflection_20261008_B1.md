# B1 接续预检：2026-10-08

沿用 2026-10-07 B1 反思的工具范围与验收门，目录名保留开始日期。本次先核实 Ubuntu 主机；B0 关闭清单 1908 项漂移为 0，控制器/Gazebo 0、新增诊断/fixture 0、不可读命令行 0，boot 与已锁定 B0 相同。事实来自 `remote_preflight_result_20261008.json`，未启动业务。

仍采用 control-preflight-reflect 的证据锁、机制假设和 go/no-go。GO 仅为新独立目录 clone 构建、工具测试、错误配置的真实 ROS 启动拒绝及文档交付；C0/R5 压力/正式冻结/physical execute 均未获本次工具验收通过。核心九个头文件保持 B0 摘要，新的 header/source/bin/runtime 锁入独立 successor 清单。

代码审查确认 Decision 入队失败分支没有自动清除共享 candidate/admission/pending；本次记录真实状态，不修改此业务政策。Sink 异步 failed 快照不能反推原短路门输入。whole tick end 包含正常 cutoff 或失败退出尾部，不能与原 Decision end 直接相等。

默认 witness=false/pause=0；启用记录仍不授权控制。暂停限 0..5000ms，显式一次 arm，queue mutex 外有限等待且 close 可取消；操作系统调度可能使实际间隔超过政策截止，必须保留实际时间，不能称硬实时证明。固定满容量、不完整槽、写入失败均保存审计失败；source RC2 与独立 audit RC3 分列。

停止条件：资产漂移、主机未知控制进程、构建/工具测试/拒绝门失败、owned 清理失败或身份不一致阻止 B1 完成和进入 C0。首次构建宏错误与第二次 ROS Python 路径错误分别保留原始记录，第三次尝试修正脚本后重新验收，不覆盖失败目录。
