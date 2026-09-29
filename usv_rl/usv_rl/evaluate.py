"""策略/基线评估与指标对比。

用法:
    python -m usv_rl.evaluate --model models/v0/best/best_model.zip \
        --vecnorm models/v0/best/vecnormalize.pkl --episodes 50
    python -m usv_rl.evaluate --baseline los --episodes 50

指标（逐步统计 + 逐 episode 统计）:
    成功率 / 超时率 / 失败率
    横向误差 e_ct RMS（逐步）、位置误差 RMS（逐步）、航向误差 RMS（逐步）
    能耗 Σ(T_L²+T_R²)·dt（逐 episode 均值）、控制平滑 Σ|ΔT|
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import yaml
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from usv_rl.baselines import LosController
from usv_rl.envs import _ENV_ID
from usv_rl.train import ROOT, make_env_fn


def build_eval_env(env_cfg: dict, seed: int, vecnorm_path: str | None) -> VecNormalize:
    venv = DummyVecEnv([make_env_fn(dict(env_cfg), seed)])
    if vecnorm_path and Path(vecnorm_path).exists():
        venv = VecNormalize.load(vecnorm_path, venv)
    else:
        venv = VecNormalize(venv, training=False, norm_reward=False)
    venv.training = False
    venv.norm_reward = False
    return venv


def run_episodes(venv: VecNormalize, action_fn, episodes: int) -> dict:
    """action_fn(venv, obs) -> action。逐步/逐 episode 收集指标。"""
    step_e_ct, step_e_psi, step_e_pos = [], [], []
    successes = timeouts = failures = 0
    energies, smooths, progress = [], [], []

    for _ in range(episodes):
        obs = venv.reset()
        done = False
        ep_energy, ep_smooth = 0.0, 0.0
        prev_thrust = np.zeros(2)
        info: dict = {}
        while not done:
            action = action_fn(venv, obs)
            # VecEnv.step 需要 (n_envs, action_dim)；单环境时兼容 (action_dim,)
            action = np.asarray(action).reshape(1, -1)
            obs, _, dones, infos = venv.step(action)
            info = infos[0]
            applied = info.get("applied_thrust", np.zeros(2))
            ep_energy += float(np.sum(np.asarray(applied) ** 2)) * 0.2
            ep_smooth += float(np.sum(np.abs(np.asarray(applied) - prev_thrust)))
            prev_thrust = np.asarray(applied)
            step_e_ct.append(info.get("e_ct", 0.0))
            step_e_psi.append(info.get("e_psi", 0.0))
            step_e_pos.append(info.get("e_pos", 0.0))
            done = bool(dones[0])
        reason = info.get("done_reason", "")
        successes += int(reason == "success")
        timeouts += int(reason == "timeout")
        failures += int(reason in ("pos_err", "psi_err"))
        energies.append(ep_energy)
        smooths.append(ep_smooth)
        progress.append(info.get("progress_s", 0.0) / max(info.get("total_s", 1.0), 1e-9))

    n = max(episodes, 1)
    return {
        "success_rate": successes / n,
        "timeout_rate": timeouts / n,
        "failure_rate": failures / n,
        "e_ct_rms": float(np.sqrt(np.mean(np.square(step_e_ct)))) if step_e_ct else 0.0,
        "e_ct_max": float(np.max(np.abs(step_e_ct))) if step_e_ct else 0.0,
        "e_pos_rms": float(np.sqrt(np.mean(np.square(step_e_pos)))) if step_e_pos else 0.0,
        "e_psi_rms_deg": float(np.degrees(np.sqrt(np.mean(np.square(step_e_psi))))) if step_e_psi else 0.0,
        "energy_mean": float(np.mean(energies)) if energies else 0.0,
        "smooth_mean": float(np.mean(smooths)) if smooths else 0.0,
        "progress_frac_mean": float(np.mean(progress)) if progress else 0.0,
    }


def print_results(name: str, r: dict) -> None:
    print(f"===== {name} =====")
    print(f"  成功率        : {r['success_rate']:.1%}  "
          f"(超时 {r['timeout_rate']:.1%} / 失败 {r['failure_rate']:.1%})")
    print(f"  横向误差 RMS  : {r['e_ct_rms']:.3f} m (max {r['e_ct_max']:.3f})")
    print(f"  位置误差 RMS  : {r['e_pos_rms']:.3f} m")
    print(f"  航向误差 RMS  : {r['e_psi_rms_deg']:.1f}°")
    print(f"  能耗均值      : {r['energy_mean']:.1f} N²·s")
    print(f"  控制平滑      : {r['smooth_mean']:.1f} N/episode")
    print(f"  平均进度      : {r['progress_frac_mean']:.1%}")


def main() -> None:
    parser = argparse.ArgumentParser(description="USV 方案C 评估")
    parser.add_argument("--model", default=None)
    parser.add_argument("--vecnorm", default=None)
    parser.add_argument("--baseline", choices=["los"], default=None)
    parser.add_argument("--episodes", type=int, default=50)
    parser.add_argument("--seed", type=int, default=9999)
    parser.add_argument("--path-type", default="random")
    args = parser.parse_args()

    env_cfg = yaml.safe_load((ROOT / "configs" / "env.yaml").read_text())
    env_cfg["path_type"] = args.path_type
    # 评估恒定关闭 DR
    for k in ("hydro_dr_frac", "thrust_delay_max_steps", "obs_noise_vel", "obs_noise_pos"):
        env_cfg[k] = 0

    print(f"评估配置: path_type={args.path_type} episodes={args.episodes} DR=off\n")

    if args.baseline == "los":
        venv = build_eval_env(env_cfg, args.seed, None)
        los = LosController()

        def los_action(v, obs):
            return los.act(v.envs[0].unwrapped)

        results = run_episodes(venv, los_action, args.episodes)
        print_results("LOS 基线", results)
    elif args.model:
        from stable_baselines3 import PPO

        venv = build_eval_env(env_cfg, args.seed, args.vecnorm)
        model = PPO.load(args.model, device="cpu")

        def policy_action(_v, obs):
            action, _ = model.predict(obs, deterministic=True)
            return action

        results = run_episodes(venv, policy_action, args.episodes)
        print_results(f"PPO ({Path(args.model).parent.name})", results)
    else:
        parser.error("需要 --model 或 --baseline los")


if __name__ == "__main__":
    main()
