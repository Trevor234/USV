# 第40批复盘

假设A在当前selected shadow/nominal配置内通过：受认证门控后的V1仍满足实际Accepted→Applied→认证phase ACK→arm→真实首次拒绝。独立故障profile实际完成，Observer Source失败语义保留，Stored/Fixture shutdown_zero成立。没有新增C++实现和构建，五个注册ELF保持。

主要机制：此前是insufficient_evidence（当前最终组合缺实际运行），本批用一次明确刺激补齐；不是模型/性能改进。次要边界为Source故障与正常关闭前提不同，不能合并资格。

下一步普通lease即时监督：confidence=medium、impact=high、cost=low、risk=low（本地shadow+有界owned关闭）。先确认callback gate与监督入口的因果依赖，再预注册一次；STOP条件是未真实触发lease、原因或身份不符、派发/退出/记录链任一失败。恢复身份验证先按已证材料做差集，不自动开展参数调优或重复V1。

依赖经验：完整准备先于业务；原150ms不变；真实Applied先于arm；fault Source不能冒充normal；owned退出与独立Stored命令分别证实；原失败必须保留。EDA route/STA/WNS/PPA不适用。无新阶段或研究结论。
