"""PPO 训练入口（方案C）。

用法:
    python -m usv_rl.train --run-name v0 --total-steps 10000000
    python -m usv_rl.train --run-name v0 --stage s4_dr          # 只跑单阶段
    python -m usv_rl.train --run-name v0 --resume models/v0/s3_random/model.zip

结构:
- 训练环境: SubprocVecEnv(UsvTrackingEnv) + VecNormalize
- 课程: ppo.yaml curriculum 顺序执行，模型与归一化统计全程延续
- 评估: EvalCallback 定期在无 DR 环境上确定性评估，保存 best_model
- 产物: models/<run>/<stage>/model.zip + vecnormalize.pkl；runs/<run>/ TensorBoard
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import gymnasium as gym
import numpy as np
import torch
import yaml
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecNormalize

from usv_rl.envs import _ENV_ID

ROOT = Path(__file__).resolve().parents[1]


def linear_schedule_fn(initial_lr: float):
    """SB3 调度接口：progress_remaining ∈ [0,1] 线性衰减到 0。"""
    def func(progress_remaining: float) -> float:
        return progress_remaining * initial_lr
    return func


def load_configs(config_path: str | None) -> tuple[dict, dict]:
    ppo_cfg = yaml.safe_load((ROOT / "configs" / "ppo.yaml").read_text())
    env_cfg = yaml.safe_load((ROOT / "configs" / "env.yaml").read_text())
    if config_path:
        override = yaml.safe_load(Path(config_path).read_text())
        ppo_cfg.update(override.get("ppo_override", {}))
        env_cfg.update(override.get("env_override", {}))
    return ppo_cfg, env_cfg


def make_env_fn(env_cfg: dict, seed: int):
    def _init():
        env = gym.make(_ENV_ID, **env_cfg)
        env.reset(seed=seed)
        return Monitor(env)
    return _init


class SyncVecNormalizeEvalCallback(EvalCallback):
    """每次评估前把训练 VecNormalize 的 obs 统计同步给评估环境（SB3 官方示例模式）。"""

    def __init__(self, *args, train_env: VecNormalize, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._train_env_ref = train_env

    def _on_step(self) -> bool:
        train_norm = self._train_env_ref
        if isinstance(train_norm, VecNormalize):
            self.eval_env.obs_rms = train_norm.obs_rms
            self.eval_env.ret_rms = train_norm.ret_rms
        self.eval_env.training = False
        self.eval_env.norm_reward = False
        return super()._on_step()


def build_vec_env(env_cfg: dict, n_envs: int, base_seed: int, use_subproc: bool):
    fns = [make_env_fn(dict(env_cfg), base_seed + i) for i in range(n_envs)]
    if use_subproc and n_envs > 1:
        return SubprocVecEnv(fns, start_method="spawn")
    return DummyVecEnv(fns)


def main() -> None:
    parser = argparse.ArgumentParser(description="USV 方案C PPO 训练")
    parser.add_argument("--run-name", default=f"run_{time.strftime('%Y%m%d_%H%M%S')}")
    parser.add_argument("--config", default=None, help="覆盖 YAML（ppo_override/env_override）")
    parser.add_argument("--total-steps", type=int, default=None, help="覆盖课程总步数")
    parser.add_argument("--stage", default=None, help="只训练指定课程阶段")
    parser.add_argument("--n-envs", type=int, default=None)
    parser.add_argument("--resume", default=None, help="model.zip 路径（需同目录 vecnormalize.pkl）")
    parser.add_argument("--no-subproc", action="store_true")
    args = parser.parse_args()

    ppo_cfg, env_cfg = load_configs(args.config)
    if args.n_envs:
        ppo_cfg["n_envs"] = args.n_envs
    n_envs = ppo_cfg["n_envs"]
    seed = ppo_cfg["seed"]

    run_dir = ROOT / "models" / args.run_name
    tb_dir = ROOT / "runs" / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    stages = [s for s in ppo_cfg["curriculum"] if args.stage in (None, s["name"])]
    if args.total_steps:
        per = args.total_steps // len(stages)
        for s in stages:
            s["total_steps"] = per

    eval_cfg = ppo_cfg["eval"]
    eval_env_cfg = dict(env_cfg)
    eval_env_cfg.pop("path_type", None)
    eval_env = VecNormalize(
        DummyVecEnv([make_env_fn({**eval_env_cfg, "path_type": eval_cfg["path_type"]}, seed + 1000)]),
        training=False, norm_reward=False,
        norm_obs=ppo_cfg["vecnormalize"]["norm_obs"],
        clip_obs=ppo_cfg["vecnormalize"]["clip_obs"],
        gamma=ppo_cfg["vecnormalize"]["gamma"],
    )

    vn = ppo_cfg["vecnormalize"]
    train_env = VecNormalize(
        build_vec_env(env_cfg, n_envs, seed, not args.no_subproc),
        norm_obs=vn["norm_obs"], norm_reward=vn["norm_reward"],
        clip_obs=vn["clip_obs"], gamma=vn["gamma"],
    )

    activation = {
        "tanh": torch.nn.Tanh, "relu": torch.nn.ReLU,
    }[ppo_cfg["policy_kwargs"]["activation_fn"]]
    ppo_kw = ppo_cfg["ppo"]
    lr = ppo_kw["learning_rate"]
    schedule = linear_schedule_fn(lr) if ppo_kw.get("lr_schedule") == "linear" else lr

    model = PPO(
        "MlpPolicy", train_env,
        policy_kwargs=dict(net_arch=ppo_cfg["policy_kwargs"]["net_arch"], activation_fn=activation),
        learning_rate=schedule,
        n_steps=ppo_kw["n_steps"], batch_size=ppo_kw["batch_size"],
        n_epochs=ppo_kw["n_epochs"], gamma=ppo_kw["gamma"],
        gae_lambda=ppo_kw["gae_lambda"], clip_range=ppo_kw["clip_range"],
        ent_coef=ppo_kw["ent_coef"], vf_coef=ppo_kw["vf_coef"],
        max_grad_norm=ppo_kw["max_grad_norm"],
        seed=seed, device="cpu", tensorboard_log=str(tb_dir), verbose=1,
    )
    if args.resume:
        model = PPO.load(args.resume, env=train_env, tensorboard_log=str(tb_dir))
        vn_path = Path(args.resume).parent / "vecnormalize.pkl"
        if vn_path.exists():
            train_env = VecNormalize.load(str(vn_path), train_env.venv)
            model.set_env(train_env)
        print(f"resumed from {args.resume}")

    model.set_env(train_env)

    eval_cb = SyncVecNormalizeEvalCallback(
        eval_env,
        train_env=train_env,
        best_model_save_path=str(run_dir / "best"),
        n_eval_episodes=eval_cfg["n_episodes"],
        eval_freq=max(eval_cfg["freq_steps"] // n_envs, 1),
        deterministic=eval_cfg["deterministic"],
        render=False,
    )
    ckpt_cb = CheckpointCallback(
        save_freq=max(500_000 // n_envs, 1), save_path=str(run_dir),
        name_prefix="ckpt", save_vecnormalize=True,
    )
    callbacks = [eval_cb, ckpt_cb]

    t0 = time.time()
    total_done = 0
    for si, stage in enumerate(stages):
        stage_env_cfg = {**env_cfg, **stage.get("env_overrides", {})}
        train_env.venv.close()
        train_env.venv = build_vec_env(stage_env_cfg, n_envs, seed + 100 * (si + 1), not args.no_subproc)
        model.set_env(train_env)

        print(f"\n=== stage {stage['name']}: {stage['total_steps']} steps "
              f"overrides={stage.get('env_overrides', {})} ===")
        model.learn(
            total_timesteps=stage["total_steps"],
            callback=callbacks,
            reset_num_timesteps=(si == 0 and args.resume is None),
            tb_log_name=args.run_name,
            progress_bar=False,
        )
        total_done += stage["total_steps"]

        stage_dir = run_dir / stage["name"]
        stage_dir.mkdir(parents=True, exist_ok=True)
        model.save(stage_dir / "model")
        train_env.save(str(stage_dir / "vecnormalize.pkl"))
        print(f"saved {stage_dir/'model.zip'}")

    train_env.close()
    eval_env.close()
    meta = {
        "run_name": args.run_name, "n_envs": n_envs, "seed": seed,
        "total_steps": total_done, "wall_time_s": round(time.time() - t0, 1),
        "stages": [s["name"] for s in stages],
    }
    (run_dir / "train_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"\n训练完成: {meta}")


if __name__ == "__main__":
    main()
