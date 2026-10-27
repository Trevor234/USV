# 实船方案B：NMPC使用MANUAL＋RC覆写

2026-10-21，依据用户明确的既定契约纠正。

实船`scheme=B`使用动力学NMPC，输出`/mavros/rc/override`，FCU控制模式为`MANUAL`。控制器保持armed及状态新鲜度检查，`allowed_fcu_modes`严格为`["MANUAL"]`。`GUIDED`、空白名单或混合白名单在RC后端启动配置校验中拒绝；关闭FCU状态检查也不能改变RC后端的模式契约。

**该校验是启动期硬拒绝**：违反时 `mpc_node` 在构造期抛 `std::invalid_argument`，`main` 捕获后打印原因并以退出码 1 结束（不是 abort）。因此任何未来的 `rc_override` 组件测试或独立仿真，都必须显式带 `allowed_fcu_modes=["MANUAL"]`——`require_fcu_state=false` 不豁免这条。

模式管理器的`mpc_fcu_mode`默认`MANUAL`，自动模式切换默认关闭；实船和SITL入口按方案显式传入目标。`safety_params.yaml`**不再**声明这两个键：两个 launch 都会按 scheme 覆盖它们，在共享 YAML 里重复声明只会制造"改了却不生效"的假象。只有仓库运动学`scheme=A`速度setpoint后端使用`GUIDED`。研究方案A以`scheme=B`为基线，不能将研究名称A与launch的运动学A混为一谈。

当前仓库ArduRover代码中，`GCS_MAVLINK::handle_rc_channels_override`把MAVLink字段交给`RC_Channels::set_override`；`ModeManual::update`经pilot输入读取RC并设置转向/油门。`ModeGuided::update`按自身guided子模式和目标驱动控制。接收到RC_OVERRIDE消息不等于GUIDED主控制链采用它，不能以接收支持为由改变B的契约。部署仍需依据实际固件版本确认RC接入参数和输入映射；本文件不声称已做实船运行验证。

Git记录：2026-09-05的`d00f401`导入B栈时已有GUIDED默认；同日`806cf95`又加入“不含GUIDED”的错误告警，并写入未由此次审计证实的“2026-07实船验证”注释。此前审查沿用了这个错误组合，现已纠正活动源码和配置。旧冻结快照及错误证据保留，不改写历史。

本次只在隔离构建/测试目录验证，不启动MAVROS、不连接飞控、不发送实船模式请求，也不覆盖既有安装二进制或研究冻结包。部署时需重新构建受影响节点，并核对所用launch、YAML和实际可执行文件版本；源码修正不等于已部署到实船。
