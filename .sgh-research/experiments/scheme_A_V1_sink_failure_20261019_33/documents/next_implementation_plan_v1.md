# 下一最小实施计划

1. 保持本批两个原run和正常关闭错误不变。以现有raw定义并实现一个独立的故障自关闭profile/检查分支：检测到真实Sink失败并且Observer自关闭后，以Source/Witness终结、精确owned组退出、Publisher成功近零请求、Recorder/Fixture观察和正常storage停止分别记账。不得让已终止Observer“补发ACK”，不伪造尾段接收。
2. 原normal publisher-first关闭仍保留原规则和false状态；故障profile通过不能变成normal关闭资格。先对现有两次raw进行离线判别和针对性数据/身份错配检查；没有具体新运行缺口就不再跑V1。
3. 再单列V2最小事前设计。native工作线程阻塞可能仍有主线程心跳，active watchdog与receipt lease失效分别触发和判断；保留原150ms绝对截止、200ms tick及同run不复活。已有基础组件不重复全跑。
4. V3与最终统一版必要确认后→B5/M0b→M4独占真实出口→有限模型事务/F6→P1复判→P2。当前execute关闭、八组B4 pending不清空、原RMSE NoGo不重判。

每个新实际run必须有明确触发/证据/退出预算。CDR比较区分typed callback重序列化与Stored wire，保留全部原始字节和SHA；不要把末尾字节差异直接当业务值不一致或任意忽略payload差异。
