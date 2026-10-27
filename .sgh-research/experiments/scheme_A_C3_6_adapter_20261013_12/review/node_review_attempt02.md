# C3.6 实际 Node v2 修订只读复审

当前source bundle v2全部声明文件与活源码SHA/字节匹配，具体登记见 [机器记录](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_6_adapter_20261013_12/review/node_review_attempt02.json)。v1审查发现保留在attempt01；本次源审查范围无剩余P1/P2。编译、测试和真实运行由root独立完成，本条不提供运行通过或阶段资格。

四项v1问题均已修：registration在bridge处理后取真实完成时间并让Admission/kernel使用同一点，任何超期或stop清双槽；资源超界Applied计入同一收到人口且永久保持lifecycle/projection不完整，不扩容CDR；submit/activation在新增bridge后取新时间并复核原始时间/source/worker/stop/owner条件；退出owner的tail要求认证关闭请求之后的实际双零、双路成功、调用时序与原GID/2s范围，仍通过旧full whole-pair assessment。

锁序与旧完整Job/Candidate、state/clock/RTF/source-age/reference/lease/resource、版本/输入变化、history、rho/command限制均保留。shadow inspect只消耗slot，不创建Active，不虚构本地actuator调用。所有失效路径清slot，关闭文件IO在业务锁外，Job DDS publish也锁外。component close在tick/prep join后，不等价于owner session/cleanup/endpoint已退出。

本reviewer另新增source-including `test_c36_completion` 三例，调用实际candidate()：无延迟完成成功、真实睡至deadline+1ms后拒绝并清双槽、最终stop后拒绝并清双槽；前置是显式有限typed fixture，adapter-null，未因此声称真实solver/owner/plant验证。与root新增kernel最终ready完成测试及owner agent资源/tail十例互补。reviewer未编译或执行这些测试，结果由独立root输出登记。

支持域仍限于新shadow接入和Applied owner认证；worker Candidate/Capability实时GID、post-pin exec连续性、连续唯一DDS出口仍未因本项取得。完整成功whole-pair反馈才导入组件；部分发布和未调用维持旧拒绝政策。4s受控recipe不能替代20s动态/mixed/压力/恢复/failed-close，也不授予B4/M0b/B5/M4、execute或研究结论。
