# D1 既存主数据独立域分析

日期：2026-10-09。**当前可复现研究域仍未闭合，D1_launch_ready、domain_closed、B4_complete、M0b_complete、execute_qualified 均为 false。** 本轮只分析本地保存的七个 bag 解码结果、原 context/session/ledger 字节及 metadata，没有访问远端、运行 ROS、新 launch 或改动其他文件。

分析 JSON：[domain_analysis.json](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_D1_prerequisites_20261009/domain_analysis/domain_analysis.json)。解包清单：[primary_files_manifest.json](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_D1_prerequisites_20261009/domain_analysis/primary_files_manifest.json)。历史路径独立复核：[historical_path_review.md](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_D1_prerequisites_20261009/domain_analysis/historical_path_review.md)及[对应 JSON](C:/Users/sgh/Documents/Codex/2026-10-02/referenced-chatgpt-conversation-this-is-an-2/work/p1_execution_architecture_2026-10-05/m0b_D1_prerequisites_20261009/domain_analysis/historical_path_review.json)。

## 1. 输入、字节保留及完整性

主包 existing_domain_primary_v2.json SHA256=0dd9cebb687783d07b5a790fb4219a3e174d41bd5be21009d2dfa1be4a220145；metadata 包 existing_metadata_verification.json SHA256=a29336ca44a900789a3042aa44a3e875aeb0ad19571a9d3241914d16a7b9eb86。两个输入及 local_source_index.json 在分析前后 hash/bytes 相同。

16份 primary_files（四组 run 的 context、session、reference ledger、publisher interval ledger）和7份 metadata 原件已按 base64 原字节解包，23份均核对 expected bytes/SHA256。为避免 Windows 路径长度限制，保存在 primary_files/001.json 等短名称，manifest 保留每份精确 Ubuntu 源路径与本地映射；没有重新排版原 JSON/JSONL/YAML。

逐包核对 raw metadata 解码后的每 topic 计数、总数、body reader_count、bag message_count 及 metadata SHA 与正文 reader before/after：

- 七包总数均等于各 topic 合计及 body 完整 reader 总数。
- 六包 raw topic counter 字典完全一致。scheme_b_straight_001 的 metadata 额外列 /mpc/predicted_trajectory:0；body Counter 没有实际帧因此不含该键。该差异显式记录，按“未观察到此 topic＝0帧”表示后逐 topic 数值完全相同，没有补造帧。
- 14项 metadata/MCAP hash 均与 local_source_index 已登记 SHA 一致，body before/after不变；旧索引已登记的12份 F4 context/ledger/session 实际 hash 也全部匹配。F5 context/ledger 原字节是新取回证据，旧索引没有这些 raw-file SHA，不能拿 source_node hash 冒充 context hash。
- v1 最终 numpy int64 序列化失败记录 existing_reader_v1_failure.json 保留未改。成功包实际 schema=p1-D1-existing-domain-primary-reader-v2；实际 remote_read_existing_v2.py SHA256=3a15af04295bbe6af6c0a11dfd37fc2c0a5a4850dad42a705b3c0753742aec88，版本按该实际脚本与成功包绑定，不能按旧称呼混为v1。

## 2. 计算语义与异常保留

速度统一重算为 hypot(state[3],state[4])；保留原上界1.2m/s及250ms分段gap门。连续段时长定义为末样本stamp减首样本stamp，不给末帧续造持续时间。每个 topic 分开统计；尤其 /model/usv_2m/odometry 与 /mavros/local_position/odom 不合并。MAVROS stamp 为其自身时间域，不能称它是模型sim clock。

**四个 F4/F5 bag 的首个 raw odometry 样本均有约46343.22436m/s的初始化异常，stamp=.02s，平面twist约[-12593.54393,44599.29479]。异常原件保留，没有删帧或用过滤后的数据伪称全域。** 四包全量均值分别16.380714、16.350108、16.219150、15.194005m/s，被初始化样本强烈影响，不具物理运行代表性。全量median/p95和独立“solve_invoked_only冻结输入全流”统计另列；后者是实际保存的不同对象，不能称删异常后的同一全流。

raw planar norm 在平面yaw旋转下不变，但这不自动认证六维体坐标、source生成时钟、当前F5兼容或plant真实执行。本文事实是保存数值/字节及源字段；动态因果解释和资格另列。

