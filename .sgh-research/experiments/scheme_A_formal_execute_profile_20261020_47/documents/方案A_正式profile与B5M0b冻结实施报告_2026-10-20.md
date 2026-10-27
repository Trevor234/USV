# 方案A 第47批：正式profile、owned入口政策与B5/M0b冻结

2026-10-20。承接46的当前版本正常来源窗及43/44/45的政策、同源契约和正式准备组件。本批完成两个原定冻结动作：**正式execute目标profile/来源/owner/bootstrap政策固定；真实不可变合同与证据索引提交并核验。**

## 当前资格

| 层次 | 实际结果 |
|---|---|
| 组件验证 | 同源双profile校验、纯owned入口政策核、冻结绑定校验通过 |
| B5/M0b | 选定有限工程域的参数/政策合同已冻结；新合同pending8清空，旧pre-freeze原件仍有8项 |
| M4 | 新Regulator实际唯一输出入口及其正常/故障确认尚未完成 |
| F6 / 完整P1 | 已知模型事务及原P1联合复判尚未完成 |
| 研究结论 | 未新增控制性能优越性、plant/6DOF、一般转弯/mixed、完整1.2m/s域或硬实时证明 |

新合同中的`execute_qualified=true`表示v3规定的工程合同冻结状态；本批实际运行释放开关`physical_execute_release_enabled=false`，未启动ROS/物理输出。纯组件输入中的GID、PID和API返回均为确定性测试事实，不能当作M4实际所有权证据。

## 修改与作用

1. `implementation/current_contract_spec_v1.json`派生同源profile目录，原diag10/81字段和旧v3识别保留。生成器从同一份spec生成Python/C++规则及资源约束，正式schema仍为v3、84字段。

| 相对旧正式pre-freeze的接口字段 | 新值/含义 |
|---|---|
| supported_parameter_profile | P1_owned_nominal_execution_20261020_01 |
| baseline_input | F5_NOMINAL_SOURCE_OWNED_REGULATOR_20261020_01，具体校准资产另表绑定 |
| preparation_retry_policy | owned reference-pair完成门；脱离旧phase Publisher授权 |
| propagation_semantics | 新Regulator逐侧真实成功API的publish-start历史；mixed保留独立IMU戳；未来held输入、RK4名义点预测 |

仅上述4个字符串字段构成profile语义差集。N20/dt0.2、19项水动力、Q/R/Rd、幅值/映射、rho80、H600ms及年龄/RTF/jitter/gap/span/watchdog/lease/清理预算均未调参。最终frozen合同另有5项资格/证据字段变化：qualification、execute_qualified、parameters_are_diagnostic_only、pending_final_calibration、freeze_evidence_sha256。

2. `owned_execution_policy_v1.json`及`native/owned_execution_entry_v2.hpp`固定入口规则。必须绑定新run/boot/合同/manifest/GID，非owner输出数为0，旧物理owner已退出。初始两侧均unknown，数字零不构成权威；每侧真实API成功后，才以该侧实际起始时间建立锚点。部分失败保留成功侧事实，失败侧unknown，业务终止不自动复活。

prepare grant即固定tick起点，首零请求pair须在200ms内开始；后续按T200ms维持零请求，直到输入/能力等门禁有效且可提交业务。最大gap240ms、pair span5ms、tick jitter20ms事前固定，迟拍不补发追赶。HOLD从最后接纳激活计时，重复发布不续期；invalid直接ramp；unknown侧只能请求零而无变化率资格。shutdown把零请求、各API成功、进程退出和plant未知分别记账。

这些是可编译、可对拍的离线入口政策核，M4还需把它接入实际Regulator计时、准入、owned图和发布API。当前Observer39仍保持原diag10+shadow；45仅正式prepare；未把旧legacy Applied改名当作新owner历史。

3. `python/freeze_binding_v1.py`要求调用方同时提供独立固定的index与contract SHA。它严格解析完整v3、核验去除marker后的合同模板、policy/spec、全部文件字节与大小、参数来源、故障判据和资格范围。64hex形状不能替代真实证据；更改任何冻结参数/资源或证据字节会拒绝。路径要求规范绝对路径及无symlink别名，读取期间核对文件身份并采用有限预算。

