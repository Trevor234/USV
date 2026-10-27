#!/usr/bin/env python
"""组会汇报图表：从 TensorBoard 事件文件生成训练曲线图。

数据来源: <artifacts>/rl_runs/{v1..v5}/<run>_1/events.out.tfevents.* (每阶段一个文件, 按步数合并)。
         <artifacts> 默认是仓库顶层 artifacts/，见 usv_rl.paths。
用途: usv_rl/docs/ 组会汇报 PPT。运行: usv_rl/.venv/bin/python fig_curves.py
"""
import glob
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from usv_rl.paths import RL_RUNS

ROOT = RL_RUNS
OUT = Path(__file__).resolve().parent

# 中文字体候选(按优先级), 渲染时若缺字形会有 warning, 用 -W error 可暴露
plt.rcParams["font.sans-serif"] = [
    "Noto Sans CJK SC", "WenQuanYi Zen Hei", "AR PL UMing CN", "AR PL UKai CN",
]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 200
plt.rcParams["savefig.dpi"] = 200
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.3
plt.rcParams["font.size"] = 11

COLORS = {"v1": "#999999", "v2": "#c44e52", "v3": "#8172b2", "v4": "#ccb974", "v5": "#2e7d32"}


def load_run(run: str, tags: list[str]) -> dict[str, list[tuple[int, float]]]:
    """合并一个 run 的全部事件文件(=课程阶段分段), 按 step 排序、同 step 保留后值。"""
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    files = sorted(glob.glob(str(ROOT / run / f"{run}_1" / "events*")))
    if not files:
        raise FileNotFoundError(f"{run}: no event files")
    merged: dict[str, dict[int, float]] = {t: {} for t in tags}
    for f in files:
        ea = EventAccumulator(f, size_guidance={"scalars": 0})
        ea.Reload()
        for tag in tags:
            if tag in ea.Tags()["scalars"]:
                for e in ea.Scalars(tag):
                    merged[tag][e.step] = e.value
    out = {}
    for tag, d in merged.items():
        if d:
            out[tag] = sorted(d.items())
    return out


def fig_cross_version(data: dict) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    for v in ["v1", "v2", "v3", "v4", "v5"]:
        pts = data[v]["rollout/success_rate"]
        ax.plot([s / 1e6 for s, _ in pts], [val for _, val in pts],
                color=COLORS[v], lw=1.8, label=v)
    for x, name in [(1.0, "s2 折线"), (3.0, "s3 随机"), (6.0, "s4 +DR")]:
        ax.axvline(x, color="gray", ls=":", lw=1.0)
        ax.text(x, 1.045, name, ha="center", fontsize=9, color="dimgray")
    ax.annotate("v1–v3 全程为 0:\n自尽 / 倒车走线 / 悬停", xy=(8.3, 0.005), xytext=(6.3, 0.18),
                fontsize=10, arrowprops=dict(arrowstyle="->", lw=0.8))
    ax.set_xlabel("训练步数 (×10$^6$)")
    ax.set_ylabel("成功率 (训练 rollout)")
    ax.set_ylim(-0.03, 1.1)
    ax.set_xlim(0, 10.2)
    ax.legend(ncol=5, loc="center right", framealpha=0.9)
    ax.set_title("五个版本训练成功率 — v1–v3 被 reward hacking 卡死, v4–v5 修复后收敛", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "curves_success_cross_version.png", bbox_inches="tight")
    plt.close(fig)


