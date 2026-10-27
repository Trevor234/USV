# 方案A：真实owned正式无输出准备与关闭（第45批）

2026-10-20。本批承接第44批的规范修复，将seeded准备权限核心接到实际Native角色、Worker、Fixture和Recorder。**一次真实四角色准备/关闭已通过独立审计；该组件工作包闭合。B5正式冻结、M0b、M4、F6及P1整体仍未验收。**

## 完成了什么

新增两个隔离Native角色及有界Driver，复用Worker35、RecorderC3.4的封存ELF。默认源码/install、scheme=B动态NMPC数值核心、19个hydro参数、代价、原shadow入口、正式契约v3及物理execute禁用保持不变。

| 角色 | 修改与实际作用 |
| --- | --- |
| 新formal_preparer（ROS名p1_regulator） | 加载84字段pre-freeze、fault=false和no_output；创建七个真实Reader，零应用Writer；以真实进程、GID、参数、输入/参考对、Capability租约、Recorder就绪构造Context，再接受一次prepare-only请求 |
| 新Fixture（ROS名p1_synthetic_source） | 50Hz发送clock/odom/IMU/path/profile，21点静止参考；不读取或伪造Applied，不把零值当成真实命令锚点；Reader就绪前不发布输入 |
| Worker35 | 原ELF不重编译；在本次真实formal84/fault=false配置下初始化acados backend，实际test_delay/native_block和V2均none/0，等待真实Reader；接到0个Job、生成0个Candidate |
| RecorderC3.4 | 原ELF不重编译；新七topic清单、真实storage、有效配置与实际Reader GID全部绑定；实际记录并完成stop/flush |
| 新Driver | 非ROS参与者；核验真实exe/argv/PID/start、清单、Source FD和参数，再发一次请求；按preparer→Fixture→Worker→Recorder关闭，只清理自己的受管进程组 |

当前契约hash为`1faedd4bbf7338ffbd3bc1f9b049285e58d7c3605816d416ac2b83fbfd5365fb`，规范仍为第44批恢复的`317ec56f9c1211b9d8adc5dc727e2a20c1f281afd2047efafecbac797c46d798`。同一字节契约及run/boot在四角色绑定。原pending8没有改动。

实现保留20s准备预算、2s授权TTL、600ms有效Capability回执租约和100ms新鲜输入检查。Path/Profile独立到达时，保留100ms内最后一对完整已认证参考；不以未配齐的新半对覆盖已完成参考。该准备角色没有命令锚点、Job/Decision业务或独立Decision Witness，不能当作完整Regulator已验收。

## 本批实际证据

最终候选编译通过，17项新增typed输入边界检查通过；最终ELF的22项真实构造拒绝检查通过，覆盖错误mode、旧diag/Frozen、fault/execute标志、SHA、字段缺失、伪ready覆盖及topic remap。前一候选同样22项结果保留，区别于本轮只有一次完整四角色运行。

唯一实际运行：`runs/formal_prepare_01`，独立DDS197，总用时 **9.714841s**。真实prepare请求被接受一次；同一请求再开被实际拒绝。授权后观察约1s。四个角色均returncode=0，只使用SIGINT，进程组全部清空；没有TERM/KILL。该有限观察不证明最坏执行时间或一般动态域。

| 账本项目 | 独立结果 |
| --- | --- |
| Fixture发布 | 每路69条，五路共345条，均返回成功 |
| Worker Capability | 发布25条，所有19个字段、实际fault=false、idle计数与bag一致 |
| Recorder Stored | 370条=345输入+25Capability；Candidate topic存在、消息0 |
| 准备角色实际接纳 | 278条输入、23条Capability；输入拒绝0，来源GID与Fixture/Worker清单一致 |
| 图/门检查 | Native轮询824次，保留42条周期图快照；记录的forbidden Writer检查均为0 |
| Job/Decision/Applied/推力调用 | 均0；新准备角色零应用Writer |
| 独立审计 | 1326项输入锁前后相同；实际源、录制、参考对、grant/lease、终态与组空核对通过 |
| 篡改实际证据反例 | 12项全部拒绝；属于离线检查器验证，不是12次运行时故障注入 |

准备角色与Recorder关闭时刻、QoS和读取窗口不同，不把278条准备输入与完整345条发布简单相减来宣称丢包或无丢包。外部Source-to-Stored审计逐一匹配345个唯一topic/仿真stamp，并核对所有输入字段（包括协方差、姿态及完整参考数据）。25条Capability的全部19字段、记录计数及显式布局解析也匹配。

## 保留的失败与纠正

首次编译因当前Jazzy没有相应free `spin_some`重载失败，日志/源码快照保留；第二候选改用显式Executor后通过。随后在运行前处理参考配对更新风险，第三次构建为最终候选，并重新做受影响构造检查。未在失败目录补跑。

原始typed重序列化SHA与bag raw SHA比较不能直接通过：clock匹配，其余五种topic不完全相等；这个失败观察原样保留。进一步按实际IDL解码，25条Capability的Source typed CDR各425字节、bag raw各428字节，所有19字段和字段字节相同，差异仅落在已定位的内部填充及3字节尾部。解析探针关于尾部的两次错误假设亦保留。独立审计不声称raw SHA相等，不修改bag或Source，也没有为修正检查器重复控制运行。

Recorder自身`storage_stream_accounting_verified=false`字段保持原样。实际完整账本核验由本批外部审计单独给出，不能回写成Recorder内部保证。Capability仍没有源packet序号/发送时刻，本批证明有效身份回执租约，未取得源packet新鲜度保证。

## 状态与下一步

初末保护均通过：49,215个本地历史路径、6,223,044,075字节；原24处151961字节业务diff、单列real.launch.py、所有冻结资产和旧失败未改变。本批MPC交付以同目录`delivery_verification.json`为准；不把未逐字检查的旧MPC镜像说成本批重验。

依交接文档S5，停止扩大已证的prepare/close组件。下一步按原D1/B4/B5/M0b条件建立最终版本冻结差集：当前20s正常域是否仍缺、B4工程假设/pending8如何闭合、完整Regulator no_output源/参考/锚点与当前formal profile有哪些实际差异。只补矩阵认定的实现或证据，不重新穷举原始消息或重做39–42全部故障/恢复，也不增加半RMSE/RTI/权重门。

B5/M0b真实条件满足后，才依序不可变冻结、M4唯一真实输出、有限已知模型切换/F6和原P1联合验收。GP/PPO和完整碰撞证书没有增加为当前P1的前置条件。详见下一步计划。
