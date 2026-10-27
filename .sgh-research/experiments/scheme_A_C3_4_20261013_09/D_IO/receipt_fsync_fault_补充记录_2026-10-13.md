# C3.4-D receipt 目录 fsync 故障补充组件记录（2026-10-13）

应 root 追加任务，使用实际 v10 gate 的源链接探针验证 receipt 侧目录 fsync 故障。生产源码已 source-ready，未再修改；仅独立 probe binary 用 link-time `--wrap=fsync` 定向检测 directory FD 下 `release_receipt.json` 已可见后返回 EIO。startup manifest 与 Python driver release 的正常 fsync 均没有被故障注入改变。

## 完成的实际观察

全新 `receipt_fsync_fault_02` 保存 ready、两个 poll 与 stderr，然后才按实际 schema 判定。结果通过：

- driver release 正常返回；合法 release 读取、解析、expiry 与 arm 发生。
- receipt 完成文件 fsync 和 no-replace rename，最终文件真实可见，nlink=1。
- receipt 的 directory fsync 收到实际注入 EIO，gate 进入 Fault；failure_phase=`receipt_io`。
- `receipt_io_completed=false`，原 freshness 读取仅前两次，final_freshness_now_ns 与 commit_steady_ns 均为 null；没有进入 Released。
- 第二 poll 仍 Fault、不调用 arm，没有“重试即可恢复”的推论。
- native process rc0。receipt 是 `prepared_acceptance`，`physical_output_state=held_pending_in_memory_commit` 且 `receipt_qualifies_physical_release=false`，不能把 receipt 可见写成内存 commit 或物理 ACK。

完整观察、源/二进制 SHA、真实 receipt 内容在 `receipt_fsync_fault_02.json`。这与 A 的 driver-release 目录 fsync 故障矩阵互补：driver release 已可见时 publisher 仍可能接受；publisher 自己的 receipt fsync 失败则维持原 Fault/held 语义。writer 返回、文件可见、gate 终态分别有独立证据。

## 失败证据与局限

第 01 次测试 harness 在两次 poll 后使用不存在的键 `final_freshness_steady_ns`，引发 KeyError；实际 schema 键名是 `final_freshness_now_ns`。原 01 目录和 receipt 字节保留，失败说明在 `receipt_fsync_fault_01_harness_failure.log`。该 harness 没有在异常前保存 native poll JSON，因此这些 stdout 已缺失，不回填或重建为原输出。第 02 次是新实例和新时间，不替换第 01 次。

本验证只表达当前 v10 header 与隔离测试 fsync 边界。无 ROS/Gazebo/plant/输出端，arm 是固定成功夹具，不能直接授予 owned 全链、真实 publisher 输出保护或其他阶段资格；它也不能解释此前未知 receipt timeout 原因。root 将统一构建并复跑原 56 个 publisher gate/node 组件用例和真实有界集成，单独形成版本证据。
