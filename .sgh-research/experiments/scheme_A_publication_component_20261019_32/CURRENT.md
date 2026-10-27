# 方案A当前状态：第32批（2026-10-19）

新派生regulator已接入共享publication_result_v1.hpp：两侧API返回、每侧实际start锚点、span/gap/rate和关闭结果分账。既有p1_admission fallback、完整合同和协议逐字节未改；execute硬禁用仍在。

首次构建通过，新runtime ELF和一个纯C++Native目标编译完成。14组事件、117断言通过，约73.67s；编译输入1403、runtime loader库54。Native无ROS头/链接/context或执行器端点，send为注入局部事件。新runtime的实际publish分支没有运行，不能称M4或双侧真实执行资格。

新ELF SHA：ada12f87305c266f53eccce249548ab882ad0e907f9865182a2c7315a0f50177；source bundle SHA：71b1bcff743091a931af075df3a34bd549b0930d0093e55d08ea99519f02b2a9。新候选没有owned运行身份；其余四角色只复用原精确bin，不继承旧Observer认证到新ELF。

原第29批101/101接纳及原RMSE失败保留。B4八组pending、B5/M0b/M4/F6/P1仍未闭合，execute/true_plant/research均false。旧业务dirty改动及单独real.launch.py变化保留。

下一步优先V1当前版本真实Sink第一次入队失败：先完成新owned prepare/peer/source绑定，预注册一个有界故障触发及关闭记录；不重新扫同类正常run或启动调参。V2将native阻塞/active watchdog与能力receipt租约分别设计，V3再核验来源/时钟重验交错。顺序B4/最终版确认→B5/M0b→M4→模型事务/F6→P1复判→P2。

MPC只写本批新目录。最终交付权威为delivery_verification.json；该文件不存在时为待交付，存在且passed/二次SHA读回通过后表示交付完成。旧批归档和失败不回写。
