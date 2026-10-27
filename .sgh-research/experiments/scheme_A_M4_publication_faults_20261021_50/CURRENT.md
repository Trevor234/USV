# 方案A 第50批当前状态（2026-10-21）

**发布/退出源码关联故障子组件通过：16项GTest及70条实际私有topic接收独立审计通过。** 第49批正常唯一出口组件沿用，publication_exit整组、完整M4/F6/P1仍未合格。

exact49 Regulator源码SHA94bbcb25...未改变。测试只新增单独ELF及工具；初轮夹具Executor接口编译失败保留，独立author_v2修复后构建通过。实际ROS组件仅一次，RC0、无外层信号、进程组空。

28对/56次私有控制RCL入口：43次真实委托、13次控制返回注入；Applied28次尝试中27真实成功、1次注入。独立解码43条Float64+27条Applied全部对应，4个证据篡改反例拒绝。已证左失败仍尝试右、逐侧成功历史不可回滚、partial terminal、Applied失败、zero请求与成功分离、grace边界及clear。1540项运行输入、36项审计输入前后hash相同。

本批无actuator topic Writer、无四角色M4故障run；owned就绪为测试种子，故障来自测试ELF return seam，不宣称现场DDS/plant故障。原stderr完整保留：2个SDK兼容告警及8块由测试setter触发的旧错误状态覆盖提示已分类，旧状态完整产生路径未证明，不作为真实DDS失败。

49封存533文件及此前历史按已登记当前基线/例外保护。旧24内容已提交、主仓受跟踪diff和暂存为空；既有未跟踪.zcodeignore及子模块状态保留，不称全工作区clean。事前缺失备份头、.gitignore与real.launch差异不恢复、不覆盖。

下一步：新注册实际owned入口grant前取消与Worker受控退出监督 → 其余原9组及F5来源适用范围闭合 → 已知模型model+plan事务/F6 → 原P1。无需重跑45/46或49正常，无差集39～42不全重验，不调数值/RTI/半RMSE、不引入GP/PPO。

报告、下一步见documents；最终资格/清单/共享盘交付分别见postrun/final_QA_v1.json、archive_inventory_v1.json、delivery_verification.json。
