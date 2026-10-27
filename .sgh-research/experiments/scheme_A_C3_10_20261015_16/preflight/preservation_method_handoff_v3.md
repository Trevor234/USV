# C3.10 保护链展平实施说明

正式实现为 `protection_v3.py`。`complete` 只用于已经成功的 v1 父语义计算的首次、create-only 续接；之后使用 `protect()` 或 CLI `verify`，不重新执行递归父 helper，也不缓存或跳过原始文件字节。

初始成功结果为 `workspace_initial_v3.json`。固定 roster 为 `preservation_roster_v3.json`，SHA-256 为 `4c9062d9033e2bd89ba34e3bf2c9490251b8bb0679a06018860fc74bc163583d`；anchor 为 `preservation_anchor_v3.json`。

初始续接完整读取 34,296 个唯一文件，共 3,108,867,869 bytes，并核对 1,344 个目录的直接子项人口。每次后续验证继续完整流式 SHA；FD 与命名文件的身份、大小、修改信息在读取前后核对，普通原始读取仍逐级 `O_NOFOLLOW`。证明明确包含 D15/M15 的 3,164 对文件与完整目录人口、D15 QA 的 5,119 个固定路径、2,559 对冻结文件，以及历史保护代码实际读取的原始资产。

一次原封不动的父 `archive_v1.protect()` 已成功执行，其结果必须与固定 D15 inventory/delivery 中四份父证明相等。`sitecustomize.py` 随 Python 环境传播到全部递归 Python 子进程，记录普通打开、带 dir_fd 的实际 FD 路径、目录枚举和 `acceptance_core.Reader.raw` 实际返回字节的 SHA。两个 Python 进程均记录到 end；父语义计算 stderr 为空。六个不同读路径/子进程校准与三个 workspace 投影用例通过。

13 份捕获来源文件在 anchor 中固定，并由每次 `protect()` 重读 SHA，包含父证明、全部实际捕获 trace、v1 helper/tracer/校准、校准 trace、v2 源码与两次失败结果。此处的来源证明及历史资产均不依赖 mtime 缓存。

## 两次保留的失败

`workspace_initial.json` 是 v1 展平失败：原父语义计算成功，但严格 no-follow 读遇到旧 ROS symlink-install 的 8 个逻辑别名。v3 显式固定这 8 个逻辑路径的 canonical 解析和 2 个 symlink 的目标，再对 canonical 文件读取全部字节；每次验证同时重检别名解析与 symlink 原文。没有把旧 symlink-install 改成普通文件。

`workspace_initial_v2.json` 是 v2 的错误 mode 断言失败：例如 D15 `CURRENT.md` 源为 0664，MPC 挂载映射为 0755；其 SHA 和 bytes 完全相等。旧库存保护只认证内容，不要求源/目的权限相等。v3 依照原库存 SHA/bytes 验证内容，并在 roster 中分别固定源和目的实际权限，后续仍拒绝权限变化；没有修改旧权限。失败文本 `original_raw_bytes_changed` 实际由权限比较触发，不能据此解释为旧文件内容漂移。

## Workspace 边界

完整、未过滤的现时 workspace 保存在成功初始结果与 anchor。稳定比较仅排除本批 D16、新作者 N17 这两个精确前缀的 `??` 未跟踪状态行；带中文路径的 Git 引号形式也按这两个前缀处理。其余状态、原始 24 个业务 dirty、HEAD、分支、boot、全部 staging、gitignore 和 submodule 状态继续固定。被跟踪的变化不会因位于新根而排除。

本轮最早完整 untracked 列表没有另存，明确标记 `initial_full_untracked_snapshot_unavailable=true`。现时快照不能补证那份未保存的列表；保护声明限于声明冻结资产、固定归档库存、原保护代码实际读取内容，以及从 v3 现时快照起固定的其它 workspace 状态。不能据此声称认证了全部 OS 内容或最早全部 untracked 文件内容。

该实现验证资产保存与实验前置条件，不授予任何阶段、execute 或研究结论资格。初始续接用时约 170 秒只是本机离线文件校验观测，不是控制 WCET。
