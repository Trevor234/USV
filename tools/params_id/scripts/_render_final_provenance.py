#!/usr/bin/env python3
"""Re-render the 2026-11-02 parameter package with truthful provenance.

The numbers come from the frozen `reidentification_20261102_v8` fit; this script
performs NO fitting and NO replay.  It only regenerates the presentation layer in
`reidentification_20261102_final`, with the real executed commands and an
explicit statement that `_final` is a re-render.
"""
import json
import os
import shutil
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reidentify_20261102 as R  # noqa: E402

D = "/home/trevor/MPC/01_MPC_Project/02_水面试验与硬件/USVANSIS"
BASE = os.path.join(D, "2026-11-02", "辨识产出")
SRC = os.path.join(BASE, "reidentification_20261102_v10")
DST = os.path.join(BASE, "reidentification_20261102_final_v10")
BASELINE = "/home/trevor/USV/usv_mpc_ws/src/usv_bringup/config/usv_params_B.yaml"
EXTRA = "/home/trevor/USV/data/flight_logs/20260625"
EXCL = os.path.join(D, "2026-11-02", "2026-11-02_失控段检测.json")

os.makedirs(DST, exist_ok=True)

fit = json.load(open(os.path.join(SRC, "fit", "params.json"), encoding="utf-8"))
metrics = json.load(open(os.path.join(SRC, "validation_metrics.json"), encoding="utf-8"))
man = json.load(open(os.path.join(SRC, "source_manifest.json"), encoding="utf-8"))

# Presentation-layer additions: the frozen run predates these two §8 caveats.
# They state limits only; no number, gate or verdict is altered.
for extra_limit in (
    "PWM neutral (1500 us) is NOT verified to produce zero thrust: no thrust "
    "measurement, no ESC telemetry and no verified ESC-to-prop mapping exist for "
    "2026-11-02. Logged PWM is a command proxy, not a measured force; no conclusion "
    "about the actual propulsion response is drawn from it.",
    "The logs show a sustained yaw rate while logged RCOU sits at 1500, with ARM/MODE "
    "transitions recorded normally and long recording gaps. This is an anomaly that "
    "warrants hardware investigation: the logs record only what the flight controller "
    "emitted, not what the ESCs received, so neither the mechanism nor a "
    "command-versus-response mismatch is established here. Diagnosis (ESC mid-point "
    "calibration, signal integrity, supply/thermal) and a verified safe-disarm are "
    "required before any further water test.",
):
    if extra_limit not in metrics["limitations"]:
        metrics["limitations"].append(extra_limit)
split = json.load(open(os.path.join(SRC, "split_manifest.json"), encoding="utf-8"))

# provenance artifacts are copied, never recomputed
for name, src in (("validation_metrics.json", os.path.join(SRC, "validation_metrics.json")),
                  ("fit_params.json", os.path.join(SRC, "fit", "params.json")),
                  ("validation_blind_compare.png",
                   os.path.join(SRC, "validation_blind_compare.png")),
                  ("validation_same_window.png",
                   os.path.join(SRC, "validation_same_window.png")),
                  ("fit_replay_parity.png", os.path.join(SRC, "fit", "replay_parity.png")),
                  ("fit_thruster_gains.png", os.path.join(SRC, "fit", "thruster_gains.png"))):
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(DST, name))

args = SimpleNamespace(data_root=D, extra_history=EXTRA, baseline=BASELINE,
                       exclusions=EXCL, out=DST, stage="validate")

PROVENANCE = f"""本目录是 `{SRC}` 的**重渲染**，不是一次独立执行。

真实执行过的命令（同一组五个路径参数，三次独立调用，`--out {SRC}`）：

```bash
export PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg
python3 scripts/reidentify_20261102.py \\
  --data-root '{D}' --extra-history '{EXTRA}' \\
  --baseline '{BASELINE}' --exclusions '{EXCL}' \\
  --out '{SRC}' --stage prepare
python3 scripts/reidentify_20261102.py ... --out '{SRC}' --stage fit
python3 scripts/reidentify_20261102.py ... --out '{SRC}' --stage validate
```

随后仅用下列命令重渲染展示层（不拟合、不回放、不重新评分盲测）：

```bash
python3 scripts/_render_final_provenance.py
```

因此：拟合与回放的**原始产物**在 `{SRC}`（含 `fit/params.json`、
`validation_metrics.json`、`fit/replay_parity.png`、`validation_blind_compare.png` 等），
本目录内同名副本是按原样复制的证据链接。"""

R._write_param_package(DST, args, fit, metrics, entry_meta=man, split=split)
R._write_report(DST, args, fit, metrics, entries=[], man=man, split=split, sets={},
                rb=metrics["blind"], rb0=metrics["blind_M0"],
                rh=metrics.get("history_replay") or {"n_windows": 0},
                rh0=metrics.get("history_replay_M0") or {"n_windows": 0})

path = os.path.join(DST, "identification_report.md")
text = open(path, encoding="utf-8").read()

# --- replace the misleading §1 command block with the real executed commands
old_start = text.index("## 1. 执行命令")
old_end = text.index("## 2. 数据清点与角色")
new_section = "## 1. 执行与产物来源\n\n" + PROVENANCE + "\n\n" \
    "依赖：" + ", ".join(f"{k}={v}" for k, v in metrics["versions"].items()) + "\n\n"
text = text[:old_start] + new_section + text[old_end:]

