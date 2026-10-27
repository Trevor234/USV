# 第107批：N4/F6有限模型事务设计批（接口映射+场景设计）

## 状态
设计批：无代码修改、无run、无资格变化（F6/M4维持false）。

## 关键事实
- F6原定义定位（首选A §5.2）：有限模型/固定偏置阶段——每候选快照绑定有限参数版本，先验证事务机制
- **缺口现状确认**：p_global(30维)仅在构造时写入（acados_backend.cpp L131-133），但**运行时setter路径存在**（vendored C API三setter：update_params/update_params_sparse/set_p_global_and_precompute_dependencies，precompute捆绑=天然原子单元）
- 维度布局：NX8(增广)/NU2/N20/NP6(每阶段x_ref)/NP_GLOBAL30(19 hydro+6Q+2R+2Rd+1Qf)

## 交付
[设计文档](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_n4_f6_design_20261025_107/documents/方案A_第107批_N4_F6有限模型事务设计_2026-10-25.md)：
- N4五义务→现有接口映射表（prepare/原子提交/tick激活/拒绝/warm独立）
- 需新增仅`model_transaction_v1.hpp`（版本戳+两相提交+互斥+按版本warm账本）——生产包零修改
- harness场景F6-1..F6-6（等价对拍/两相互斥/逐拍对拍/旧mixed拒绝/warm回切/无事务负控）
- M0/M1=两个有限参数版本（合同hydro vs 有限扰动），不codegen、不GP/PPO

## 下一批（108）
model_transaction_v1.hpp + test_f6_model_transaction.cpp：登记→native构建→单次运行→裁决
