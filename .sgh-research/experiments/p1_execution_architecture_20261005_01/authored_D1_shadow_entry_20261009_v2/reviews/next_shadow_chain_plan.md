# B4-D1 下一最小计划：冻结工况说明与严格 shadow 观察链

日期：2026-10-09。承接已完成的七包正文核验与隔离入口有限构建/针对验证；本计划不包含直接启动20s动态采集。当前D1动态No-Go。

**下一轮先把“能复现什么、谁发布动作、如何拒绝不完整证据”做成可运行的严格工具，再作一次事前Go判断。** 不继续重复静止样本、遍历历史目录或选尾部低速段。

## 1. 先说明并固定当前可复现输入条件

仅审已登记F5冻结参考生成器、profile解析、fallback及nominal/plant配置和少量原ReferencePrediction完整矩阵，绑定源码/参数SHA；核对参考位置步长、时间步长、u/v/r含义、实际首次u≈0.8但冻结体速约1.25m/s的关系，区分事实与未解释原因。针对twin仅核对已登记生成器/launch与reference空/非空交替的owner/清空行为；身份/源缺失则不能用旧circle替代当前工况。

输出一个当前输入recipe：明确参考几何/时间/profile、源频率、起步条件、F5唯一owner、nominal/plant和预计覆盖straight/turn/mixed/非零skew的范围。研究域仍≤1.2m/s；实测是否在域内单列，不以调低参考值自动推出实速。若须改变参考/scene参数，先在recipe写精确差异及对公平比较、旧资格的影响，不临场改模型/权重/GP/PPO/plant或扩大阈值。没有可解释的当前域内recipe仍No-Go，不用收尾零命令作动态样本。

## 2. 新建严格 shadow source 与实际 bag reader

独立新文件/版本，不改旧D0/C0 checker。启动source强校验entry policy、mode=shadow、五hook0、exact legacy expected identity、source/bin/worker/contract/run/boot；每条新增legacy拒绝/接纳/terminal事件严格schema、计数、时间和whole-pair语义校验。D0同Decision观察语义沿用，但新reader明确允许shadow与真实held_history，canonical投影不能改变。旧工具的55个SHA继续保持。

actual bag必须含完整/clock、odom、IMU、path、profile、AppliedControl、typed Decision/job/candidate/capability及所需research字段；以原始storage实际全量计数对metadata、source与Witness，不能只查metadata或decoded样本。精确核验每包AppliedControl身份/epoch/sequence/start/end/双路成功及每次冻结pre-odom双路覆盖；整个legacy链缺帧、source缺summary或Witness不完整即失败。未执行plant接收测量，所有命令语义保持publisher_command。

输出strict reader/CLI+针对负例测试：缺/伪造/重复字段、错mode/hook/身份、跨boot、history单边/缺号/变化再返回、空snapshot/null误差、typed投影不符、完整生命周期计数不符、graph owner错误、owned身份不符等。测试调用实际checker，不复制一份业务模型凑通过。

## 3. 受控 driver 与 readiness / owned 链

新driver只能启动预声明F5旧publisher和新shadow observer/原Worker；明确整个场景存在F5旧物理发布、新entry0物理publisher。执行前绑定F5/source/bin/model/contract/external worker argv（delay/native0）及boot/PID/start_ticks/PGID/SID/exe；隔离产物目录create-only且只清理本次owned身份。

source与Witness输出、actual recorder/observer先arm。启动F5后通过预声明身份的research startup证据取得producer，不从任意AppliedControl首包自学；固定exact producer后启shadow。constructor记录图arm与executor spin后真实legacy ready是两门；用有限ready预算核验exact双路owner/历史、clock/odom/IMU/reference和Worker capability。失败完整保存并有界回收；不进入measurement。

先对driver/cleanup/reader的本地或隔离针对路径测试，不启动Gazebo或伪称实际20s管线。源/bin/工具统一版本的压力/恢复/关闭受影响范围单列pending；有限case不能代替R5再资格。

## 4. 单次D1事前Go判断

Go必须同时有：已冻结当前域内recipe、实际legacy身份/history与唯一双路owner、完整新strict source/actual-bag/Witness/owned工具与负例、外部Worker五相关有效配置零、父守卫无漂移、准备/关闭有限预算、20ms工程门和带假设receipt proxy的声明。独立真实主时钟界仍没有证据时明示false。

满足后才另行声明一次20s monotonic来源测量窗、准备与收尾上限、scope与停止条件，完整保留全接受/拒绝/域外/无job及生命周期。不能按成功数延长、挑幸存窗或凑覆盖。没有任何一门则写具体No-Go缺口并停止，不改变execute授权。

验收：recipe/source/bin/tools/contract的SHA及资格矩阵可复核，有限测试实际结果与失败记录全保留，旧资产/正式消息/默认install未漂移。B4逐参数理由、M0b/B5/M4/F6/P1/execute仍按原门逐项闭合。
