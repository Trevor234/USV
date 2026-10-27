# B0合同校验实施前置反思

日期：2026-10-07，Asia/Shanghai。沿用control-preflight-reflect已读evidence-lock/checklist/reflection-artifact；EDA特有指标不适用，以源码/合同/MCAP/owned/资产哈希代替。

事实锁：progress_v15 SHA 43da08e4fd292b16a05feb60a13210d569f66cf9c4ea1169561ab0d5d48038a6，contract5 SHA 0e3eb70e74e922059ff17014ab1971b8a9fe20be0171964fc26410b7d769a933，1196保护资产，worker v9/regulator v13/runtime v29。前轮只读数据分析不改变物理资格。最新M0b参数来源/政策最小计划已交付，M0b正式、R5、M4/F6仍false。

根因排序：1公共loader与resourcewrapper都绑定diag5/v2；2regulator非诊断execute与诊断lease门互斥；3除资源外原字段类型/finite/支持域校验不完整。假设：显式schema/角色/模式与固定候选profile能解决兼容并拒绝错误类型，且不靠填写qualification让未冻结配置进入物理输出。

选A：固定F5_P1_candidate_20261007_01、v3独立execution/resource revision1、严格重复键/类型/finite/字段集合/模型值/资源域；跨C++/Python同原始JSON corpus；runtime release=false；正常diag5与pre_freeze各一个10s无输出run。B：直接flip flags拒绝，互斥且无数值来源；C：开放任意阈值/完整物理run拒绝，超出B0并未经B5冻结。

GO条件：源码/依赖原SHA和1196资产核验、host无控制器/Gazebo且可读、完整受控差异及原件备份、build和必要回归通过、原始corpus预期结果跨语言一致、明确release=false，startup拒绝无source/物理publishers创建。只有新guard闭合后才启动两个无输出短run，继续保留source/bag/应用分账/owned原门。

NO GO：任何实际execute startup、R5压力宣称通过、formal冻结宣称完成、history/log合法范围冒称覆盖充分。所谓frozen fixture只在纯schema测试目录用于验证结构与release拒绝，不是资格化合同；本轮只交付pre_freeze实际候选资产。diag5完整严校验是受控拒绝增强，不声称非法输入接受行为未变。旧recognizer与历史checker/runner原分支不变。

STOP：unexpected资产漂移/来源不明/跨语言结果不一致/新物理端点/坏字段启动通过/owned清理不完整/原checker故意改宽。有限跑数、计数、具体通过数量由实际结果生成，不预填写测试通过。对照不是C0日志witness对拍，也不替代B1/R5。