# --- observed-verification record
text += """
## 10. 核验记录

- 原始 BIN 未被修改：执行前后 `15-31-04` = `7415f212…cacaec2`、
  `16-00-09` = `6c6c1244…5e2d63fd`、`16-19-57` = `d9ea15ec…2815f68e`，
  与计划中的核验表逐字节一致。
- `usv_mpc_ws/src/usv_bringup/config/usv_params_B.yaml` 全程只读
  （sha256 `9425eb3f…5aa7600a`）；现用 ROS 配置、飞控参数与实船均未改动，未启动任何水试。
- 冻结清单 hash：`c493bc6054dcb2fb…`；随机种子 42；依赖版本见第 1 节。
- 写入隔离：已完成阶段的 `--out` 会被拒绝覆写（实测 prepare/fit 均返回冲突），
  因此每次修正都落在新目录（v1…v8），旧结果保留为证据。
- 回归测试：`python3 -m pytest -q tests/test_reidentify_20261102.py` → **12 passed**，
  覆盖开机绝对时间排除窗、`46.1→578.1 s` 缺口不跨越、ENU 差动符号与已知系数恢复
  （合成轨迹真值 Xu −2.2 / Nr −3.1 / 增益 25 N 被恢复到 0.01 % 以内，RMSE≈0）、
  无 ESC 等效路径不产生 RPM/K_RPM 伪结果、秩亏按规则降阶、替换盲测观测不改变候选、
  ESTALE 顺序复制、GPS 断链不继承旧健康值、POS 缺口不外推。
- 物理门槛实测：`M` 对称部分特征值 `[5.329, 16.2, 22.41]` 正定；`M` 可逆；
  `D` 对称部分最小特征值 `2.63 ≥ 0`；`max Re eig(−M⁻¹D) = −0.118 < 0`。
  但**完整速度子系统的数值 Jacobian 最大实部 = +2.112 > 0**，
  即观测包线内存在不稳定特征方向 —— 这是判定 `rejected` 的独立物理依据。
- 打靶估计的 `Nr`、`Nrr` 落在搜索盒边界（10× 先验），`Xuu` 塌缩到 0，
  `A_L_fwd` 仅为同组最大前向增益的 0.48 %：均**不构成可靠参数更新**，
  已在 `surge_params.json`/`yaw_params.json`/`parameter_comparison.csv` 的 `status`
  字段标注为 `boundary_hit_no_shooting_ci` / `near_zero_no_shooting_ci`。
  打靶估计本身没有置信区间（`ci_final_estimate: not_evaluable`）；
  文中 bootstrap 区间只属于线性回归初值。
- `T_max`、反推力、推力变化率、电压补偿一律未更新；因结论为 `rejected`，
  **未生成** `usv_params_candidate.yaml`。
- 盲测暴露：`16-19-57` 已被 `v6` 评分一次（结论 `rejected`），本次沿用同一冻结划分，
  未更换盲测文件、未修改任何门槛，但属**复用盲测**。
"""


# --- disclose the deviation from the approved gap rule ------------------------
gap_note = """
### 4.1 缺口阈值的偏离（必须记录）

计划 §2 规定每个源流用 `min(1.0, max(0.5, 3*median_positive_dt))` s 检测缺口。
该式用于状态/输入流（IMU 27 Hz、ATT 50 Hz、XKF1 50 Hz、RCOU 10 Hz）**完全照用，未改**。

但对**慢速辅助流**（GPS 健康门 ≈1 Hz、POS 状态回退 ≈25 Hz）该式的 1 s 上限会失效：
GPS 的正常采样间隔恰为 1.00 s，因此**每一次正常采样都会被判为缺口**。
实测：`06-08 15-16-31` 得 560 个"缺口"而真实中断只有 2 处（79.0 s、194.1 s）；
`06-08 15-44-56` 得 1069 个"缺口"而真实中断为 0。这检测的是采样率，不是数据丢失。

本次对这两条慢速流改用同形但上限不低于该流自身三倍节奏的阈值：

```
used  = max( min(1.0, max(0.5, 3*median_positive_dt)), 3*median_positive_dt )
```

- 状态/输入流：`3*median_dt` 远小于 0.5 s，结果与计划公式**逐个相同**。
- GPS/POS：阈值升到约 3 s，恰好仍能捕获真实中断（79.0 s、194.1 s、532.4 s），
  且不再误切正常采样。
- 影响范围：今日三份航行日志 GPS 为 0.2 s 节奏，阈值仍被 1.0 s 上限约束，
  **今日分段与判定未受该偏离影响**（用原式重算今日分段逐段相同，已实测）。
- 受影响的是历史候选：`06-08 15-16-31`（400.7 s / 23 段）与
  `06-08 15-44-56`（1135.9 s / 64 段）在本次阈值下被判为可用；
  若严格采用 1.0 s 上限，这两个文件几乎全部被判为缺口。
- **未执行**原阈值下的敏感性拟合。因此本报告只能说明：该偏离改变了历史可用样本量，
  从而可能改变 `M2` 的训练集与模型选择结果；**不能**据此断言"结论方向不变"。
  要量化该影响，需在独立 `--out` 下用原式重跑 prepare/fit/validate 一次，本次未做。
- 该偏离不涉及任何验收门槛（§6 的 u/r/位置/合成误差阈值全部未改）。
"""

anchor = "其余排除规则："
idx = text.index(anchor)
text = text[:idx] + gap_note.strip() + "\n\n" + text[idx:]

open(path, "w", encoding="utf-8").write(text)
print("re-rendered", DST)
for f in sorted(os.listdir(DST)):
    print("  ", f)
