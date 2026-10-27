# 第102批：T2-B新代际正控——scoped Epoch生命周期设计批

## 状态
设计批：无代码修改、无run、无资格变化（M4/F6/P1/plant/硬实时false不变）。

## 交付
[scoped Epoch生命周期设计](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2b_epoch_design_20261025_102/documents/方案A_第102批_T2B新代际scoped_Epoch生命周期设计_2026-10-25.md)

## 关键设计决定
1. **方案B（选定）**：scoped generation包装层——每代是一个完整的不可变terminal原版Epoch对象；换代=满足G1-G6前置条件时换新实例+旧实例入只追加账本。Epoch类零改动。
2. **否决**：改Epoch类开reset洞（复活风险最高）；101→201（R74-07离线证伪）；换run_id（禁止）。
3. **前置条件G1-G6**：终态在册/已quiesce(复用invalidate_locked)/真实新绑定(账本全异,同内容不换代)/静态域一字不放松/跨代job单调/账本只追加。
4. **政策版本化**：scoped policy="scoped_generation_first_target_task_time_profile_v2"显式声明；旧first_successful_job政策含义不改写；普通scope(v3)路径bit不变。
5. **两级正控**（R74-07"组件验证"要求）：Stage 1组件级E1-E6（含复活负控E2、域不放松E4、无换代负控E5、quiesce前置E6）；Stage 2 owned T2B-GEN（boundary scope登记）。
6. 复活防护：换代不新增旧结果复活通道——quiesce清场+现有版本门+账本binding不可复活+job单调，T2-A"旧候选不复活"不削弱。

## 义务绑定
R74-07原文（批74审查）+批86复核"新代际正控❌未覆盖"+批96优先级1+批97任务1。

## 下一批（103）
`scoped_epoch_v1.hpp`实现+组件harness E1-E6：预登记→native构建（编译冻结Epoch header+新包装头）→单次运行→裁决。
