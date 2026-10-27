# P1/M2 原始消息接收责任：运行前反思（2026-10-06）

## 证据锁与错误前提

当前事实为 progress_v13_20261006.json：worker v8/regulator v12/runtime v28/诊断契约 revision4；上一批多拍跳过、准备等待自然释放、normal/150ms迟到已闭合。本地 CDR 审计创建0 ROS节点、0 DDS发布者，只证明已装库对规定字节的 local deserialize 行为，不能晋升为真实 DDS 接收证据。

只读主机审计 cdr_ingress_readonly_preflight_20261006.json：1123资产无漂移、控制器/Gazebo0、cmdline不可读0；已装 rclpy7.1.11/rclcpp28.1.21/rmw_fastrtps8.4.4/FastCDR2.2.7。已装 Publisher.publish支持bytes→publish_raw，Node.create_subscription支持raw=True。固定版本上游代码支持 take失败/未取到时不进入业务callback；不要求错误字节一定触发main catch或executor ERROR。

主要源：固定tag rclcpp28.1.21 executor.cpp、rmw_fastrtps8.4.4 rmw_take.cpp/rmw_publish.cpp，以及已装API文件hash。上游版本对应仍非逐指令证明已装二进制，行为必须实测。

## 根因排序及假设

1. insufficient_evidence：local API边界与真实DDS交付责任不同。H1：raw观察者/原始bag能记录部分规定字节，但目标typed reader是否交付及具体丢弃层可能unknown。
2. flow_policy_mismatch：typed业务source只记进入业务的消息。H2：可解码foreign控制能被既有身份门拒绝，前后控制及正常native链确认处理继续；不可解码样本不能补造source拒绝行。
3. model_mismatch：有限字节样本未覆盖中间件全部崩溃/恶意长度/内存耗尽。H3：本批通过只支持规定样本与观察政策，不能推导全面反序列化防护或最坏实时保证。

## A/B/C 与选择

| 方案 | 内容 | 判定 |
|---|---|---|
| A（选择） | 新建独立诊断runner副本及raw观察工具；原生产源/二进制/契约不变。Job和Candidate每类前后foreign控制各1；empty、header3、tail-1各1，共10次有限尝试。随后跑原v28 normal必要回归 | 低改动，责任可核对 |
| B | 生产订阅改成raw并自定义异常隔离，或修补executor/RMW | 缺少必要性证据，改变接收分配/调度范围；本轮不做 |
| C | 随机fuzz、超大长度或直接physical execute | 不能隔离当前机制，NO-GO |

新副本不得成为原normal runner默认路径。raw观察QoS reliable/depth64，生产reader仍depth1；逐样本约400ms，独立记录尝试/匹配端点/返回/原字节；正常消息可能与注入竞争，不能把无callback唯一归因损坏CDR。观察source仅统计实际事件；有效foreign控制使用topic/stage不同的保留job_id，不能改变合法last_received。

## 预声明验收与停止政策

- 运行只在domain96/localhost、no_output、fault-enabled诊断契约；每次前后1123资产核对，原worker/regulator/模型/IDL/F5不改。无物理发布者，全owned身份/关闭/flush完成。
- 每topic全部5次尝试记录。保存固定原blob/hash/长度；API拒绝则记sender-side rejection，目标路径未覆盖，不当作目标接收通过。API返回后raw观察者与bag看见的字节逐一按topic+hash匹配；未观察列unknown，禁止默认通过。
- 可解码foreign before/after控制须进入对应生产source并reason=foreign；不能被注册/激活/native求解。foreign Job只凭保留ID及时间窗归因，因为worker rejection不含完整payload。
- malformed若被raw收到，观察节点显式deserialize异常有记录；bag逐条独立decode，失败仍继续扫描。目标typed source只报“未观察到可归因业务事件”，不等于目标reader收包或拒绝证明。完整stderr实际日志单列，不强制ERROR存在。
- 自然合法链注入前至少1次、注入结束后至少3次native成功虚拟接纳。所有decisions物理发布false；无worker终端/调度跳拍。实际样本超门或无法恢复即停止晋升并保留失败证据。
- 原v28 normal回归通过既有完整source/bag/input/时间/activation/lifecycle门；CDR注入run不得标normal_contract_complete或execute qualified。
- publish API错误、raw/recording缺失是有效边界观察，但相应receive coverage仍pending。完成事实收集后立即复盘，不为同一个未覆盖门盲目重复；相同门连续2次失败无新机制证据停止递归。

本批覆盖Job/Candidate规定样本；WorkerCapability、其他状态/参考/stop类型损坏字节与所有malformed形式不在本批覆盖。整体M2需后续scope审查；M0b/M4/P0/P1/F6均未因此完成。认证备份、双路物理出版预算、F4速度域差异等仍待办。

## GO/NO-GO

GO：A有限、无物理输出事实验证，启动前再次核对host/asset，工具文件create-only/hash固定。NO-GO：B/C以及任何physical execute、全面中间件保证、整阶段完成声明。EDA route/STA/DRV/PPA/Slurm为N/A；对应证据采用ROS raw mcap/source/stderr/identity/cleanup/hash，不伪造EDA指标。
