# 方案A下一步：RawBackend共享初始化的详细修改与验收计划

版本：v1，2026-10-27。承接第128批的下一项工作。

**本文件是待执行计划。编制本计划期间只读核查了源码、夹具和已交付证据，没有修改执行代码，没有构建或启动ROS/owned。** 执行批号在真正开始P00时取当时可用的下一号，不预占批号，也不把计划文档称为实施完成。

## 1. 目标与完成后的实际作用

下一步只做一件事：让实际owned路径中的`RawBackend`复用第127批的共同packing/checked setter，并证明原有cold/native组件政策保持。

第128批已在派生候选和组件验证中修正普通工厂接纳非法模型的问题，尚未落位生产源码；实际owned路径也没有经过该工厂：

```text
普通生产求解器路径：make_dynamic_mpc → AcadosBackend／CasadiBackend
实际owned路径：Worker → owned_cold::Backend → startup_replay::RawBackend → acados C
```

因此，第128批工厂修正不能替代RawBackend接线。下一步完成后，应能证明：

1. 两条路径使用同一份30项参数布局，消除Raw中另一张手写槽位表。
2. Raw构造时真正消费setter报告结果，非有限载荷、报告错误和C++异常不会被当成初始化成功。
3. 已完整建立的native graph在后续构造异常时按已知阶段释放，不依赖未完成对象的析构。
4. 原有cold四次调用、普通单次调用、warm平移、约束撤销、终端失败及W2已接入守卫均无回归。

完成结论只能是“共享初始化及既有组件政策验证完成”。Worker线程所有者协议、模型热更新、完整reference绑定、生产落位和阶段验收另行处理。

## 2. 已核实的现状，执行时不得误读

### 2.1 setter只在构造时应用

实际源码位置：

- [RawBackend构造与手写packing](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/implementation/author/worker/raw_backend_v1.hpp:24)：第31行手写30项数组，第32行忽略setter返回值。
- [owned_cold生命周期与调用政策](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/implementation/author/worker/owned_cold_backend.hpp:50)：`reset_warmstart()`只置`reset_pending_`；不是重建capsule。
- [Raw step](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/implementation/author/worker/raw_backend_v1.hpp:69)：reset清warm缓存并调用`acados_reset`，不重新设置`p_global`。
- [Worker构造](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/implementation/author/worker/solver_worker_m4.cpp:56)：目前在节点构造中创建Backend，计算线程随后使用它。

**本批不得新增逐Job setter、capsule重建、模型切换或generation提交。** reset、模型初始化和cold once-only是三个不同概念。

### 2.2 构造异常的资源清理需要分阶段

Raw当前构造在分配、create、尺寸检查、setter及warm数组初始化之间连续执行。若构造抛异常，`~RawBackend()`不会自动运行，不能靠第34行析构函数兜底。

但也不能对任何非空capsule统一调用完整free：当前生成C的`create_capsule`使用未清零的malloc；完整free会直接访问`nlp_solver_plan->N`并销毁多个成员。尚未完整create的capsule不满足这些前提。

核查源：[生成C的分配入口](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_model_setter_review_20261026_127/implementation/baseline/acados_generated/acados_solver_usv_dyn_nmpc.c:97)、[create阶段](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_model_setter_review_20261026_127/implementation/baseline/acados_generated/acados_solver_usv_dyn_nmpc.c:909)、[完整free](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_model_setter_review_20261026_127/implementation/baseline/acados_generated/acados_solver_usv_dyn_nmpc.c:1074)。

另外，生成C的`create_precompute`在失败时会`exit(1)`，不是可被C++ catch接住的异常。本批不改生成C，也不宣称覆盖任意部分创建失败、C内部退出或内部挂起。

### 2.3 普通路径和W2路径的最末守卫不能混称

[attach_boundary](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/implementation/author/worker/owned_cold_backend.hpp:19)仅在boundary非空时安装Raw最终guard；[Worker](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/implementation/author/worker/solver_worker_m4.cpp:289)也只在W2 boundary存在时接线。

本批复跑的是：普通路径已有的前置deadline检查，以及W2已接入的准备后stop/deadline最终guard。不得把它写成所有普通run已经具有相同最末stop guard。若要补普通路径的最终guard，必须另列行为变更，不能夹在packing抽取中实施。

## 3. 固定修改顺序

