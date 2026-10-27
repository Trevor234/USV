# D1 隔离观察入口构建与有限测试：事前反思

日期：2026-10-09。本批次只在已登记 Ubuntu 研究目录新建隔离 native CMake 构建并运行针对测试。当前决定：**有限构建/测试 Go；D1 动态 shadow 采集 No-Go。**

使用 control-preflight-reflect 的根因排序、A/B/C 和停止门；其 EDA 流程在这里用于 ROS 实验管理，WNS、布线等指标不适用。

## 事实与缺口

冻结 D0 专用入口只支持 no_output，因此不能通过放宽一个模式判断取得 shadow 资格。既有 F5 bag 的 193 个冻结控制状态只有两帧速度范数 ≤1.2 m/s、最长连续跨度 0.2 s；bag 的域内里程计尾段不能替代真实控制冻结状态来源。当前没有声明可重现的当前域内 shadow 工况。

1. 根因一：模式与产物用途不一致。假设：独立 shadow-only 入口能在创建应用 publisher/Sink 前拒绝其它模式、非零注入和缺失 Witness 身份，保持 D0 字节身份。
2. 根因二：旧 legacy 首包自学身份和逐通道合并。假设：预声明精确身份与完整双路校验可以拒绝半包、时序/epoch 错误；已接纳真实 producer 变化能走统一终止失效路径，不留下 pending/ready/cache。
3. 根因三：旧 qualification 与新版本混用。假设：新 source-linked 针对测试可验证这些机制，但不能代替当前 F5 owned/实际 bag/Witness 链和完整压力恢复关闭资格。

## A/B/C 与单批次声明

- A（采用）：复制 D0 为独立观察版本，新增 entry policy / legacy 整对门，编译 `p1_regulator_shadow_observer`；运行 23 个新 source-linked case，并将字节复制的 8 个 D0、10 个诊断 enqueue 测试指向新入口编译。共预声明 41 个 C++ case。旧 55 个运行工具只按已冻结 SHA 复制为构建/owned 支持。
- B（不采用）：修改 D0 constructor 或旧 checker 的 mode 允许表。会改变旧证据适用对象，也不能关闭整条 shadow 观察链。
- C（不采用）：直接启动 F5/Gazebo 或将研究域扩为 1.3。当前可复现域、严格 shadow driver/reader、外部 worker 零注入 argv 和时间声明尚未闭合。

父守卫：`D0_closed_assets_20261009.json`，3322 项，SHA256 `d52d88ad8d90e52852e3d1411fa57a438f281ebf928c9c8a1525df5a7e8380b4`。新目录：`/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_shadow_entry_20261009_v1`；必须不存在、create-only。默认源码/build/install、正式 IDL、Worker、Witness 布局和旧产物保持原 SHA。

构建预算：configure ≤60s、compile ≤480s 且 -j2、每个测试 target ≤30s；由记录 boot/PID/start_ticks/PGID/SID/exe 的 Supervisor 拥有并有界回收。不能因接纳数或观察结果延长。本批次没有控制器动态运行、Gazebo、物理输出或执行授权。

## 验收与停止条件

构建/测试通过要求：runtime 与三测试 target 编译成功；41 个 case 实际 run、唯一、不 disabled/skipped、0 error/failure；runtime compile flags 无测试宏，测试宏只在测试翻译单元；3322 父守卫前后无漂移；host 前后无存量控制器/Gazebo，owned 清理完整；源/helper/测试/二进制与 XML/控制台身份全保存。

若编译或测试失败，保留目录与完整日志，仅按具体错误准备新隔离版本；不覆盖失败版本或盲目反复运行。通过即停止本批次，编写 summary/manifest/retro；不继续动态采集。新版本严格 shadow reader/driver、真实双路 owner、当前域内输入条件与时间政策仍单列 pending，所有研究及 execute 资格保持 false。
