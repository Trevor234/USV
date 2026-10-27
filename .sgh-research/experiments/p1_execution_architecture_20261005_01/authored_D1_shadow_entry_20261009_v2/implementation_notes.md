# 隔离 shadow-only 入口实施范围

日期：2026-10-09。状态：本地源码、CMake和测试正文已创建；本文件不报告编译或测试执行成功，不授权D1动态采集。

生产target：`p1_regulator_shadow_observer`。新增source-linked target：`test_shadow_entry`，23个case。继承target：`test_d0_observation`，8个原case；`test_enqueue_branch`，10个原case。总计41个声明case，继承18不能记为新23的独立新增资格。两个继承test文件从D0逐字节复制，但本次 `P1_REGULATOR_SOURCE` 指向本目录新的 `src/shadow/regulator_shadow_observer.cpp`。

继承的 EnqueueTestTag 只在定义 `P1_ENQUEUE_BRANCH_TEST` 的测试translation unit中存在，保留no_output/5000ms pause以调用原enqueue/观察回归边界。这不是生产shadow管线。新 `ShadowTestTag` 仅在 `P1_SHADOW_ENTRY_TEST` 测试translation unit存在，mode=shadow、pause=0、调用实际legacy callback。生产CMake target不定义任何测试macro，不install或改默认build/install。测试需要每个target独立、fresh绝对目录 `P1_BRANCH_TEST_OUTPUT`；不能重用已有产物目录。

本轮有限业务修订：

- actual constructor接受显式NodeOptions供source-linked真实拒绝分支测试；节点名仍为p1_regulator。mode参数默认空，必须显式shadow；缺mode/no_output/execute/未知mode立即拒绝。再运行原完整diag5 loader与新EntryPolicy；所有应用publisher/sink创建都在这些门之后。该顺序不声称rclcpp Node基类隐含endpoint为零。
- 五个hook声明均为严格int64零，正/负/错误类型拒绝。worker delay/native只是本入口声明，另进程worker实际argv/source/bin零门仍由未来driver独立证明；没有修改worker或合同flag。diag5能力flag=true不代表本次有注入。
- 强制Witness启用，要求本entry source/真实self executable/指定worker executable SHA与instance，绑定fresh绝对且互异source/Witness输出路径。身份源必须存在；source fresh检查是创建前预检，原Sink仍按原append实现打开，不宣称原Sink具有新增atomic O_EXCL保证。未来owned driver还需隔离产物目录与完全路径审核。
- 必须预声明schema/run/producer/config/domain；schema=p0-contract-v1、baseline来自完整合同冻结F5标识、domain必须同时exact匹配本boot+:steady_clock与消息。producer为opaque bounded exact值，不猜SHA，不从首包自学习，也不复用历史run producer。
- 新helper在原业务mutex内先验整包身份、两路publish success、top/left/right epoch、每路完整start/end与跨路顺序、非负且不倒退sim/history、原command bounds与clock receipt基本顺序；失败不合入半包。已认证run/producer的畸形包使anchor双路unknown、清双history、invalidate。foreign run/未认证producer不能自学习；producer更换在首次已认证后走原unusable_locked统一terminal，保留候选/pending before证据，未来合法包也不得重新入历史。
- 真实sequence gap仍保留原clear/invalidate后只合入当前已观察pair的行为；不补缺号，duplicate/old不改历史。原连续history校验、pre-odom双路覆盖、nominal/state/command/rate/time公式、原reason/fallback、D0观察schema与single Decision enqueue/close/Witness布局保持。原physical publish函数保留原正文，但生产无法进入execute且constructor不再创建任何物理publisher。
- 不订阅`/p1/diag/arm_sink_pause`；生产pause policy为0。新有界`legacy_admission_rejected` source事件包括expected identity、observed每字段截断值/bytes/truncated、reason、sequence、received/admitted counts及invalidated/terminal。所有untrusted identity text最多128字节。未来strict reader须为新source事件和startup新增policy字段单列严格式；旧D0/C0 reader尚不能验证此版本。
- recording_ready保留原图arm，不在constructor等callback；未来driver须在executor spin后有界证明真实legacy历史及owner，再开始事前声明measurement window。

测试直接包含本runtime源，调用actual EntryPolicy/constructor拒绝、实际legacy_applied、原predict/连续history检查和原统一terminal。新case覆盖mode/五hook/Witness/paths/pins、missing/empty/foreign identity、日志截断、producer terminal before-evidence、真实双路与missing pre-odom、duplicate/gap/epoch/partial/future/失序、change-then-return和容量失去frozen端点。继承8case仍验证null/full6/来源快照/canonical投影；继承10case仍验证原enqueue失效/关闭分支。并未创建重复业务模型作为测试。

actual constructor负例断言具体exception.what原因（错误hook类型断言其RCL类型拒绝及hook名字），不把后续故意fixture SHA不匹配当作入口门通过。正常完整policy已由同一实际helper的NO_THROW正例覆盖；完整runtime constructor通过Witness真实identity、graph recording-ready并进入spin的成功路径仍未执行。baseline不提供可覆盖参数，扰动baseline仅在helper实际validate测试，不声称测过actualctor baseline override。

仍pending：native编译与上述测试实际结果；新source/bin完整身份；未来独立shadow driver/strict source+actual bag+Witness+owned组合；冻结F5新run真实publisher认证；actual研究域、owner/time政策；统一版本受影响pressure/recovery/close资格。任何本轮有限source-linked通过都不能自动承接旧R5压力证据或启动D1动态场景。B4/M0b/B5/M4/F6/P1/execute均保持未闭合。