```text
P00 固定输入、目录、白名单和预期结果
 → P01 真实旧基线与构建接线核验
 → P02 只替换packing，先证原行为一致
 → P03 单独修已知构造阶段的异常清理
 → P04 再接checked setter与明确拒绝
 → P05 初始化与失败阶段真实正反例
 → P06 cold/native/W2组件政策回归
 → P07 定向变异验证测试确实约束接线
 → P08 分项补丁与只读复核
 → P09 资产保护、文档和MPC交付
```

每一步必须有`step_result.json`。状态只允许`PASS`、`FAIL_STOP`、`BLOCKED_SPEC`、事前登记的`NOT_COVERED`。必要项失败时不推进；不能在运行后把必要项改成可选或降低阈值。

### P00：固定输入和执行边界

**做什么：**

1. 建立一个新执行包，原126/127/128批只读。固定基线Raw/owned/Worker及测试源码、共同头、生成C、复用归档、运行库、夹具、计划和合同的绝对路径与完整SHA。
2. 记录当前git状态及已有dirty文件的内容身份。正确处理中文路径；其他任务的变化保留并标注，不恢复。
3. 固定本机架构、编译器、优化级别、native库路径、线程选项与测试超时。组件超时不等于合同deadline。
4. 登记每项case的名字、入口、预期结果、native调用事实、释放次数和必要断言；登记变异清单。
5. 确认M0及已有合法M1的确切来源，不临时设计新的水动力参数。找不到合法M1来源则`BLOCKED_SPEC`。

**必须先核验的夹具：**

| 内容 | 当前已核实SHA |
|---|---|
| RawBackend原件 | `2e1f2f0d1f3a393ec1e944462b9490a258eb8cdfa6103144816b8a8fbf13aa8f` |
| owned_cold原件 | `4746895a0367caba189dffbd6391adfb7603ba5f4c033ec22dc21c441f9a8128` |
| Worker原件 | `d4e2cd2cc2db7c68fa928dcc2012130e890e3370f88ffba796eb2cfc894468a8` |
| 102-Job旧输入 | `66fcf57e255c4843d551f74464d7cda3fb0f1d5832c589484a55b96d8f5ea475` |
| sealed cold候选结果 | `64a94b463f5eaacca2703646e44065e4a4a91cd347e74eb4ddc8c4c4d30af514` |

两个数据文件的完整路径在[夹具索引](/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_offline_hardening_20261026_126/implementation/author/worker/cold_backend_test_inputs_v1.json)中。索引内写了SHA不等于测试已核SHA：runner必须启动前和结束后实际重算。

**产物：**输入manifest、工作区快照、变更白名单、case registry、变异registry、执行环境记录。

**进入P01条件：**输入可读、SHA符合登记、白名单无歧义；旧失败证据索引保留。

### P01：建立真实旧基线，先证明编译的是谁

**做什么：**

1. 使用独立离线CMake，编译未修改Raw与真实acados调用链。不得直接复用旧安装solver归档冒充当前源码。
2. 生成C归档可以复用第127批已固定产物，但要记录原路径、SHA、生成源码身份和O1配方，不能写成本批重新编译了全部codegen。手写源码统一使用固定配方。
3. native三库用绝对路径选择，子进程搜索环境明确登记。Raw验证不需要CasADi，不把CasADi回退引入owned路径。
4. 显式注册cold测试目标及`OWNED_COLD_TEST_INPUT_FILE`。现有author根CMake未注册该9项cold测试，不能只构建根目标后声称cold已覆盖。
5. **将测试源码复制到中立`tests/`目录后编译。** 原worker测试使用带引号的本地include；若直接编译冻结worker目录里的测试，即使加候选`-I`路径，也可能优先包含旧owned/raw，导致“候选坏了但测试仍绿”。
6. 从实际`.o.d`、编译命令、链接行和运行时映射确认：Raw来自本变体；类型/公共头来源唯一；候选共同头来自新包固定位置；没有暗中引入旧安装solver。

**先跑哪些：**9项真实cold、13项W2真实接线、15项Boundary状态测试；52项政策模拟单列。名字和数量以P00固定源码与实际测试发现结果双重核对，不能沿用历史“W2只有11项”。

**停止条件：**旧基线本身不通过、实际include不对、夹具不符或运行库身份不对。保留失败，不先改算法或放宽公差使它通过。

