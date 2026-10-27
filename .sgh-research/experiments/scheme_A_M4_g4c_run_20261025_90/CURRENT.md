# 第90批:G4/T2-C owned(基础设施✓ 触发✓ 架构发现)

T2-C infra完整;shutdown触发命中;**架构发现**:Regulator停止路径总是先清除admission再guard→guard见job=0非目标Job。修复Option A(停止不清除admission)最小变更。owned=1。

