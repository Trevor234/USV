# 启动身份与legacy就绪握手：有限实现批次事前反思

2026-10-09；计划A。本目录新建，不改原F5、entry_v2、D0、C0、55工具或3864父资产。

## 事实、假设与缺口

原F5 ResearchLogger只在结束后产生session_summary；arm(false)不拦截控制器physical publish，shutdown也会publish。因此先用未发生的summary构造legacy pins，或将日志关闭当作动作保持，是错误前提。entry_v2 constructor要求完整pins；recording_ready只证明图订阅，不证明收到真实双路动作与post-pair状态。原source checker拒绝legacy_ready，新版本必须显式派生。当前86个最终组件case、F5原生完整storage负例和193条冻结参考逐元素核验，都不等于完整新shadow运行。

原F5有效冻结域内≤1.2 m/s只有0.2 s；20 ms仍是工程门，主时钟硬界未证实。启动持有改变初态/热启动，须另记recipe公平性，不能继承旧动态成绩。

## A/B/C与决策

A（选定，有限Go）：隔离publisher/observer/checker新版本，构造期身份和显式release，executor侧真实legacy_ready；新增独立owned/argv/graph认证工具。实际源链接测试、有限prepare/close路径、共享readiness协议核验。只验证源码与协议组件，不执行Gazebo、D1或真实物理接管。

B：只加启动文件，不加动作门。不能消除telemetry之前动作，否决。

C：沿用旧source checker或用synthetic stub宣布完整正链。跨版本与证据前提不成立，否决。

## 输入锁、预算与停止

既有权威manifest：m0b_D1_chain_20261009/document_manifest_final.json，SHA256=199a48b144a7644d9fa71c166d6e9d7e491fdc3e965668b137b7c10b9673d416。Ubuntu父资产D1_prerequisite_closed_assets_20261009.json，SHA256=27df4957d21c29a9d724bc97a1221f0fee814d99d53f9f7be041b1e23a7124a0，3864文件。期望boot=5a417cdc-1c7f-4c5c-8186-6d7e9a85ddcb；执行前后实际复核，不将旧值当当前事实。

源码/test/CMake清单与SHA在运行前另写input_manifest及batch supplement。所有新远端目录create-only。每configure≤60 s，compile≤480 s，单C++测试target≤30 s，Python完整target≤30 s；owned cleanup每阶段≤1 s，异常不扩预算、不删除首轮失败。不进行无限继续或成功数补采。远端主机原controller/Gazebo/unreadable进程数必须0，资产差异、未知子进程、超时或证据IO失败即停止该批，不发宽泛kill。prepare/close harness只用源链接测试和owned受控子进程，不连接plant。实际ROS订阅收集器只在隔离ROS_DOMAIN_ID=156、ROS_LOCALHOST_ONLY=1中创建两个component测试节点、专用/p1_handshake_component命名topic；4 s discovery上限，不发布命令，不使用/wamv节点或Gazebo。

## 验收与边界

startup文件原子无覆盖、异常不放行；release缺失/错run/重复/未就绪拒绝；timer/helper与prerelease shutdown无physical动作。logger在首条实际测试publication之前armed。legacy_ready必须当前clock/odom/IMU/path/profile与Worker能力、完整双路pre-odom held history，图ready不能冒充。epoch/producer/history失效不可恢复旧ready。实际Worker argv和owned PID复用拒绝；保留原41个C++与37+49 checker组件case语义。真实新源链接产生的ready事件通过同版本source/bag readiness验证，注入fixture的传感器/动作/Worker消息仍标synthetic，不能升级为实际完整storage、Witness正链或域证明。

启动协议组件通过才能标记组件完成。完整owned准备/关闭、真实raw/source/typed/Witness守恒、新版本压力/恢复、当前域与时间参数理由继续pending。D1、B4、M0b、M4、F6、P1整体、physical_execute和主时钟界均No-Go。

skill control-preflight-reflect用于ROS有限实现；其EDA routing/WNS/TNS项目在本平台不适用，替换为源码身份、动作守恒与生命周期验证，未声称完成EDA检查。