### P02：仅抽取packing

**改哪里：**新派生`packing_only/worker/raw_backend_v1.hpp`中原第31行的手写数组，改用第127批`p_global::pack(p_)`；调用维度使用共同`count`。

**此步刻意保持：**setter结果仍沿用旧处理、构造清理仍是旧处理、step/cold/guard/observer完全不动。它是为分离影响而保留的中间候选，不能单独标为最终安全可用。

**验证：**

- 用互不相同的30槽测试值做位模式对拍；NaN/Inf位模式只能作packing观察，不能送入真实precompute。
- 用同一份102 Job输入分别驱动原Raw与packing候选；比较control、X、U、warm、首控制边界、调用次数及政策字段；计时字段排除。
- 比较前先验shape和全部元素finite。原`maximum_error()`使用`std::max`，单靠它不能可靠拦NaN，不能把“max error=0”当成有限性证明。

**公差固定：**旧102 Job回放control≤`1e-10`、X/U≤`1e-9`；sealed cold候选X/U≤`1e-8`。位模式对拍不使用浮点容差。对拍差值如实记录，不四舍五入成0。

**产物：**`01_raw_packing_only.patch`、packing及数值对照记录。

**进入P03条件：**原行为对照全通过，真实依赖指向候选Raw；只改packing的diff成立。

### P03：单独补构造阶段的清理责任

**改哪里：**在packing候选基础上，构造体中引入局部`graph_ready`状态及一套异常清理块；不新增公共接口，不把它做成通用资源框架。

**实现顺序固定：**

1. 分配capsule，空指针立即拒绝。
2. `graph_ready=false`。分配成功后立即进入异常保护范围，create调用自身也必须包含在内；只有create正常返回0之后才置true。
3. 后续句柄获取、baked N/dt检查、参数初始化、warm矩阵初始化均在同一受保护范围内。
4. 捕获可传播的C++异常：若`graph_ready`为true，先完整free；随后释放capsule；置空成员指针并重抛原异常。
5. 正常构造完成后仍由现有析构释放一次。不要在成功路径中提前free，也不要重复释放。

**清理判据：**

| 已知阶段 | 允许的清理 | 本批如何取得证据 |
|---|---|---|
| 分配返回null | 不调用任何free | 命名分配边界注入 |
| 已分配、测试适配器在进入create之前拒绝 | 只释放capsule | 明确标记pre-create拒绝，不伪装成native内部部分创建失败 |
| create正常返回0后，N/dt或setter等C++路径拒绝 | 完整graph free，再capsule free，各一次 | 实际graph建立＋命名后续失败 |
| 正常对象退出 | 完整graph free，再capsule free，各一次 | 正常构造、求解、析构 |
| native内部部分创建失败或`exit(1)` | 本批不作通用清理承诺 | `NOT_COVERED`，若必须解决则另开设计项 |

`graph_ready=false`只表示尚未确认完整建立，不证明内部从未分配graph。不允许把“create返回非零”一律解释成未分配graph，也不允许一律full-free。当前生成C在固定create路径没有提供任意部分初始化可恢复协议。除C09明确位于进入create之前的受控拒绝外，实际create中途异常/非零均记`FAIL_STOP`：记录已知状态和清理动作，但不宣称graph释放账闭合，不靠猜测推进。

**产物：**`02_raw_known_constructor_cleanup.patch`，与packing补丁分开。

**进入P04条件：**正常路径对拍保持；已知阶段的释放账一致；未知native部分失败没有被冒称覆盖。

### P04：接入checked setter

**改哪里：**在已通过P03的候选中，将原setter调用替换为共同`p_global::apply(c_, packed)`，检查`ApplyResult::ok()`。

**具体要求：**

- 共同`p_global_pack.hpp`、`p_global_apply.hpp`原字节复制自第127批，统一物理路径，不能在本批另写一套槽位或修改共同头来迁就Raw。
- 保留helper的可写私有副本、30维静态约束、有限性检查及真实报告状态。
- 报告失败时抛出有界、明确的构造错误，包含apply类别和native报告状态；由P03清理块释放并重抛。
- setter异常同样清理并传播，不吞异常、不改成success、零控制、shift结果或CasADi回退。
- 不改step，不把初始化重做移入reset或每个Job。

