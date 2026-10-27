# 70 / 71 / 72 只读审查

本目录仅为私有离线反例与历史证据重读。没有启动ROS、owned或改写批次原件。

## P1：T2B / T2C阶段触发字典缺字段，真实入口不能执行

`72/implementation/t2_author_rev8/t2_scenario_driver_v1.py:308-315` 的job_received/solve_active，以及`:328-332` 的ready_window，只缓存`{observed_ns, job}`。`:354-365`原样用作command.trigger并调用校验；`t2_action_contract.py:209-210`要求精确字段`{phase, job, observed_ns, source_role}`。因此T2C的ready_window命中后先报`command trigger evidence exact fields`，到不了`:366-371`的shutdown动作；T2B同样受影响。T2A的after_grant_ms在`:352-353`自行构造了四字段，已有T2A执行不能覆盖该故障。反例见`counterexample_inputs.json`中的`actual_ready_cache_command`和`results.json`首项。

## P1：T2C审计在缺目标guard或目标实际接纳时仍可通过

`72/implementation/t2_author_rev8/audit_t2.py:99-113`只检查ready<request及Source结束行晚于request。`:105-106`先过滤`accepted is False`；`:109-111`没有拒绝decision就给True，已接纳目标从未进入检查。它也未检查`stopping_observed<=activation_guard`，`:112-113`仅比较条款字符串。下列三个反例的全部bool都True：无任何目标decision；目标在request之后accepted=True；目标拒绝guard发生在request之前。

此外`:101-103`使用`owned_reception_closed`作为stopping_observed；实际Regulator源码`observer/src/shadow/regulator_owned_execute.cpp:309-314`是在join tick/prep线程之后写这行，不能直接替代目标guard之前的stopping标志观测。

三个最小运行目录分别为`no_target_guard_or_decision/`、`accepted_target_after_request/`、`rejected_target_guard_before_request/`。运行原audit CLI读取第二目录也返回passed=true，输出保留在`audit_cli_stdout.json`。

## P2：receipt完整性检查不核对登记Job、command SHA或外来ID

71原版与72 rev8的` t2_action_contract.py:223-251`逐字相同。`:228-232`将任意action_id收入字典，`:235-246`只要求每个登记ID存在且时间递增；未拒绝多余ID，也没有把trigger的Job/phase或command_sha256与登记动作/实际command对账。各自独立的wrong_command_sha256、foreign_extra_action_id、wrong_bound_job反例均返回receipts_complete=true，见`results.json`。这不能证明现有真实T2A回执有错，但不能宣称该检查已具备完整动作/Job对账。

## Fixture与身份核对

72 rev8 `fixture/synthetic_source_m4.cpp:123-128`已跳过dot前缀临时边车，修复原子.tmp被消费。`:133-143`的Fixture接收端只验证sequence递增、ID存在与phase匹配，未等价执行Python`:205-217`的重复ID、声明ID顺序、完整Job绑定检查；例如换文件名的a1/sequence2会重复执行a1。此为接收端合同不等价，正常Driver合法命令不会自行触发。

实际重读rev8 bundle全部103文件、registry的Driver与四ELF，以及T2A/B/C的table/registry/audit pins，均一致。若修订Driver/共享合同/Fixture，必须通过新冻结身份同步；这不是要求回头重跑全部历史。

## 70批S1补证结论

原严格判定器直接读取保留attempt04的GoogleTest JSON：baseline RC0、完整32项RUN/COMPLETED；三mutant均prepared、RC1并命中登记命名断言。mutant源pin与当前原件相同，source_pins_before/after相同且与当前源文件吻合。按69原harness插入helpers后追加7用例，重新构造的字节与70当前harness完全一致，因此原25项保留。

69范围债已在组件层闭合：success与solver_invoked单独拒绝；原生维度126/40/2作为类型构造性证据且与metadata拒绝区分；真实prepare_loop提交/成功publish/真实echo免seed接纳；真实submit守卫shutdown/version禁止提交；logical尚未ready旧版本结果拒绝加新代注册/槽位/真实activate_candidate正控；普通new odom后真实激活及task/config/schedule版本维度。

关键源码：`70/implementation/supp_harness/s1_helpers_insert.cpp:17-34,67-73`；`s1_tests_append.cpp:49-78,79-129,131-151`；生成harness中`activate_taken:205-218`调用真实admission.take/activate_candidate/publish。真实Source摘取保留在`batch70_source_facts.json`。

范围仍限组件缝：旧/新Candidate为helper构造，不是Worker真实求解。70报告`:21,25`明确五项owned原子待T2、owned=0；不应为此推翻已证S1或要求重跑70。Regulator当前SHA仍为dd03d7694b494d05fd4985db2c172c45658d7d938cebb723c084daaf6c43f6b5。
