# 方案A当前状态：第38批（2026-10-20）

普通无暂停监督的Python实现与组件验证完成；实际Worker集成未通过，不授予ordinary服务资格。支持active_watchdog／worker_capability_expired两种显式原因，完整身份/配置与Source FD再认证后单次派发注册Worker stop；不注入SIGSTOP，等待按合同500ms／1s／1s记账。

组件：两组冻结实际Source原因正例、44项反例、两个真实Linux owned小子进程的SIGINT正常退出通过。小子进程的授权上下文明确为unit seed；不是实际ROS Source→Worker通过。五角色ELF全部沿用第37批组合，CXX构建0，合同/认证/Supervisor/C++未改。

实际尝试三次，全部失败并保留：
- ordinary_active_01：release调用153ms，原首phase完成晚于计划181.627ms，超过150ms被拒；推断pending未释放，实际随后26次queue_bound。Observer job0、Worker active/completed0、Source终结0，普通监督派发未进入。五角色return0。
- r2：把Recorder就绪提前到Observer之前，违背Recorder需订阅完整声明topic的依赖；release前终止，Recorder/Worker return2，其余0。
- r3：修正Recorder顺序后，提前查询Publisher参数服务仍不可用；release前终止，具体构造/发现机理尚未证明，不伪写为已定位。Recorder/Worker return2，其余0。

三轮全部已启动owned组清空，宿主扫描无遗留；源锁1841／1843／1845项未变化。独立失败审计2551输入前后SHA一致，三个SQLite完整性通过。所有旧失败与正常资格false保留；设计的成功链审计和10项实际成功raw反例未执行。

本批改进了组件派发，也暴露了启动握手缺口及两次准备流程假设错误；不能把它写成普通监督实测通过或算法失败。按已锁定停止条件不再追加actual run。下一步先实现显式区分端点/参数就绪与业务tick启动的受认证门控，保留完整图与参数查询顺序，Native及组件闭合后才预注册实测。原顺序仍为B4→B5/M0b→M4→模型事务/F6→P1→P2。阶段资格与研究结论仍false。

本批MPC交付与SHA读回仅认delivery_verification.json；不声称重读全部历史MPC镜像。
