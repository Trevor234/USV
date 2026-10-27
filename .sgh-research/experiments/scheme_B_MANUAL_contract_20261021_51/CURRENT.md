# 第51批：纠正实船B的MANUAL＋RC覆写契约

用户原契约由原实施方案108行及632项确认。GUIDED默认来自2026-09-05导入，错误“不含GUIDED”告警来自同日后续审查；此前未纠正该冲突是审查遗漏。实际MODE请求历史未由这些静态代码证明。

动态NMPC默认及B配置恢复MANUAL，RC后端拒绝其他白名单；模式管理器以mpc_fcu_mode选择B=MANUAL、运动学A=GUIDED，自动切换默认关闭。30项检查通过：18控制器＋6私有模式服务＋6有效launch/YAML。构建两个新节点及测试目标，未install或连接FCU。

初轮launch类型、夹具条件筛选、日志路径失败及各源码版本保留，最终v4通过。原47冻结4103项、49/50封存包字节保持。活动源码11项修改＋3项新增有前后快照和patch；旧未跟踪/子模块状态保留，禁止用旧clean投影抹除本次用户纠正。

研究方案A以scheme=B为基线，不能与launch运动学scheme=A混淆。既有隔离nominal组件证据不等于实船MANUAL验证；完整M4/F6/P1未因此提升。后续先承接本次有效配置/工作区差异，再按原M4运行时故障→F6→P1推进。

详见documents报告、postrun/final_QA_v1.json及delivery_verification.json。
