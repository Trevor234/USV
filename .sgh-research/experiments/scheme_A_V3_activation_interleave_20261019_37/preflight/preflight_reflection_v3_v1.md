# 第37批V3预检反思与锁定计划（2026-10-19）

方案A继续基于scheme=B动态NMPC，现有运行仅shadow Observer、受控Publisher C、nominal Fixture。采用control-preflight-reflect和control-theory-veto的证据与先决条件结构；route/STA/WNS/PPA等EDA专用项不适用，不转造控制指标。

最新依据为第31批最小确认设计、第28/29批activation实际代码与Native、第35/36批终结与监督证据。第36批正式无暂停监督和所有终结原因派发尚未资格化；不能用其单次通知时延声称通用WCET。原半RMSE诊断NoGo继续保留。

本次缺口：实际Source输入在activation快照复制后、最终commit前变化。已有32容量、最多2次重验，Native手工版本/单次/持续输入竞争通过；不能把这些继承为实际DDS交错已验证。

A（选定）：Observer新增显式诊断参数await_actual_odom_once_before_commit_v1、固定25ms观察上限；仅fault-enabled、witnessed shadow、V1关闭时允许。已有一次健康accepted之后，首次原始候选reason为空，等待真实executor完成odom回调；无业务锁、无Source JSON格式化、无输入改写。原20ms抖动、150ms job deadline、因果选择、提交再验、回退全部保留。25ms等待若越过20ms必须拒绝，诊断完成与正常时序资格分开。

B：改Fixture增加命令和一次性发布。需扩大角色、身份、配置与触发协议，当前真实50Hz owned来源足够，暂不选。

C：仅复用既有Native。无法补齐实际来源与Stored关联证据，不选为本批交付终点。

GO：实现与一次新Observer构建；先运行source-linked activation Native（原因果/历史/竞争/时间检查及新增真实线程等待、超时、实际clock回调和入口反例）。Native创建本地rclcpp上下文，显式种入Ticket/RTF/lease/readiness，不创建actuator Writer。构建前冻结来源与实际链接输入。CXX编译上限120s，Native45s，初次加至多2次修复，失败目录保留。仅新Observer，四角色沿用。

实际run的GO另锁：Native和loader检查通过、保护通过、五角色完整配置认证、原合同SHA不变；唯一5s测量，45s总driver预算、128MiB原始输出，外层55s INT加20s清理守卫。run编号create-only。若25ms内无实际新odom，本case失败；若输入变化后旧快照未经重验被提交则失败。一次交错最多2轮、每轮最多32历史，第二轮为新快照；若原时限耗尽，保留真实拒绝。实际clock epoch、参考指纹改变和重复竞争本批仅组件证据，不冒充实际全矩阵。

身份与数据：五owned manifest/PID/start/ELF/source bundle/完整typed配置、Writer GID、实际odom raw CDR与Recorder Stored、原Fixture transport和nominal步骤；Source trace保存原快照、guard、selected frame、input ordinal与等待前后时刻。关闭用正常Publisher-first协议与尾部ACK，必要验证全角色return0/组空，原资格失败不覆盖。全程不做物理接管、安装、codegen或调参。

现有24个业务dirty、real.launch既有差异、所有父批次与失败已逐字节保护。本批所有输出只新增第37批目录，最终MPC create-only交付、二次SHA读回。
