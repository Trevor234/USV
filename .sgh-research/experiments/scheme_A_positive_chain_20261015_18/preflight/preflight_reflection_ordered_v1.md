# 运行前反思：A/B/C 固定顺序

观察：七组当前普通运行152次实际求解和登记成功，145次激活全因anchor_mismatch。140/145全维误差显示潜在状态门超容差。原owner独立约200ms更新，合成state为零而参考速度0.6。

假设排序：

1. 冻结输入假设与旧独立owner更新冲突（高信心）；A 真实零输入稳定历史应可合法接受，B 人为改变同owner输入应拒绝。
2. 静态零传感器与非零预测不一致（高信心观察，修复效果待实验）；C 使用 actual Applied 调用时刻和明确模型积分状态。
3. 新身份/Observer适配器隐藏可用性问题（未排除）；A 仍0就先按首门定位，不立即扩大数值容差。

A 当前方案：复用封存F5/Worker/Observer/Recorder，仅重建全零且时间轴合法的Synthetic。原始producer不改，旧合同和守卫不改。实际F5输出是否精确零由全量Applied验证，不靠理论代替。

B/C 构建准备可以并行，实验必须A→B→C。新受控owner不得继承F5 lineage；如需新Observer baseline声明，保留原判断逻辑并新锁source/bin/contract。

提交门：资产完整流式SHA/目录/别名复核通过；构建和有意义有限验证通过；完整typed配置/端点/源码/二进制固定；本机当前boot及owned回收策略已记录。满足后仅Go A；B/C在相应前项通过前No-Go。

成本/价值：先恢复正常阳性可用性证据，价值高；继续外围反例对当前阻塞收益低。本轮不启动硬件/FCU/Gazebo或physical execute。
