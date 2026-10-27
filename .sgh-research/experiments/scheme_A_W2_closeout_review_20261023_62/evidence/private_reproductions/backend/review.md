# W2 D3/D4 只读复核（供主审收录）

当前作者树的 D3 已修复，D4 的目标 Job/ordinal 准备窗口也已真正防护。额外私有检查 7 项为 **4 通过、3 失败**，不能归纳为整批失败或整批通过。

## 仍需修正

1. **P2：最终 guard 仅检查注册边界，遗漏其它内部调用。** `owned_cold_backend.hpp:26–29` 在 Job/ordinal 不匹配时直接 `return true`，而61号原计划 D4 要求覆盖每次内部调用及所有可能等待的 hook。真实 `update_params` 准备窗口改变 stop 或推进 Job 截止，使用不匹配 Job2 时均实际调用 C solve 一次，且 solve_owned 正常返回。对应私有测试 `NonmatchingJobStopDuringPreparationStillMustPreventTheCEntry` / `NonmatchingJobExpiryDuringPreparationStillMustPreventTheCEntry`。最小修正：每次 RawBackend C solve 前都查当前 Job 原绝对截止与 stop；只把注册目标的释放许可与 Boundary 记录更新限定于 matches。普通非匹配调用在未停止且未过期时继续放行。

2. **P2：新增两个准备窗口测试并未到达准备窗口。** `test_w2_backend_wiring.cpp:201–205,220–222` 使用 entry_observer；`w2_native_boundary.hpp:187–191` 明确在 gate.wait 前调用它。因此 stop 被 Gate 自己捕获、推进时钟被 Boundary 的旧 guard 捕获。实际删掉 `raw_backend_v1.hpp:88` 的最终 guard 后，原8个Backend测试仍8/8通过。九个登记变异没有删除这个 guard 的项。最小修正：在真实约束/reference/warm 准备期间使用私有链接适配器注入状态变更，并增加 delete_real_final_guard 变异；不要扩大到 C 内部挂起实验。

3. **P2：最终 guard 拒绝后，policy 缺 Boundary 事实。** `owned_cold_backend.hpp:67–75` 只处理 enter() 拒绝，`85–98` 只在 C 已调用或成功返回时记录，`115` 的 catch 未刷新。真实准备窗口推进到 deadline+1 时，Boundary 为 released=true/expired/actual_native_invoked=false，policy 中完全没有 w2_boundary。最小修正：在目标调用的最终拒绝/异常路径刷新一次 Boundary 与调用事实；避免把其它 Job 事件挂到目标身份。

## 通过的新增检查

- 成功路径 policy 与 Boundary 的 actual_native_invoked 一致。
- 真实 C solve 执行后用私有链接适配器返回非零：Boundary 与 policy 均保留 actual_native_invoked=true，真实 C 调用计数1。这关闭 D3 原缺陷。
- 真实 update_params 调用完成后置 stop：目标调用 C 次数0。
- 真实 update_params 调用完成后推进至 Job deadline+1：目标调用 C 次数0。

## 可复现资料

`commands.json` 包含本次独立 C++ 编译与链接完整 argv；原输入来自当前61作者树的94项文件，未沿用旧作者树头文件。`source_identity_and_link_inputs.json` 比对94项输入与私有副本一致，并记录122项显式链接文件 SHA。`run_compile.py` 为本次附加检查入口；`run.stdout.txt` 保留4通过3失败及JSON事实。`final_guard_deleted` 单独存放额外变异的源副本、命令、输出、SHA，RC0/8通过代表**变异存活这一覆盖缺口**，不代表通过阶段验收。

本次只在 `/tmp/review_w2_v62_backend` 新建私有源和离线测试程序，调用了真实 native solver 作为组件检查；未启动 ROS、owned、闭环或硬件。未修改61/60及生产根源码。
