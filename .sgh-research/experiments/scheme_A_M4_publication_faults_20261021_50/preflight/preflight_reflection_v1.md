# 第50批事前反思与有限验证选择

2026-10-21，verdict=GO：仅允许原49源码关联的发布/退出故障组件及其独立私有topic记录检查。继续采用control-preflight-reflect、control-theory-veto与control-postrun-retro结构，EDA领域指标不适用，文件按用户要求归档MPC。

证据锁：49 archive SHA 7ca703b906bc95e154816ef591b9df6a8b5cadcdd4e2842b42ad3b254dbc87fc；QA eb2ef9d422b83d3bc0de0739b1b781acdafd4b5cb1adcfd66a496a2762f00ca7；receipt df7a3cffd7e702b7544fa0a13d1c01209dfbcad56a5eaef2a296e0cc55ab8931。49正常唯一出口组件通过，原9组故障、F6/P1未通过。沿47冻结合同与判据，不改参数或复跑正常源。

机制排名：1.insufficient_evidence——新Regulator publish、owned_pair_record、Applied和finish_tick组合在partial及关闭异常下尚无对应源码关联证据；2.flow_policy_mismatch风险——不能把零请求或仅成功一侧标成双路成功，也不能把组件种子身份当真实owned图资格。48 Recorder互等已由49独立成功闭合，不再作为本批待修复问题。

方案A（选定）：测试直接包含exact49源码，用已有测试构造器和friend；只在新测试ELF拦截精确私有publisher handle的rcl_publish返回，成功调用委托真实RCL/FastDDS，失败是声明的return seam。独立订阅者捕获成功侧Float64与真实Applied；核验实际源码的双侧尝试、锚点、历史、terminal、normal=false及shutdown事实。confidence高、impact高、cost中、risk低。验证对新执行组合有信息增益，不重复47纯政策52项。

方案B：立刻在实际四角色入口增加故障hook并重编所有角色。当前最小缺口可先由A解决，B后续仅对确需实际时序/监督的case注册，避免扩大差集。方案C：重跑49正常或全部39～42；对partial组合无新信息，不选。

假设表：exact49源码/政策在编译前后hash相同（必须核验）；拦截器仅测试ELF和精确私有handle生效（nm导出和调用计数核验）；成功侧真实wire、Applied可独立观察（运行前订阅匹配及事后完整计数核验）；身份/lease/tick由测试种子提供（显式有限前提，不授予真实owned入口资格）；错误返回来自受控seam（不称真实中间件故障）；原父包和已有未提交状态保留（前后全量本地保护）。

阻断理由：无针对该有限组件提案的阻断。GO不授权普通生产release或扩大结论。无veto override。依本地47故障矩阵、49原始日志/审计和安装SDK publisher接口为依据，无额外外部事实或算法比较。

运行前固定case清单、测试源码/ELF/依赖/命令SHA、timeout和预期；自动重试0，构建失败保留并显式派生版本。STOP：非私有推力topic、拦截不生效、未知调用/丢失、成功侧回滚、未关闭线程/owned组、父包或工作区变化。partial等预期normal=false保持，额外未解释异常仍失败。完成后只提升对应组件，不把publication_exit整组或M4/F6/P1提升。
