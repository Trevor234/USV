#!/usr/bin/env python
"""组会汇报图表：训练环境复演 — 同一条随机路径上 LOS 基线 vs v5 PPO 的轨迹与横向误差。

注意: 这是训练环境(纯 Python Fossen 模型)复演, 不是 VRX bag 回放; 图注必须保留此说明。
运行: usv_rl/.venv/bin/python fig_trajectory.py
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import VecNormalize

from usv_rl.baselines import LosController
from usv_rl.train import ROOT, make_env_fn

OUT = Path(__file__).resolve().parent
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "WenQuanYi Zen Hei", "AR PL UMing CN"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 200
plt.rcParams["savefig.dpi"] = 200
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.3
plt.rcParams["font.size"] = 11

MODEL = ROOT / "models" / "v5" / "s4_dr" / "model"
VEC = ROOT / "models" / "v5" / "s4_dr" / "vecnormalize.pkl"
SEED = 9999  # 与 evaluate.py 默认一致; 两个控制器用同一 env 种子 → 同一条参考路径


def rollout(action_mode: str):
    """跑一个 episode, 返回 (ref_xs, ref_ys, traj_x, traj_y, t, e_ct)。"""
    import usv_rl.evaluate as ev

    env_cfg = yaml.safe_load((ROOT / "configs" / "env.yaml").read_text())
    env_cfg["path_type"] = "random"
    for k in ("hydro_dr_frac", "thrust_delay_max_steps", "obs_noise_vel", "obs_noise_pos"):
        env_cfg[k] = 0
    venv = ev.build_eval_env(env_cfg, SEED, str(VEC) if action_mode == "ppo" else None)
    env = venv.envs[0].unwrapped
    model = PPO.load(MODEL, device="cpu") if action_mode == "ppo" else None
    los = LosController() if action_mode == "los" else None

    obs = venv.reset()
    ref = env.reference  # reset 会重新生成随机路径, 必须在 reset 后取参考
    xs, ys, ects, ts = [], [], [], []
    done, t = False, 0
    while not done:
        if action_mode == "ppo":
            action, _ = model.predict(obs, deterministic=True)
        else:
            action = los.act(env)
        obs, _, dones, infos = venv.step(np.asarray(action).reshape(1, -1))
        info = infos[0]
        done = bool(dones[0])
        if done:
            # DummyVecEnv 对 done 环境已自动 reset, 此时 env.state 是新回合初始态, 不可再录
            break
        xs.append(float(env.state[0]))
        ys.append(float(env.state[1]))
        ects.append(float(info.get("e_ct", 0.0)))
        ts.append(t * 0.2)
        t += 1
    venv.close()
    return (np.array(ref.xs), np.array(ref.ys), np.array(xs), np.array(ys),
            np.array(ts), np.array(ects), info)


def main() -> None:
    ref_x, ref_y, px, py, _, pe, pinfo = rollout("ppo")
    _, _, lx, ly, _, le, linfo = rollout("los")
    print(f"PPO: {pinfo.get('done_reason')}, 弧长进度 {pinfo.get('progress_s', 0):.1f} m, "
          f"e_ct RMS {np.sqrt(np.mean(pe**2)):.3f} m")
    print(f"LOS: {linfo.get('done_reason')}, 弧长进度 {linfo.get('progress_s', 0):.1f} m, "
          f"e_ct RMS {np.sqrt(np.mean(le**2)):.3f} m")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.0, 6.4), height_ratios=[2.2, 1.0])
    ax1.plot(ref_x, ref_y, "k--", lw=2.0, label="参考路径")
    ax1.plot(lx, ly, color="#7f8c9b", lw=1.4, label="LOS+PD 基线")
    ax1.plot(px, py, color="#2e7d32", lw=1.4, label="PPO v5")
    ax1.plot(ref_x[0], ref_y[0], "ko", ms=6)
    ax1.annotate("起点", xy=(ref_x[0], ref_y[0]), xytext=(4, 4), textcoords="offset points")
    ax1.set_aspect("equal")
    ax1.set_xlabel("x (m)")
    ax1.set_ylabel("y (m)")
    ax1.set_title("随机路径复演 (训练环境, 同一 seed, DR off) — 参考路径 vs 两种控制器", fontsize=12)
    ax1.legend(loc="best")
    ax2.plot(pe * 100, color="#2e7d32", lw=1.0, label="PPO v5")
    ax2.plot(le * 100, color="#7f8c9b", lw=1.0, label="LOS+PD 基线")
    ax2.axhline(0, color="k", lw=0.6)
    ax2.set_xlabel("时间步 (0.2 s)")
    ax2.set_ylabel("横向误差 e_ct (cm)")
    ax2.legend()
    fig.text(0.99, 0.005, "训练环境复演(非 VRX bag), 供形态对比; 汇报统计数字以 50-episode 评估为准",
             ha="right", fontsize=8, color="gray")
    fig.tight_layout()
    fig.savefig(OUT / "trajectory_replay.png", bbox_inches="tight")
    plt.close(fig)
    print("saved", OUT / "trajectory_replay.png")


if __name__ == "__main__":
    main()
