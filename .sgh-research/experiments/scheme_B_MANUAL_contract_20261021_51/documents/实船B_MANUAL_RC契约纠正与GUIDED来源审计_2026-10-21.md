# 实船B：MANUAL＋RC覆写契约纠正与GUIDED来源审计

2026-10-21。结论：用户契约始终是动力学NMPC使用MANUAL＋RC覆写；GUIDED组合与该契约冲突。此前审查未识别并纠正，属于审查遗漏。现已纠正活动源码、配置和模式管理器，30项必要验证通过；没有部署实船或发送真实飞控模式请求。

## 契约及错误来源

原文件`/home/trevor/MPC/01_MPC_Project/01_实施方案/implementation_plan.md`第108行明确“MicoAir743设为MANUAL”，第632项再次要求RC Override通信使用MANUAL。原文及SHA记录于`evidence/original_user_MANUAL_contract_v1.json`。

Git将动态节点GUIDED默认值定位到2026-09-05的导入提交`d00f401`；同日`806cf95`加入了“不含GUIDED”的错误告警，并写下“2026-07实船验证”的注释。本次未发现能支持该注释的对应实船证据，不能把注释当作改变契约的依据。Git记录可定位代码引入时间，作者字段不能证明具体是哪一次人工或AI会话生成。后续工作沿用了错误组合，前面的审查没有把原契约与活动默认值对齐。

造成冲突的实际配置链是：实船B读取mpc_params_B.yaml，该文件以前未写模式白名单，于是继承动态节点的GUIDED默认；模式管理器又把自动切换目标硬编码为GUIDED。SITL B反而显式配置MANUAL，因此同一B后端两种入口不一致。实船launch的auto_mode_switch原本已关闭，这意味着错误白名单可能导致MANUAL下wrong_mode，不能据此断言本机已经实际向飞控发送过GUIDED请求。

仓库运动学`launch scheme=A`使用速度setpoint及GUIDED；研究方案A以`scheme=B`动力学NMPC为基础。二者命名不能混同，运动学的模式需求不能套用到B的RC后端。

## ArduRover源码依据

本地子模块源码显示：`GCS_MAVLINK::handle_rc_channels_override`更新RC通道覆写；`ModeManual::update`经pilot输入读取RC并设置steering/throttle；`ModeGuided::update`使用guided子模式及其目标。接收RC_OVERRIDE消息不等于GUIDED主控制链采用该输入。这一“消息接收支持→主控制模式支持”的错误推断应撤销。

具体版本、文件SHA和控制路径保存在`evidence/firmware_control_flow_v1.json`。未修改ArduRover、飞控参数、油门/转向映射或水动力/求解器数值；也未验证实船运行效果。

## 已修改内容

1. 动态NMPC声明及成员默认白名单改为MANUAL。RC后端要求精确的单元素MANUAL白名单，GUIDED、空和混合白名单启动校验拒绝；关闭FCU状态检查不能改变该后端契约。删除未核验的GUIDED实船验证注释。
2. mpc_params.yaml和mpc_params_B.yaml显式写入rc_override、require_fcu_state=true及MANUAL白名单。real.launch.py明确按方案传入类型正确的字符串数组，避免依赖默认值。
3. 模式管理器新增mpc_fcu_mode，默认MANUAL，自动切换默认关闭；real/SITL按B=MANUAL、运动学A=GUIDED传入。自动切换分支使用该目标，保留人工接管冷却和failsafe优先级。
4. 删除模式管理器“GUIDED统一无setpoint超时”的泛化注释，保留上层watchdog；未改超时/保护阈值。
5. 新增模式服务及launch解析回归，扩展原控制器回归。仓库规范说明位于`/home/trevor/USV/docs/scheme_B_manual_rc_contract.md`。

## 验证与保留的失败

隔离构建了修正后的两个节点和两个测试目标，未install替换原安装二进制、未重新生成控制代码。

- 18项控制器回归通过：包括MANUAL可解算、GUIDED状态拒绝、GUIDED/空/混合配置拒绝，以及原deadline/超时/输出锚点/退出行为。
- 6项模式管理器测试通过：默认无自动请求；启用B时从GUIDED请求MANUAL；已在MANUAL时不请求GUIDED；显式运动学目标仍可请求GUIDED；人工冷却有效；无效目标拒绝。服务为隔离域内私有mock，非飞控。
- 6项YAML及real/SITL两后端有效参数解析检查通过；只解析声明和参数，不执行任何Node。

首轮launch检查4项失败及完整原源码保留。随后明确区分了测试夹具与生产配置问题：SDK将数组规范化为tuple、测试遗漏禁用Node的condition筛选、受限环境无法在默认ROS日志目录写入；本次新增real模式覆盖也曾被SDK当成标量字符串，解析回归拦截后改为显式List[str]。未放宽模式值或数组类型要求，最终v4全部6项通过；18＋6项C++检查未重复运行。所有旧XML、stderr、测试及launch源码版本保留，不把首轮失败改记成功。

## 研究资产与部署边界

47冻结索引4103项、373401307字节重新核验通过；本次修改路径及解析后的真实路径与该索引、49运行输入、50组件输入无直接交集。49的533文件和50的262文件封存包全量核验，旧正常/组件结果保持原范围，不能把它们提升为实船MANUAL资格。

活动源码产生11个受跟踪文件修改及3个新增文件，全部前后版本、patch、SHA与工作区状态在本批保全。既有.zcodeignore和子模块状态保留，无commit/reset/stash。旧“工作区clean”的历史保护脚本不能直接套到当前状态，后续需明确承接这次用户要求的纠正差异；不能静默丢弃这些修改以通过旧保护投影。

安装launch/YAML通过既有symlink指向活动源码，配置可见性已经改变；原安装可执行文件保留。本批新二进制位于隔离build目录，源码修正不等于实船已部署。后续部署必须采用匹配的新节点、launch与YAML核对有效模式；本次未连接飞控或发送实船模式请求。M4/F6/P1资格仍按原独立条件判定。
