# P01通用证据独立重放层次

实际读取第81批登记指向的 `78/implementation/runs/T2B_P01`；没有启动任何ROS节点、rclpy.init、角色、信号或owned；sqlite使用mode=ro，CDR只反序列化。38个run普通文件读取前后逐SHA一致。

1. **身份链**：登记→Driver、registry→登记、合同、动作表一致；audit_tool登记pin不一致。角色ELF本身匹配，但三个新角色bundle检查因audit_t2.py已修改而拒绝；Recorder独立旧bundle通过。因此不可能靠后续数据完整性把当前冻结身份链宣布通过。
2. **Source/API事实**：29条Decision/API/Applied连续1..29；真实API最大单侧gap约200.11ms、最大pair span150265ns，数值/限幅/斜率/零结尾通过。Decision诊断标签与Job时间/anchor检查通过。Source generated=emitted=1174，dropped=0；witness closed/无溢出/非incomplete/observation_complete=true。四角色记录rc=0、group_empty=true、无error；Regulator受控零关停未超grace。
3. **Stored**：SQLite integrity=ok；1130条；Typed Source/Stored多重集和逐字段通过（Jobs2、Candidates2、Decision29、Applied29、两侧各29）；capability完整payload34/34；Fixture真实transport/GID1129条均在Stored，有额外1条允许的capability；Fixture各topic实际计数与Stored一致，Recorder干净关闭。
4. **不适用的W谓词**：原样运行通用W check_fallback_policy会拒绝tick4(age399.95ms)ramp_zero，但该tick reason=worker_unusable、前序真实transition=task_time_reference:epoch_terminal；生产fallback显式`!invalid`才允许hold，worker_unusable应invalid/ramp。该旧W函数未适配T2 invalid分支，保留原始fail不能据此再报实现缺陷。
5. **家族和阶段资格**：这些通用数据检查不证明动作发生于boundary内部、不证明release因果绑定、不修复audit身份，也不替代T2-C时序或T2-A恢复条款。13项旧审计未执行上述Stored检查；本次新私有重放补出有限数据事实，不将旧registration/审计改成合格。

脚本 `validate_t2b_p01.py`、stdout和`validate_t2b_p01_result.json`保留每项独立结果；任何单项失败均不阻断后续检查。
