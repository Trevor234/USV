"""策略/基线评估与指标对比。

用法:
    python -m usv_rl.evaluate --model ../artifacts/rl_models/v5/s4_dr/model.zip \
        --vecnorm ../artifacts/rl_models/v5/s4_dr/vecnormalize.pkl --episodes 50
    python -m usv_rl.evaluate --baseline los --episodes 50

指标（逐步统计 + 逐 episode 统计）:
    成功率 / 超时率 / 失败率
    横向误差 e_ct RMS（逐步）、位置误差 RMS（逐步）、航向误差 RMS（逐步）
    推力平方积分 Σ(T_L²+T_R²)·dt 及其共模、差模分量（逐 episode 均值）
    控制平滑 Σ|ΔT|、进度与单位进度推力平方积分（逐 episode 均值）
    反向推力占比、纵向速度误差 u - v_ref（逐步统计）
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from usv_rl.baselines import LosController
from usv_rl.train import load_configs, make_env_fn, resolve_device


def build_eval_env(
    env_cfg: dict, seed: int, vecnorm_path: str | None, *, vecnormalize_cfg: dict | None = None,
) -> VecNormalize:
    venv = DummyVecEnv([make_env_fn(dict(env_cfg), seed)])
    if vecnorm_path and Path(vecnorm_path).exists():
        venv = VecNormalize.load(vecnorm_path, venv)
    else:
        options = {k: v for k, v in (vecnormalize_cfg or {}).items() if k != "norm_reward"}
        venv = VecNormalize(venv, training=False, norm_reward=False, **options)
    venv.training = False
    venv.norm_reward = False
    return venv


def run_episodes(venv: VecNormalize, action_fn, episodes: int) -> dict:
    """action_fn(venv, obs) -> action。逐步/逐 episode 收集指标。"""
    step_e_ct, step_e_psi, step_e_pos, step_e_surge = [], [], [], []
    successes = timeouts = failures = opposing_steps = 0
    energies, smooths, progress = [], [], []
    cm_energies, dm_energies, progress_m, energies_per_meter = [], [], [], []
    dt = venv.get_attr("dt")[0]

    for _ in range(episodes):
        obs = venv.reset()
        done = False
        ep_energy = ep_cm_energy = ep_dm_energy = ep_smooth = 0.0
        prev_thrust = np.zeros(2)
        info: dict = {}
        while not done:
            action = action_fn(venv, obs)
            # VecEnv.step 需要 (n_envs, action_dim)；单环境时兼容 (action_dim,)
            action = np.asarray(action).reshape(1, -1)
            obs, _, dones, infos = venv.step(action)
            info = infos[0]
            applied = np.asarray(info.get("applied_thrust", np.zeros(2)))
            tl, tr = float(applied[0]), float(applied[1])
            ep_energy += float(np.sum(applied ** 2)) * dt
            ep_cm_energy += 2.0 * (0.5 * (tl + tr)) ** 2 * dt
            ep_dm_energy += 2.0 * (0.5 * (tr - tl)) ** 2 * dt
            opposing_steps += int(tl * tr < 0.0)
            ep_smooth += float(np.sum(np.abs(applied - prev_thrust)))
            prev_thrust = applied
            step_e_ct.append(info.get("e_ct", 0.0))
            step_e_psi.append(info.get("e_psi", 0.0))
            step_e_pos.append(info.get("e_pos", 0.0))
            step_e_surge.append(info.get("signed_surge_error", 0.0))
            done = bool(dones[0])
        reason = info.get("done_reason", "")
        successes += int(reason == "success")
        timeouts += int(reason == "timeout")
        failures += int(reason in ("pos_err", "psi_err"))
        ep_progress_m = info.get("progress_s", 0.0)
        energies.append(ep_energy)
        cm_energies.append(ep_cm_energy)
        dm_energies.append(ep_dm_energy)
        energies_per_meter.append(ep_energy / max(ep_progress_m, 1e-6))
        smooths.append(ep_smooth)
        progress_m.append(ep_progress_m)
        progress.append(ep_progress_m / max(info.get("total_s", 1.0), 1e-9))

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
        "cm_energy_mean": float(np.mean(cm_energies)) if cm_energies else 0.0,
        "dm_energy_mean": float(np.mean(dm_energies)) if dm_energies else 0.0,
        "opposing_thrust_fraction": opposing_steps / max(len(step_e_ct), 1),
        "energy_per_meter_mean": float(np.mean(energies_per_meter)) if energies_per_meter else 0.0,
        "signed_surge_error_mean": float(np.mean(step_e_surge)) if step_e_surge else 0.0,
        "smooth_mean": float(np.mean(smooths)) if smooths else 0.0,
        "progress_m_mean": float(np.mean(progress_m)) if progress_m else 0.0,
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
    print(f"  共模 / 差模   : {r['cm_energy_mean']:.1f} / {r['dm_energy_mean']:.1f} N²·s")
    print(f"  反向推力占比  : {r['opposing_thrust_fraction']:.1%}")
    print(f"  平均进度距离  : {r['progress_m_mean']:.2f} m")
    print(f"  单位进度能耗  : {r['energy_per_meter_mean']:.3f} N²·s/m")
    print(f"  有符号纵向速度误差均值: {r['signed_surge_error_mean']:+.3f} m/s")


def main() -> None:
    parser = argparse.ArgumentParser(description="USV 方案C 评估")
    parser.add_argument("--model", default=None)
    parser.add_argument("--vecnorm", default=None)
    parser.add_argument("--baseline", choices=["los"], default=None)
    parser.add_argument("--config", help="覆盖 YAML（ppo_override/env_override）")
    parser.add_argument("--episodes", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--path-type")
    args = parser.parse_args()

    ppo_cfg, env_cfg = load_configs(args.config)
    eval_cfg = ppo_cfg["eval"] if args.config else {}
    episodes = args.episodes if args.episodes is not None else eval_cfg.get("n_episodes", 50)
    default_seed = ppo_cfg["seed"] if args.config else 9999
    seed = args.seed if args.seed is not None else default_seed
    path_type = args.path_type if args.path_type is not None else eval_cfg.get("path_type", "random")
    vnorm_cfg = ppo_cfg["vecnormalize"] if args.config else None
    env_cfg["path_type"] = path_type
    # 评估恒定关闭 DR
    for k in ("hydro_dr_frac", "thrust_delay_max_steps", "obs_noise_vel", "obs_noise_pos"):
        env_cfg[k] = 0

    print(f"评估配置: path_type={path_type} episodes={episodes} DR=off\n")

    if args.baseline == "los":
        venv = build_eval_env(env_cfg, seed, None, vecnormalize_cfg=vnorm_cfg)
        los = LosController()

        def los_action(v, obs):
            return los.act(v.envs[0].unwrapped)

        results = run_episodes(venv, los_action, episodes)
        print_results("LOS 基线", results)
    elif args.model:
        from stable_baselines3 import PPO

        venv = build_eval_env(env_cfg, seed, args.vecnorm, vecnormalize_cfg=vnorm_cfg)
        device = resolve_device(ppo_cfg.get("device", "cpu")) if args.config else "cpu"
        model = PPO.load(args.model, device=device)

        def policy_action(_v, obs):
            action, _ = model.predict(obs, deterministic=eval_cfg.get("deterministic", True))
            return action

        results = run_episodes(venv, policy_action, episodes)
        print_results(f"PPO ({Path(args.model).parent.name})", results)
    else:
        parser.error("需要 --model 或 --baseline los")


if __name__ == "__main__":
    main()
