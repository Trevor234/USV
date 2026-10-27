# C3.4-A 发布协议修复预登记（2026-10-13）

本工作仅在新派生 `authored_D1_C3_4_20261013_v10` 修改 create-only 发布原语；旧 v9、review 原探针与所有旧证据只读。发布目标首次可见时必须已经写完、完成文件 fsync 且为单链接 regular file；不得通过删除 single-link 读取门、重试、期限延长或改变原三个 freshness 读取来闭合。

## 实现约束

- Python、owned C++ 与 publisher C++ 统一采用同目录 `renameat2(RENAME_NOREPLACE)`；不使用覆盖 rename、os.replace 或 link/unlink 发布。实际 Linux 文件系统先记录类型与 no-overwrite 支持，unsupported 时明确失败。
- C++ 共用一个无 ROS 依赖的 publication header。原路径通过逐段 nofollow directory FD，临时文件 O_EXCL/O_NOFOLLOW，文件预算保留；Python 对父目录采用相同 FD 路径约束。
- 完成临时文件写入和文件 fsync 后再原子发布，随后 fsync 目录。目录 fsync 异常必须保留可见目标和原异常链；未发布异常只清理本调用独占临时路径，不删除既有目标。
- Python strict_json 同时拒绝浮点解析溢出（例如 1e309）和显式 NaN/Infinity。
- runtime 不增加测试 hook、诊断 IO、额外 freshness 读取；故障注入只在隔离探针/测试中发生。

## 先验矩阵

1. 原 v9 正常与双链接竞态报告作旧对照，原源码和结果不改变；复制源链接探针显式改为 v10。
2. 新正常与目录 fsync 暂停：目标首次可读 nlink=1；在 writer 返回前原 publisher gate 可 Released；原时间事件顺序保持。
3. 同目标 EEXIST：不覆盖，目标字节/ inode 保持；本调用临时路径清理。
4. symlink（含父目录）、FIFO、多硬链接：读取门仍拒绝；create-only 不覆盖这些目标。
5. 写入暂停/失败与文件 fsync 失败：发布前目标缺失；实际已存在目标保持；无 partial visible target。
6. 目录 fsync 失败：目标可见且 nlink=1；Python 保留 PublicationAmbiguousError 与 errno cause；原 C++ gate 可接受该可见 release，不授予正常全链资格。
7. C++ 共用原语实际文件系统正常、EEXIST、post-publish fsync 错误路径（测试-only 拦截）；正常临时文件不残留。
8. 所有原 56 publisher tests 的身份及 gate 语义保留，必要错误字符串仅将错误操作名 link 更新为 rename。

所有失败保存独立输出，成功结果只表达组件适用范围。无 ROS/Gazebo/plant/物理输出；历史 receipt timeout 根因、D1/B4/B5/M0b/M4/F6/P1 与研究结论仍不得据此提升。
