# 方案A第64批：两轮代码与正式登记独立复核

日期：2026-10-23。正确时间线：61为上一轮D1–D6；62为E1–E6；63为正式构建/登记；64只做审查与私有验证。

[完整报告与owned W2实施意见](/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_registration_review_20261023_64/documents/方案A_两轮代码与正式登记复核及owned_W2实施意见_2026-10-23.md)。

## 已确认

- 最终63源码：39项、12变异、源码10项、Driver观察后5例独立通过。
- bundle95项、Driver、3个新ELF、复用Recorder、registry和registration与当前文件一致；真实编译宏可核对。
- 当前三个acados运行库解析文件匹配registry；原Driver尚未核对真实Worker加载maps。
- INDEX_SHA沿用56的合成EVIDENCE，不能误认为合同文件SHA篡改。
- Job2/ordinal1源码可达，实际owned路径尚未运行。

## 有限残余

- bootstrap提前失败时，观察集合仍未初始化，finally可再次抛错阻止driver_result落盘。
- 最终判据需交叉核对verified release/原截止/正确target terminal；publication不能以accepted_registration替代。
- 准备后真实拒绝虽阻止C，目标Boundary仍可能allowed；长等待正控正确，不是C放行漏洞。
- 9步preflight为手抄部分静态校验，nonce0可漏过；真实Driver该预检会拒绝。
- 运行库实际加载认证和W2独立审计仍未闭合。

## 下一步

一次运行前有限收尾与审计入口→重封受影响源码/Driver/ELF/登记→一次有限owned W2、自动重试0→独立对账→原矩阵对应子项/M4→F6→P1。无需新增C内部挂起、重复release协议或新DDS通道。

本批只新增64包，未修改62/63及旧资产；固定218项输入、保护306项选定历史输入和21个普通工作区文件。未启动ROS/owned/硬件，离线测试实际调用acados。M4/F6/P1/plant/硬实时全部false，实船B保持MANUAL＋RC覆写。