**重要计数口径：**本方案在create成功后的runtime setter处检查。即使调用者模型含NaN，生成器create中的固定合法bootstrap仍可能执行；要求是“坏载荷不进入runtime setter、solve为0”，不能错写成“native初始化相关函数总调用为0”。测试应按create阶段和create返回后的runtime_apply阶段区分，不用`mass==30`作为通用身份判断。

若bootstrap在链接包装器中不可见，应如实记录可见性，用固定生成C源码说明其行为，不能补造一条事件。

**产物：**`03_raw_checked_initialization.patch`、初始/报告错误行为变更表。

**进入P05条件：**接线真实到Raw构造调用处，拒绝后对象不可使用，且正常路径对拍继续保持。

### P05：初始化与失败生命周期矩阵

以下是必须登记并取得实际结果的最小矩阵。每一项都记录：输入身份、构造是否完成、runtime setter边界及报告、真实solve数、graph/capsule释放、异常类别和原因。

| ID | 刺激 | 必须结果 |
|---|---|---|
| C01 | 原登记M0 | 构造和真实求解成功，30项载荷正确，正常释放一次 |
| C02 | 既有合法M1 | 构造及规定单次组件求解成功；不据此扩充owned cold登记域 |
| C03 | hydro NaN | 坏载荷runtime setter为0、solve为0、构造拒绝、完整graph/capsule各释放一次 |
| C04 | hydro Inf | 同C03，覆盖非首槽 |
| C05 | 晚槽Qf非有限 | 同C03，防止只检查hydro或首项 |
| C06 | runtime setter边界报告17 | 构造拒绝、无solve、错误明确、完整资源释放一次 |
| C07 | runtime setter边界抛C++异常 | 原因向owner传播、无solve、完整资源释放一次 |
| C08 | capsule分配返回null | 拒绝，create/setter/solve均不执行，free为0 |
| C09 | 进入create之前的命名拒绝 | 仅释放已分配capsule；不冒称部分graph失败已覆盖 |
| C10 | baked N与配置不一致 | 真实create后拒绝、runtime apply不执行、完整释放一次 |
| C11 | baked dt与配置不一致 | 同C10 |

旧基线对非法载荷或报告错误的观察必须采用适配器阻止危险数据进入真实native，并明确标为旧行为观察。不能为了对比直接让旧Raw用NaN进行真实precompute/solve。

warm数组分配异常属于P03同一catch保护范围；本批只对实际注入过的异常点声称动态覆盖，不宣称已穷举所有内存分配失败点。

### P06：真实cold/native/W2政策回归

**现有测试的正确分工：**

| 资产 | 当前数量 | 作用 | 不能替代什么 |
|---|---:|---|---|
| `test_reference_cold_backend.cpp` | 9项 | 真实Raw/owned调用；102 Job、cold四次、once-only、warm/边界撤销、hook失败终端 | 不等于完整Worker进程/owned运行 |
| `test_w2_backend_wiring.cpp` | 13项 | 真实Backend/Raw接线；目标/非目标、准备期stop/expiry、C入口事实 | ControlledReader不是新跨进程pipe证据 |
| `test_w2_native_boundary.cpp` | 15项 | Boundary纯状态、双身份匹配、release/stop/事实序列化 | 不调用C，不能代替接线测试 |
| `test_m4_native_policy.cpp` | 52项 | 纯政策/API模拟、合同及grant规则不变 | 不是52项真实native求解 |

测试源均来自第126批`implementation/author/worker/`，政策模拟在`author/tests/`。P00须展开绝对路径固定，不直接运行旧runner的清理或重写步骤。

**必须保持的cold行为：**

- 注册域内当前首Job：一次自由求解，再固定首控制0.5的三次RTI，共四次调用；不能增减次数。
- 只有最后一次作规定warm shift；撤销固定边界不再改变warm。
- 非cold或后续Job仍为既有单次路径；reset和代际字段变化不重新武装cold机会。
- 非法身份、迟到、重复等仍按现有验证入口处理，不引入新的恢复或复活通道。
- hook异常仍走既有终端语义，随后Job不得继续使用终端Backend。

**必须新增的最小native故障事实：**

