# 第128批：工厂路由与准入修正组件评审完成

真实复现checked acados拒绝非有限模型后被CasADi构造接纳的缺口。派生补丁在两个工厂入口检查共同30项参数，保留有限参数的正常回退。未修改生产源。

78项矩阵符合预期（含9项关闭配置API不可用）；实际成功求解52次，其中CasADi/IPOPT 28次。16项有限参数对照最大数值差0；4个变异均由指定运行时断言捕获。私有补丁应用核对通过。

80项输入、127批786项、126批1786项无漂移；本轮39项工作区状态无漂移。两次前置构建/加载失败原件保留。

生产源修改0、ROS/owned运行0；完整ROS构建未执行。M4/F6/P1/plant/硬实时全false；生产B仍MANUAL＋RC覆写。

[报告与详细执行顺序](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_factory_routing_20261027_128/documents/方案A_第128批_工厂路由实证与准入修正_2026-10-27.md)

下一步：在新派生批中执行RawBackend共同头复用草案与cold/native政策回归。具体进入/退出条件和限制见`postrun/next_plan_v1.json`，不自动落位或启动owned。

MPC镜像采用排除编译产物/缓存的规则，交付是否一致以独立回读回执为准。
