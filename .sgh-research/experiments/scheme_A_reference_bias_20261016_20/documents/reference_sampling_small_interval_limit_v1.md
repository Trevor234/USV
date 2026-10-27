# 极小 profile 时间间隔：当前资格范围之外的已知边界

日期：2026-10-17。本记录不改变已冻结的候选头文件、Observer、Worker、合同或原 96 项组件结果。

独立原生最小反例仍使用 201 个直线路径点，但把 profile 的第一个时间间隔从 0.2 s 改为 1e-12 s；其余时间严格递增。目标位置 x=0.005 m，首段路径 x=0→0.01 m。连续投影得到 fraction≈0.5、t0≈5e-13 s、projection_x=0.005 m，当前候选返回 valid=true；实际复用的 legacy sampler 输出 ref0.x=0 m。

原因是已固定静态库的 `sample_path_profile_at_time()` 对 `t_seg > 1e-9` 才插值，否则把 alpha 置零。这使 metadata 投影点与极小间隔的实际参考首点不一致。Source 阈值行、源码及实际静态库 SHA、prebuild pins 和原生输出均在配套 JSON 中。

当前预注册运行域严格使用 201 点、每段 0.2 s 的四级参考，此反例在该域之外。它不是第 19 批 22–25% 速度偏高的根因，不否定当前固定域的组件结果，也不授予通用 profile 输入资格。下一批若扩展时间输入域，需要新版本明确拒绝极小间隔或实现与投影一致的采样，再加入该反例回归；原源码及原证据保留。

展示 harness 的 attempt01 使用 fraction==0.5，受浮点舍入影响把“已显示出的差异”错误标为未展示，原失败输出保留。attempt02 只修正展示断言的浮点比较，未修改候选实现或阈值，成功记录同一个语义差异。

证据：`postrun/small_profile_interval_known_limitation_v1.json`、`build/small_interval_boundary_attempt01/` 和 `attempt02/`。这是已知限制的重现，不计入生产运行通过数。
