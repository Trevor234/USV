# AtomicCapturedCandidate 首轮 padding 失败与独立 typed fixture 修订

日期：2026-10-14。本条范围是组件测试判据修订；没有修改已锁 N13 v2 runtime、原测试、CMake、serializer、旧 expected 或原始失败，也没有由本 reviewer 编译/运行 ROS。

## 实际失败与字节证据

原始 [run.log](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_6_adapter_20261013_12/component/native_attempt01/test_atomic_observation/run.log) 与 [gtest.xml](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_6_adapter_20261013_12/component/native_attempt01/test_atomic_observation/gtest.xml) 保留。首轮共12例，11例通过，唯一失败是 `AtomicCapturedCandidate.IdentityComesFromFullCapturedImmutablePayload`；XML该测试记录2条failure断言，不能记成2个测试失败。

失败断言对同一 immutable Candidate 多次调用实际 `captured_candidate_json`，要求含raw CDR和SHA的整个JSON始终相等。原始日志4条相关record可归为2个不同CDR SHA，两者均2860字节，每条SHA均与该条完整raw字节重新计算一致。完整抽取、原始文件SHA和逐字节差异见 [字节证据](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_6_adapter_20261013_12/review/atomic_padding_failure_bytes_v1.json)。

| 记录 | SHA256 | 字节数 | 自身SHA核验 |
|---|---|---:|---|
| 实际再捕获 | `5a1859e4e7f6c04351405c4edbd50105898e5873944b5875687f48d574444dd4` | 2860 | 通过 |
| 首次记录 | `b2a25e077a930d5c894e066e633ff57ad6de24b2f1dfd1932f39ace988126f8f` | 2860 | 通过 |

仅byte offset 9、10不同（从0计）：再捕获为`07 88`，首次为`00 8a`。本fixture的首个Job schema字符串为空；CDR四字节encapsulation之后，offset4–7是长度1、offset8是字符串终止NUL，下一string长度从offset12开始。9–11处为对齐padding，观察差异位于其中。原始记录的已展示typed metadata完全一致。这说明跨独立序列化的raw frame/SHA相等，不是完整typed载荷身份的可靠判据。reviewer对日志做了raw SHA/长度核验，没有在本条执行原失败frames的ROS反序列化；新fixture交由root编译后逐条实际deserialize。

## 新增fixture与完整性检查

仅新增 [test_atomic_observation_typed_v1.cpp](/home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored_D1_C3_6_adapter_20261013_v13/component_fix/test_atomic_observation_typed_v1.cpp)，SHA `2dc6079420fc2e0979d841aaf09efe89e32ddbd6db035ddf3b5d55dc5d21a773`，21753字节。它复制原fixture，只改上述identity case；其余11例前后源片段逐字节相同，总数仍12例。它从原始已锁Node源码调用真正的snapshot/captured方法；新fixture不改原v2 bundle内的任何文件。

修订identity case对**每一次**首次/改变/重复原始capture：

1. 验证hex、非空/偶长度、record cdr_bytes、≤1MiB、hex回读与该record完整raw SHA。
2. 从该条真实bytes构造SerializedMessage，实际使用 `rclcpp::Serialization<Candidate>::deserialize_message`。
3. 比较全部Job字段（p1::job_json含schema、各身份、所有代次/时钟/时间/来源/历史/数组）和SolveCandidate消息的全部14字段：job、worker、三时刻、三个布尔、reason、backend、backend_ms、first_control、X与U。所有float64转为IEEE754 hex，随后比较canonical JSON文字；因此`+0.0`与`-0.0`保持不同，也没有JSON numeric equality抹掉signed zero。
4. 从decoded完整载荷明确检查firstcontrol/reference/X/U/frozenstate五个被改变字段，与预期changed payload全字段完全相等、与原始字段不同。每次也重新capture immutable原对象，验证其自身bytes/SHA并deserialize，完整typed载荷仍与原对象一致。

新判据保留每条raw证据的完整性，并把typed身份建立在完整实际decoded载荷上；没有用较小字段子集、指针地址、汇总flag，或padding随机变化推断载荷改变。原有全字段roundtrip和所有float数组逐位比较的独立case也保留。

## 状态与后续

重新核验已锁v2 bundle的34文件，SHA/字节全部不变。新fixture编译/link由root沿用原compile_commands与link.txt另建独立binary，运行结果要单独登记；本条的源码交付不等于新fixture已通过。首轮失败证据、原test源码和原v2 runtime仍保留。不得表述为runtime业务bug已经修复，也不得据此授予B4/M0b/B5/M4、execute或研究结论。
