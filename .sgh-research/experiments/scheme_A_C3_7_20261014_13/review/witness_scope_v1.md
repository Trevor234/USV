# C3.7 Witness v2 的接口与证据边界

日期：2026-10-14（Asia/Shanghai）。本文件描述 N14 新生产端及新解码器。N13/v1 生产端、解码器和上一批 normal Witness 失败均保留，不修改其历史含义。

## 生产端

observer/src/shadow/p1_witness.hpp 保留全部固定 POD、容量、流的生产 API，以及 Witness(bool, header) 构造 API。原子 reservation/append 路径保持 noexcept，不增加日志、分配、I/O、控制锁或授权依据。新增的固定上限扫描只用于观测汇总；它不证明硬实时 WCET、wait-free，或每个业务线程已正确 join。

生产 JSON 的精确 schema 为 p1-fixed-witness-v2，固定 profile=closed_shadow_observation。生产 profile 描述观测模式，评价 profile 由调用者独立显式选择；它不由 accepted 数量或运行结果自动切换。

| 字段 | 含义 |
|---|---|
| observation_complete | 已启用并关闭，固定流 header/count/slot/first failure/drop 一致；有实际 Tick；有且仅有一条最后 Close phase，观察时间不早于任何生产记录；Tick/Submit/Activation 的时间、job 人口、去重、causal 关系一致；存在的 BusinessReady 必须与首个 accepted 精确对应。全拒绝可以成立。 |
| business_ready_observed | 真实 record_activation(accepted=true) 生产记录存在；恰好一条 record_phase(BusinessReady)，其 job_id/tick/ns 精确等于首个 accepted 的 job_id/tick/commit_ns，observation code 为 FinalActivation。它不是启动 readiness。 |
| normal_contract_qualified | 上述完整观测和 BusinessReady 均成立，而且全部 normal Witness 必要记录条件通过；failed Tick/Submit/Activation、failed phase、QueueOverflow/SourceFailure 会使其为 false。它只评价本文件中的 Witness 记录，不能解释为整体控制 contract 或 B4/M0b/B5/M4 阶段资格。 |
| normal_contract_scope | 固定为 “Witness records and first real accepted activation/BusinessReady consistency only; no control or phase qualification”，避免将前一字段推广为整体控制结论。 |

JSON 删除旧 audit_complete。C++ WitnessSummary.audit_complete 仅保留原内部 storage 完整性语义，供已有组件代码兼容；不能当作新版闭合观测人口验证结果。enabled/closed/overflow/incomplete/header/capacities/counters/streams/first_failure/clock_name 继续输出，新增字段按严格有限 key 集验证。

因此，缺失 Close、重复 job、时间倒序、伪造或重复 BusinessReady 时，即使所有 append 都成功，新的 observation_complete 也为 false。没有 BR 但完整 accepted 记录可以保持观察完整，同时 business_ready_observed=false、normal false；该缺失不能被启动 readiness 补齐。完整记录的失败状态允许如实归档，normal 条件仍拒绝。

## 新独立解码器

新增 runtime/check_p1_witness_v2.py；旧 runtime/check_p1_witness.py 不修改。调用：

~~~text
python3 -B runtime/check_p1_witness_v2.py WITNESS.json \
  --expected-header INDEPENDENT_HEADER.json \
  --profile closed_shadow_observation \
  --output CREATE_ONLY_REPORT.json
~~~

--profile 必填，可选 closed_shadow_observation 或 normal_business。同一生产文件可以分别评价两种 profile。前者允许记录完整的全拒绝运行通过组件验证；后者必须有首个 accepted 与真实 BR，且 normal 条件全部通过。不会假定固定 accepted 数，也不会把原生有限 fixture 的 accepted 代入真实 DDS 运行。

解码器独立重算上述条件，不信任生产 bool。严格拒绝 root/row/counter 多余或缺失 key、bool 冒充整型、浮点或负数 ID、超容量/越界数值、计数失衡、缺 reservation/重复人口、无 submit 的 activation、时间顺序错误、header pin 不一致、伪 BR、未闭合等。Parser 有有限字节、JSON 深度和节点预算，拒绝重复 JSON key 和非有限数。输入身份 header 必须由外部可信来源给出，不能直接从待验 Witness 复制。

输出 normal_business/normal_contract_qualified 仍只是有限 Witness 组件条件。source_join_verified/normal_contract_complete/execute_qualified/phase_qualified/research_conclusion 固定为 false；Source/DDS/SQLite/owner 认证和 phase 必须另行验证。Witness v2 本身不证明连续 DDS 唯一性、进程 exec 连续性、MasterClock、plant、物理作用或关闭者已退出。

## 必要验证与使用方法

新增 tests/test_witness_v2_c37.cpp，20 个原生 GTest 方法调用真实 Witness API；不调用 solver、DDS、plant，也不模拟一个真实运行 accepted 结果。覆盖 accepted/BR、全拒绝、后来拒绝、append rejection、容量 overflow、disabled、重复人口、BR 不匹配/重复/来源错误/缺失、缺 Close、failed Tick、SourceFailure、header invalidation、after-close append、时间倒序，以及 create-only 终端写入。

共享 fixture 在 tests/witness_v2_c37_fixture.hpp。tests/witness_v2_c37_producer.cpp 是标准 C++ 文件生产器：

~~~text
witness_v2_c37_producer accepted CREATE_ONLY_NATIVE_WITNESS.json
~~~

runtime/run_witness_v2_c37_cases.py 调用该文件生产器，保存 18 个真实 native file 输出并分别评价两种 profile（36 次评价），另测 disabled 不创建文件；共 19 个有限 fixture。它把 expected failure 与真实 passed=false 结果一同保存，而不会覆盖或把失败改写成正常证明。expected_fixture_header.json 来自独立固定的测试声明常量；这些常量只用于有限 fixture 身份比较，不冒称生产 binary/boot/worker 认证。

新增 runtime/test_p1_witness_v2_c37.py 的 16 个方法验证 typed/keys/counter/ID/identity/profile/BR/Close/failed-record/parser 负例；属于解码器测试，不能代替 native replay 或真实 Source join。首次运行记录保存在 component/witness_decoder_attempt01/，exit 0。原生构建、native replay 和实际 owned Source join 由本批统一流程执行，在结果完成前维持 not_run。

## 当前资格和下一步

本组件不授任何阶段资格或研究结论。真实运行的闭合观测人口验证仍须与实际 Source、GID/完整 CDR、roles/进程、driver-close 请求/确认、关闭后业务禁入及 Recorder 数据互相核对。运行全拒绝时应明确写 observation_complete=true 与 normal_business=false，并保留旧 v1 normal failure；若下一批需要 normal 资格，应使用预注册的真实业务 accepted 研究条件，不得据此改写当前全拒绝人口。