## 3. 全量 odometry 与实际冻结输入

| bag / topic | 全量odom数；≤1.2数 | 原门下最长odom低速跨度 | raw speed median / p95 (m/s) | 全部冻结输入数；≤1.2数；最长跨度 |
|---|---:|---:|---:|---:|
| F4 baseline02 / WAM-V ground-truth odom | 4106；1443 | 19.78s | 1.246847 / 1.256670 | 215；2；0.2s |
| F4 plant_mass01 / WAM-V ground-truth odom | 4115；1451 | 17.86s | 1.247186 / 1.258857 | 224；2；0.2s |
| F4 nominal_mass01 / WAM-V ground-truth odom | 4147；1478 | 18.48s | 1.246468 / 1.255593 | 222；2；0.2s |
| F5 atomic02 / WAM-V ground-truth odom | 4427；1761 | 24.16s | 1.246131 / 1.256056 | 193；2；0.2s |
| twin_circle007 / WAM-V ground-truth odom | 1696；1696 | 169.5s | .646720 / .708894 | 0；无freeze |
| scheme_b_circle001 / WAM-V ground-truth odom | 145；6 | .5s | 3.327981 / 3.331799 | 0；无freeze |
| scheme_b_straight001 / model usv_2m odom | 5013；5013 | 100.24s | 0 / 4.0151e-10 | 0；无freeze |
| scheme_b_straight001 / MAVROS odom | 58；58 | 0s（每帧约1s间隔超过250ms） | 见逐topic JSON | 0；无freeze |

F4/F5 全部冻结流的 hypot(u,v) 均值分别1.248647、1.248930、1.248905、1.248541m/s。旧 local index 的 controller_ref_state_u 只统计 u，本文统计 hypot(u,v)，数值小差异来自变量定义，不能称旧数据变动或哈希不一致。

| run | 冻结stamp范围 | 仅有的低速冻结seq与stamp |
|---|---|---|
| F4 baseline02 | 19.856–62.656s | seq214/215；62.456/62.656s |
| F4 plant_mass01 | 20.040–64.640s | seq223/224；64.440/64.640s |
| F4 nominal_mass01 | 20.460–64.660s | seq221/222；64.460/64.660s |
| F5 atomic02 | 26.252–64.652s | seq192/193；64.452/64.652s |

四组全流分别215/224/222/193条，reference ledger按sequence与freeze_steady_ns逐条全部精确join。这证明旧 F4/F5 保存的实际 solver 输入归属，不提供旧 P1 tick-start validation Snapshot，也不能补回旧158拒绝项认证。

mixed来源也必须按实际字段解释：F4 baseline全215条与F5全193条均controller_mixed，已选odom/IMU stamp相差12ms；plant_mass有182条odom_atomic及42条mixed，nominal_mass有121条odom_atomic及101条mixed。odom_atomic行imu_sequence/stamp为0表示未选择独立IMU来源，不能将0减odom_stamp称“巨大的负skew”。JSON只对两侧已选seq/stamp存在的样本算skew，全部速度样本仍保留；这种来源语义不改变1.2资格门。

## 4. F5 24.16s低速尾段不能当20s当前shadow资格

F5 raw odom的低速段有两个：

- .06–11.08s，11.02s，位于26.252s首冻结输入之前。
- 64.38–88.54s，24.16s；与完整冻结流stamp范围仅重叠.272s。实际域内冻结输入只有64.452和64.652s两条，跨度.2s。

publisher interval ledger 302行：301个closed_publisher_interval、末条end_unknown。193条reference/freeze停止在seq193；seq193命令仍为[8.239559897,7.821046368]N，双通道保存的observed-sim闭合区间64.652–64.852s。从seq194、64.852s起，final_n精确为[0,0]，连续闭合零命令区间延续至86.324s；最后seq302没有后界，保持end_unknown。

因此64.38–88.54s低速尾段仅与非零命令观察区间重叠.472s、与闭合零命令观察区间重叠21.472s，其余2.216s没有已闭合publisher覆盖。将完整24.16s写作“20s低速求解/当前shadow资格”会跨越停止产出实际冻结输入、零输出和末端未知三种不同事实。

