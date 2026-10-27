# 方案A当前状态：第34批（2026-10-19）

已在独立派生driver中实现显式 `sink-fault-self-close-v1`：校验真实Sink失败、五个owned角色身份和配置，再按Observer→Publisher→Worker→Fixture→Recorder清理；不向已经自关闭的Observer请求正常ACK，也不补造正常尾段接收。校验或记录失败仍继续尝试其余owned清理。正常关闭分支与第33批对应代码逐字节一致。

两次冻结raw均通过独立的回溯故障清理/关机零命令证据检查；25项身份或数据错配被拒绝，9项driver adapter、8项最终状态汇总用例通过，CLI导入通过。末尾账本/driver关闭失败会使最终故障用例未完成。本批实际新控制run为0，新driver分支仅经过离线替身验证，没有实跑资格。

首run原V1严格顺序仍失败，修复run仍通过；两次normal passed=false与原ACK/尾段错误保留。Witness关闭不代表进程已退出：首run后续仍有Observer SIGINT，修复run没有该信号，但Observer清理记录晚于Publisher。两次原始清理顺序不被重写。

Stored关机零命令分别为Applied5、Applied6；两侧API成功、Fixture实际owner GID、Stored完整业务字段及Recorder关闭/SQL metadata独立匹配。它们证明命令发布与观察，不证明plant接受、实际推力或执行原子性。Recorder内建stream_accounting=false保留。

本地初次全字节核验43114路径、5382874541字节；原24个业务dirty、单列real.launch差异、旧冻结资产和失败证据保留。未新增C++构建、ROS节点、端点接管或模型切换。

V2接口已核验并形成最小计划：现有Worker钩子是pre-native工作线程阻塞，不能宣称acados内部挂起；active watchdog与有效能力回调receipt租约分别验证。150ms截止、200ms tick、1s active watchdog、600ms receipt lease不变。

B4八组pending、B5/M0b、M4、有限模型事务/F6、原P1整体验收仍未闭合；execute/true_plant/research均false。新故障profile不提升正常最终版关闭资格，也不重判原性能减半失败。

MPC交付仅以本批 `delivery_verification.json` 为准；该文件存在且passed、完整二次SHA读回通过后表示本批交付完成。历史MPC全部镜像未在本批重新全读。
