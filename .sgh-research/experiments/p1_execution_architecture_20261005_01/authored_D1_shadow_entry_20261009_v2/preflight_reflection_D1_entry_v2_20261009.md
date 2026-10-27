# D1 entry v2 定点构建事前反思

日期2026-10-09。承接preflight_reflection_D1_entry_20261009.md的同一有限目标、41case与全部动态No-Go，不扩范围。

根因排序与假设：1.已确认GTest宏同源行label重复，拆行应修复；2.是否还有具体编译/断言错误待编译和41case判定；3.当前动态域与strict shadow链未闭合，通过本批不能替代。

A/B/C：A采用仅测试断言拆行的新entry_v2；B不采用-fpermissive或删断言，不能保持验证意义；C不采用原目录重构建，避免覆盖v1失败。生产source/hash、41case数量及业务/公式/合同/默认install不变。新远端目录authored_D1_shadow_entry_20261009_v2必须不存在、create-only，继承3322父守卫及额外只读核验v1全文件SHA。

configure60s、compile480s/-j2、每测试30s，由原Supervisor有界拥有/回收；host前后clean、原3322/v1无漂移。0 disabled/skipped/error/failure且23新+18继承=41全部run为通过；runtime无测试宏，最终source/bin/XML身份明确。通过即停，任何失败保留原文定点处置，不启动F5/Gazebo/D1动态。采用control-preflight-reflect的机制与停止门，EDA指标不适用。