| ID | 刺激 | 必须结果 |
|---|---|---|
| N01 | cold ordinal1真正进入C后，由适配器返回非零报告 | actual C调用事实保留；本次未成功完成；Backend终端且不返回成功fallback |
| N02 | cold ordinal4同类报告错误 | 前三次成功和第四次已进入C分开记账；终端，禁止后续Job继续 |
| N03 | 真实solve后向返回输出注入NaN | Raw有限性门拒绝；C调用事实仍成立；不得污染为成功结果 |

原cold测试的逐ordinal失败通过`BeforeCall`抛异常，不能拿来替代N01/N02的实际C入口故障证据。注入的非零报告也不能宣称为真实C内部自然发生的故障。

N01/N02的适配器必须先调用真实`__real_usv_dyn_nmpc_acados_solve`，记录其进入、返回和真实状态，再改写对上层报告的状态。真实调用计数独立于政策observer计数，两者交叉核对。若包装器不调用真实函数而直接返回17，只能称为调用边界拒绝，不能满足这两项“真实C函数体已经执行”的义务。

W2回归必须继续驱动真实目标Job和ordinal，覆盖及时释放、跨deadline、准备期间stop/expiry、非目标约束及拒绝记录刷新。进入C前被拦应记actual=false；已经进入C后失败不得被改回false。

本批不启动Worker。`terminal_exception`、pending discard、active清零及进程关闭仍只有已有证据和本次只读调用图说明，不新增“Worker事件流已验证”的结论。

### P07：定向变异，验证测试没有绕开新接线

至少固定以下6项。每个变异都在新包内自己的私有副本中实施，不改主候选和冻结原件。

| ID | 变异 | 必须由哪类断言拒绝 |
|---|---|---|
| M01 | Raw传给实际setter的某个槽位错位 | runtime载荷位模式/正常数值对照 |
| M02 | Raw忽略ApplyResult | C06报告17后仍构造成功的拒绝断言 |
| M03 | 删除构造失败清理中的graph free | C06/C07的分阶段释放对账 |
| M04 | 删除或提前Raw最末guard | W2准备期stop/expiry目标与非目标用例的native_calls=0断言 |
| M05 | 删除C入口observer或在异常时抹掉已提交事实 | N01/N02的实际C调用计数与政策事实交叉对账 |
| M06 | 删除正常cold结束时撤销固定首控制边界 | cold结束后的真实C API首边界回读 |

变异成功的固定链：匹配恰好一个修改点→变异源码确实改变→编译成功→链接成功→进程正常完成并产出完整证据→被**登记的具体断言**拒绝。编译错误、超时、缺字段、KeyError和任意崩溃都只能算验证失败。

不得为了凑“捕获数”选择无行为差异的变异。例如只删`consumed_`检查，可能仍被first-Job资格约束挡住；这种等价/冗余变异不能伪称测试已捕获。需在运行前按可观察行为登记上述实际变异。

如果删候选接线后测试仍全部通过，P07失败，先修测试入口或断言，禁止声称组件完成。

### P08：分项补丁及只读复核

必须交付三张按顺序应用的功能补丁：

1. `01_raw_packing_only.patch`：仅槽位逻辑共享，保留原行为。
2. `02_raw_known_constructor_cleanup.patch`：已知阶段的异常清理。
3. `03_raw_checked_initialization.patch`：消费共同helper结果，新增明确拒绝。

新增测试和CMake改动另列支持文件清单，不混入生产落位补丁。第127批共同头属于固定依赖，其来源和SHA单列。

在私有目录依序dry-run、实际应用并比较最终字节与被测候选；禁止在生产根目录尝试应用补丁。复核全部step、失败处置、实际include、编译/链接/加载身份和正常/拒绝行为表。

所有正例、公差、schema和合同预算保持原值。发现需要改变`owned_cold_backend.hpp`、Worker、nominal/reference绑定或普通最末守卫政策时，写独立问题单并`BLOCKED_SPEC`，不能以“配套修复”为由扩大白名单。

### P09：保护复查、交付和停止

1. 重算输入、夹具、共享库和冻结126/127/128批保护人口；记录同时发生的外部工作区变化。
2. 每步汇总必须同时检查预期case人口、实际名字、`failures=[]`、unexpected errors为空及必要产物；不能只看rc0或`status`字符串。
3. 所有尝试使用新`attemptNN`目录、create-only写入。首次失败、旧源码/变异diff、stderr和退出信息保留，不清空旧case目录换取通过。
4. 完成CURRENT、详细报告、分项补丁清单、下一步和资格表。
5. MPC镜像排除build、ELF、归档及缓存；保留源码、身份、失败证据与结果。若依赖复用归档，列明从USV固定来源取回和核SHA要求。
6. 两轮逐文件人口及SHA回读，交付回执同步后再回读；源与镜像多文件、少文件、不同内容均拒绝。