def fig_v5_detail(data: dict) -> None:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.5, 5.4), sharex=True)
    pts = data["v5"]["rollout/ep_rew_mean"]
    ax1.plot([s / 1e6 for s, _ in pts], [val for _, val in pts], color="#2e7d32", lw=1.5)
    ax1.set_ylabel("平均回合奖励")
    ax1.set_title("v5 训练收敛细节 (s4_dr 域随机化阶段全程在线)", fontsize=12)
    ev = data["v5"].get("eval/success_rate", [])
    ax2.plot([s / 1e6 for s, _ in ev], [val for _, val in ev],
             color="#1f77b4", lw=1.2, label="eval/success_rate")
    ax2.axhline(1.0, color="gray", ls="--", lw=0.8)
    ax2.scatter([10.09], [1.0], color="#1f77b4", zorder=5)
    ax2.annotate("最终 1.00\n(50 eps 验证, DR off)", xy=(10.09, 1.0), xytext=(7.6, 0.55),
                 fontsize=10, arrowprops=dict(arrowstyle="->", lw=0.8))
    ax2.set_xlabel("训练步数 (×10$^6$)")
    ax2.set_ylabel("评估成功率 (DR off)")
    ax2.set_ylim(-0.03, 1.1)
    fig.tight_layout()
    fig.savefig(OUT / "v5_convergence.png", bbox_inches="tight")
    plt.close(fig)


def fig_v3_eplen(data: dict) -> None:
    fig, ax = plt.subplots(figsize=(9.0, 3.8))
    pts = data["v3"]["rollout/ep_len_mean"]
    ax.plot([s / 1e6 for s, _ in pts], [val for _, val in pts], color=COLORS["v3"], lw=1.5)
    ax.annotate("303 步", xy=(0.1, 303), xytext=(0.5, 260),
                fontsize=10, arrowprops=dict(arrowstyle="->", lw=0.8))
    ax.annotate("≈29 步\n“求死通道”", xy=(9.5, 29), xytext=(7.2, 110),
                fontsize=10, arrowprops=dict(arrowstyle="->", lw=0.8))
    ax.set_xlabel("训练步数 (×10$^6$)")
    ax.set_ylabel("平均回合长度 (步)")
    ax.set_title("v3: 提前终止被策略当成了“速死止损通道” — ep_len 单调衰减", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "v3_ep_len_decay.png", bbox_inches="tight")
    plt.close(fig)


def fig_results_bar() -> None:
    """README v5 表(50 eps, 随机路径, DR off): LOS 基线 vs PPO; 能耗来自本次复现评估。"""
    metrics = [
        ("横向误差 RMS (m)", 0.404, 0.312, "−23%", False),
        ("横向误差 max (m)", 1.172, 1.056, "−10%", False),
        ("航向误差 RMS (°)", 25.8, 16.1, "−38%", False),
        ("能耗均值 (N²·s)", 2416.5, 7338.5, "+203%", True),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(11.5, 3.4))
    for ax, (name, los, ppo, delta, worse) in zip(axes, metrics):
        bars = ax.bar(["LOS", "PPO v5"], [los, ppo], color=["#7f8c9b", "#2e7d32"], width=0.55)
        for b, val in zip(bars, [los, ppo]):
            ax.text(b.get_x() + b.get_width() / 2, val, f"{val:g}",
                    ha="center", va="bottom", fontsize=10, fontweight="bold")
        ax.set_title(f"{name}\n({delta}, {'代价' if worse else '更优'})", fontsize=10.5)
        ax.set_ylim(0, max(los, ppo) * 1.25)
    fig.suptitle("v5 评估: PPO vs LOS+PD — 随机路径 50 eps, DR off（前 3 项: README v5 表; 能耗: 本次复现评估）",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(OUT / "results_bar.png", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    tags = ["rollout/success_rate", "rollout/ep_rew_mean", "rollout/ep_len_mean", "eval/success_rate"]
    data = {v: load_run(v, tags) for v in ["v1", "v2", "v3", "v4", "v5"]}
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)  # 缺字形直接报错而不是画豆腐块
        fig_cross_version(data)
    fig_v5_detail(data)
    fig_v3_eplen(data)
    fig_results_bar()
    for v in ["v1", "v2", "v3", "v4", "v5"]:
        pts = data[v]["rollout/success_rate"]
        print(f"{v}: success_rate 首值 {pts[0][1]:.2f} → 末值 {pts[-1][1]:.2f}, "
              f"共 {len(pts)} 点, 步数范围 {pts[0][0]}..{pts[-1][0]}")
    print("figures written to", OUT)


if __name__ == "__main__":
    main()