**事实**是停止出现新的ReferencePrediction、零final_n与账本边界；“进入standby/收尾”是有依据的解释，但interval ledger没有control_source/status字段，不能在此写成已证实原因。双通道observed-sim区间仅证明本地publisher调用观察覆盖，不是plant接纳区间或独立真时间界。

三个F4最长低速尾段也主要出现在冻结流结束/零输出以后：与冻结stamp跨度仅重叠.316/.2/.2s；与非零命令观察区间仅重叠.516/.4/.4s。因此F4 min-u线索现在得到更精确说明：确有两条域内冻结输入，但没有较长域内动态冻结覆盖。

## 5. 旧 circle 的证据升级与仍未闭合项

twin_circle 全部1696条odom均≤1.2，max=.7352783957、mean=.6040089280m/s。不能再把它只描述成文件名线索；主数据确有低速运动轨迹和非空弯曲参考摘要。但首个ReferencePath为空也不能推出始终空：

- 336条 /path/reference 中173空、163非空，非空均217点。初始11条空后，余下325条按保存主题序号严格空/非空逐条交替。
- profile同样336条、173空/163非空；非空868elements、dims[217,4,0,0]。空掩码按主题序号一致是事实，profile摘要缺逐条timestamp，因此不能认证精确同消息配对或同publisher。
- 非空参考摘要215个三点曲率中149个超过1e-4，max约.112105292m^-1，其余有近零段。这是存在弯曲参考的数值线索；主包没有这些非空path完整XY，无法在本地重建路径形状/曲率分位数或认证纯圆。交替清空是否多publisher或任务机制，当前正文不能判断。

三点曲率在低速/近重复位置时可被噪声放大。twin全量maxabs约589.845m^-1不能称可信转弯半径。独立路径复核按原≤1.2门保留全部数据，再**仅为诊断**考察固定.1–1.2m/s运动段：最长158.6s、1587点、路程102.300m，yaw展开净变5.74747rad、位置course展开净变5.81720rad，abs三点曲率median=.0646081、p95=.1287519m^-1。它们支持“持续弯曲运动存在”的推断；.1下限没有变成资格门，也没有使当前F5 lineage、模式或D0字段闭合。另列.2/.3诊断下限敏感性，不择优取资格。

scheme_b_circle001有完整273点参考，曲率含直段、正曲率和负曲率；它的实际odom max=3.335497m/s，原≤1.2内只有.5s启动段，不是低速circle覆盖。scheme_b_straight001的model轨迹近静止，MAVROS轨迹也是极低速噪声；巨大曲率不能认证转弯。

三包Research/frozen_records均0，记录的six-state convention/current_F5_compatible/D0 snapshots认证标志均false。实际历史低速运动不等于当前观察版可复现来源。旧报告 /home/trevor/usv_vrx_logs 路径与 USV/data/sim_bags 的alias关系仍未知；metadata/MCAP hash验证不能独自证明文件系统路径别名。

## 6. 最小下一步与保持的资格边界

本轮已经恢复了既存资料中能得到的域内样本和来源正文，继续宣称“只差从Windows补回CSV就有20sF5域内shadow段”是不成立的。最小下一步是先形成并审查一个**可复现的原≤1.2动态工况方案**，明确参考非空/清空机制、实际path/profile publisher来源、当前支持入口、source/binary/contract与冻结输入测量窗，而不是先启动新实验后选样本：

1. 对twin低速运动/弯曲参考，固定其非空参考的构建方法、交替清空原因与来源身份；已有摘要足以说明旧转弯线索，仍不足以移植成当前F5 recipe。
2. 对F5当前straight参考，面对约1.25m/s的实际全冻结流，明确原研究域能否由已存在工况复现。若需改变参考、路径、模型或控制参数，应单列受控变更和重新资格范围；本轮没有做这些改动，也没有扩1.3或放宽连续门。
3. 当前专用diag5仍仅no_output；新shadow观察入口需要受控设计及新source/binary/contract绑定、控制门等价与负载验证。历史F5同锁资格不能自动继承到新观察binary。
4. 新测量必须记录真实validation Snapshot、predict success、完整逐维computed/finite与时钟来源。旧158认证缺口、20ms真实界、plant执行接纳保持未证明；receipt插值和同公式自洽不填真值。

本报告仅完成历史主数据的独立域分析、完整性核对与原字节保留。全部qualification为false，未执行新D1实验。