**本包到这里停止。** 不自动启动新owned、不生成可直接启动owned的有效registry/registration、不生产落位，也不把历史126批过程失败撤销。

## 4. 变更白名单和目录约束

执行包建议固定以下结构；所有名字都是计划中的新路径：

```text
<新执行包>/
  CURRENT.md
  implementation/
    baseline/author/              # 固定原字节，只读基线
    packing_only/author/          # 仅Raw packing差异
    cleanup_only/author/          # 在packing上加已知阶段清理
    checked_init/author/          # 再接checked setter
    shared/include/usv_mpc_cpp/   # 127共同头的唯一固定副本
    tests/                       # 中立目录的测试副本与新增测试
    cmake/                       # 独立离线构建入口
  evidence/inputs/
  evidence/P00/...P09/attemptNN/
  patches/
  postrun/
  documents/
```

| 路径/对象 | 本包权限 |
|---|---|
| 新变体中的`worker/raw_backend_v1.hpp` | 仅按P02/P03/P04分项修改；step/guard/observer功能主体保持 |
| 新包共同pack/apply头 | 从127复制并固定字节；不修改 |
| 新包测试、离线CMake、runner、报告 | 可按本计划新增；测试注入不得成为ROS参数或业务接口 |
| 主候选`owned_cold_backend.hpp`、Worker、W2 Boundary/Gate | 只读；变异仅可在独立测试副本中改 |
| 126/127/128批、旧run/registry/registration/失败证据 | 全部只读 |
| 生产`usv_mpc_ws/`、ArduRover及已有dirty文件 | 只读，不reset/clean/提交/推送 |
| 创新登记簿、其他研究弧 | 本包不修改 |

预算和尺寸按各测试自己固定的合同，不改200ms周期、150ms业务deadline、hold/watchdog/grace等值；不得把v3预算套用到其他诊断合同。固定生成尺寸NX8/NU2/N20/NP6/NPG30，不codegen。

## 5. 收尾时必须怎样报告

至少分四栏，不用一个`complete`把它们混起来：

| 层次 | 允许写的结论 |
|---|---|
| observed_facts | 实际构造、setter报告、C入口、释放调用、数据与政策轨迹 |
| component_cases_accepted | 本计划登记case是否满足预期，拒绝是否来自正确断言 |
| production_integration_ready | 本批不作最终生产资格结论；仍需所有者/身份/完整构建等后续门 |
| stage_qualified | M4/F6/P1/plant/硬实时均保持false |

即使P00—P09全通过，也不把“初始化共同头复用”写成“模型事务已进入owned”或“F6运行时事务完成”。生产B始终保持MANUAL＋RC覆写。

## 6. 本包之后的总体顺序

| 顺序 | 后续主题 | 必须先解决的问题 |
|---|---|---|
| 本包 | Raw初始化复用及组件政策保持 | 本计划P00—P09 |
| 下一设计包 | Worker唯一所有者生命周期 | 创建、使用、销毁线程一致；不可变capability；就绪与DDS发现依赖不循环 |
| 再下一设计包 | 模型/reference完整身份与target-tick激活 | 登记模型表、旧Job处理、完整binding、新窗口、提交/隔离终局 |
| 分项集成评审 | packing、checked初始化、scoped/B2/model等各项独立评审 | 不捆绑；明确实际落位点、负控、构建身份和冻结策略 |
| 必要运行证据 | 在单独确定范围后做有限owned补证 | registry/registration、实际ELF和运行库身份、case断言与退出对账 |
| 阶段验收 | 重新核对M4/F6/P1各自剩余义务 | 组件结果、场景证据与阶段资格分开；GP/plant/RT缺项不由软件回归代替 |

**收到“执行本计划”时的默认范围：只执行本计划P00—P09。** 允许为已登记步骤修复测试工具与派生候选，保持失败证据；需要改变业务政策、生产树或运行层范围时，先提交明确变更项，不能自由扩展。
