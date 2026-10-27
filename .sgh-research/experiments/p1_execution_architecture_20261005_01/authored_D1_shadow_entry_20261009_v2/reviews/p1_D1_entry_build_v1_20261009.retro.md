# D1 entry v1 运行后复盘

机制：tool_stability_issue / 测试宏源行冲突。入口runtime编译成功；测试编译失败，关于实际测试验证的假设仍未判定。configure0、compile2、tests0、父守卫3322无漂移、owned cleanup完整。

高置信修订：仅拆开同一行的两EXPECT_NO_THROW。confidence高、impact中（恢复针对验证）、cost低、risk低；不修改控制源或条件，不使用-fpermissive或弱化测试。支持一次新的隔离v2有限构建，先独立preflight；不反复重跑失败目录。原源码/manifest/console/build_result全保留。

停止条件：新v2编译及41case通过即停，保留summary/manifest/retro；若出现新具体失败，保留该失败并定点处理。任何结果均不自动解除D1动态No-Go。使用control-postrun-retro用于ROS批次机制复盘，EDA路由/PPA指标不适用。