索引先绑定marker为空的规范化frozen模板，再把索引实际SHA写入最终合同，避免自引用hash。冻结文件已设只读并按hash封存；不宣称操作系统不可修改、文件系统已加锁或共享盘持久性得到证明。M4启动仍需重新核验和现场owned门禁。

## 实际验证与失败保留

- Python/C++原始字节对拍：641项通过（原385＋新256；53项预期接纳、588项预期拒绝）。旧类型/重复键/NaN/资源/mode规则保留；execute运行模式继续拒绝。
- 纯owned入口政策：92项通过，覆盖unknown、双成功、partial、实际逐侧时间、启动整流gap、HOLD等号/超界、5次miss、ramp、jitter、shutdown及context身份/类型。
- 真实冻结绑定及altered-copy：24项通过（3项接纳、21项拒绝），包括实际包、精确副本、伪造marker、源文件同大小改写、阈值/资源改写、旧pre-freeze、错误profile、越权execute。
- 同源生成5个输出逐字复现；两次离线构建涉及3个probe ELF，均成功，未重编译五个业务ELF。
- 19项提交条件和23项最终独立审计通过。最终审计再次逐字核验索引全部4103项资产。

初轮入口测试有1项失败：把右侧ramp末值预期写为0；右侧实际锚点晚200ns，正确剩余为0.000016N。原v1源码/请求/输出/失败报告/ELF保留；v2修正预期，并根据代码审查增加等待期零请求、bootstrap不可复用两条约束及反例。未修改数值预算，也没有把失败覆盖成通过。

本批前后各核验50,790条既有记录路径、6,548,663,296字节；原24项业务diff保持151,961字节、SHA d901511293df5be4aecb988509e4c4107977dc7c05f042286869c36e0a239ba5。已单独登记的real.launch.py差异、Git HEAD/分支、旧封存资产与全部失败保持本批开始时状态。原MPC历史镜像未在本批全量重读；本批交付的逐字核验以delivery_verification.json为准。

## 冻结身份与适用范围

- spec SHA：`dca89c6559110290ece07e6102ee4f0bd28f38031f5dfe1702aaab81be45846f`
- policy SHA：`475d093f034165b94a09dde577a4462dc3c575752e25a99364d4ac699955918b`
- freeze index SHA：`1d750a7eeb32f379f2be5dd516533f6f785e091c6b30082dda68e51b3f100081`
- frozen contract SHA：`19d6962b859533134f797f005dfa7af2b3434dae16cd6bd550e96e17cafdc23a`
- 索引文件数4103，合计373,401,307字节；包括源码、当前校准ELF、模型、配置、工具、阈值来源及新政策组件ELF。

校准来源仍为46的owned nominal直行0.05m/s短域：20.002935074s、101个动态Job、窗内100/100接纳、2个mixed Job。完整legacy启动API gap约1.54s仍是240ms失败事实；新bootstrap政策由既有T/gap预算和确定性规则固定，等待M4实际确认。近1:1外推、可信prepared图、名义点模型、本地有限调度仍为工程前提。F5 nominal/plant/reference与当前fixture的具体映射必须在M4差集审查中核实；0.05校准资产不能自动取得原M4整体或plant资格。

原M0b允许shadow或无输出校准；本批没有另增“完整no_output业务长跑”门，也没有要求首次execute观测作为冻结来源。旧半RMSE NoGo（0.009195365994 > 0.007392495755）保留，未作为新的P1门槛或通过理由。

## 下一步

按固定顺序推进：**M4新Regulator唯一输出入口 → 受影响差集回归与新正常/故障确认 → 已知数值模型事务/F6 → 原P1联合复判。** 不重跑45准备、46正常校准或无差集的39～42故障；不调RTI/权重/半RMSE，不引入GP/PPO。具体任务、有限首跑预算和STOP见[下一步实施计划](下一步实施计划_M4唯一输出_2026-10-20.md)及postrun/next_implementation_plan_v1.json。

本批目录`/home/trevor/USV/.sgh-research/experiments/scheme_A_formal_execute_profile_20261020_47`；MPC交付目录`/home/trevor/MPC/scheme_A_formal_execute_profile_20261020_47`。冻结索引引用本机原始资产绝对路径，本批MPC镜像不重复复制所有前序原始数据；校验依赖原路径可读和精确字节一致。
