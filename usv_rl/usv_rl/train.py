"""PPO 训练入口（方案C）。

用法:
    python -m usv_rl.train --run-name v0 --total-steps 10000000
    python -m usv_rl.train --run-name v0 --stage s4_dr          # 只跑单阶段
    python -m usv_rl.train --run-name v0 --resume <artifacts>/rl_models/v0/s3_random/model.zip

结构:
- 训练环境: SubprocVecEnv(UsvTrackingEnv) + VecNormalize
- 课程: ppo.yaml curriculum 顺序执行，模型与归一化统计全程延续
- 评估: EvalCallback 定期在无 DR 环境上确定性评估，保存 best_model
- 产物: <artifacts>/rl_models/<run>/<stage>/model.zip + vecnormalize.pkl
        <artifacts>/rl_runs/<run>/ TensorBoard
        （<artifacts> 默认是仓库顶层 artifacts/，见 usv_rl.paths）
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

from usv_rl.envs import _ENV_ID, make_env_factory
from usv_rl.equivariant_policy import EquivariantActorCriticPolicy, SymmetricVecNormalize
from usv_rl.paths import RL_MODELS, RL_RUNS

ROOT = Path(__file__).resolve().parents[1]   # usv_rl/：configs 等源码资产仍在这里


def linear_schedule_fn(initial_lr: float):
    """SB3 调度接口：progress_remaining ∈ [0,1] 线性衰减到 0。"""
    def func(progress_remaining: float) -> float:
        return progress_remaining * initial_lr
    return func


def segment_linear_schedule_fn(peak_lr: float, base_steps: int, segment_steps: int):
    """续训专用线性调度：按**本段**步数归一化，不再按整个训练史归一化。

    直接复用 linear_schedule_fn 的问题是 progress_remaining 由 SB3 以
    (total_timesteps - num_timesteps)/total_timesteps 计算；续训时 num_timesteps
    已经是 1e7 量级，而本段只有 1.5e6 步，progress_remaining 起步就 ~0.87，
    peak 却按"剩余整个训练史"衰到段末 —— 实际学习率落到 1e-6 量级，等于空转。
    这里把段首映射到 peak、段末映射到 0：p0 = 段步数/(历史+段步数) 是段首的
    progress_remaining，段内线性衰减。
    """
    p0 = segment_steps / float(base_steps + segment_steps)

    def fn(progress_remaining: float) -> float:
        return float(max(0.0, min(1.0, progress_remaining / p0)) * peak_lr)

    return fn


def load_configs(config_path: str | None) -> tuple[dict, dict]:
    ppo_cfg = yaml.safe_load((ROOT / "configs" / "ppo.yaml").read_text())
    env_cfg = yaml.safe_load((ROOT / "configs" / "env.yaml").read_text())
    if config_path:
        override = yaml.safe_load(Path(config_path).read_text())
        ppo_override = dict(override.get("ppo_override", {}))
        for key in ("policy_kwargs", "fusion"):
            if key in ppo_override:
                ppo_override[key] = {**ppo_cfg.get(key, {}), **ppo_override[key]}
        ppo_cfg.update(ppo_override)
        env_cfg.update(override.get("env_override", {}))
    return ppo_cfg, env_cfg


def make_env_fn(env_cfg: dict, seed: int, fusion_cfg: dict | None = None):
    # FUSION_ENV=1 时用方案 A 的融合闭环环境（FusionTrackingEnv），否则方案C环境。
    fusion_factory = make_env_factory(dict(env_cfg), seed, fusion_cfg=fusion_cfg)
    if fusion_factory is not None:
        return fusion_factory

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
            if train_norm.norm_obs:
                self.eval_env.obs_rms = train_norm.obs_rms
            self.eval_env.ret_rms = train_norm.ret_rms
        self.eval_env.training = False
        self.eval_env.norm_reward = False
        prev_best = getattr(self, "best_mean_reward", None)
        keep_training = super()._on_step()
        new_best = getattr(self, "best_mean_reward", None)
        # best_model.zip 没有配对归一化统计就等于不可用（外部评估/导出都要它）。
        # EvalCallback 自己没有 save_vecnormalize 参数（只有 CheckpointCallback 有），
        # 所以在"最优模型刚被刷新"这一刻手动存一份。
        if (self.best_model_save_path is not None and new_best is not None
                and (prev_best is None or new_best > prev_best)):
            venv = self.model.get_vec_normalize_env()
            if venv is not None:
                Path(self.best_model_save_path).mkdir(parents=True, exist_ok=True)
                venv.save(Path(self.best_model_save_path) / "vecnormalize.pkl")
        return keep_training


def build_vec_env(env_cfg: dict, n_envs: int, base_seed: int, use_subproc: bool,
                  fusion_cfg: dict | None = None):
    fns = [make_env_fn(dict(env_cfg), base_seed + i, fusion_cfg=fusion_cfg) for i in range(n_envs)]
    if use_subproc and n_envs > 1:
        return SubprocVecEnv(fns, start_method="spawn")
    return DummyVecEnv(fns)


def resolve_device(requested: str) -> str:
    """把 auto 解析成实际 device，并对显式 cuda 做可用性前置校验。

    宁可在这里报错退出，也不要让 SB3 静默回落到 cpu —— 否则 train_meta.json
    记录的 device 与实际训练所用不一致，产物 provenance 就不可信了。
    """
    req = (requested or "cpu").strip().lower()
    if req == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if req.startswith("cuda") and not torch.cuda.is_available():
        raise SystemExit(
            f"请求 device={requested!r}，但 torch.cuda.is_available() 为 False。\n"
            f"  torch={torch.__version__} cuda_build={torch.version.cuda}\n"
            "  排查：nvidia-smi 是否能通、内核模块版本是否与用户态库一致"
            "（HWE 内核升级后需同步安装 linux-modules-nvidia-<ver>-open-<kernel>）。"
        )
    return req


def describe_device(device: str) -> dict:
    """记录到 train_meta.json 的硬件事实，便于日后复算与归因。"""
    info = {
        "device": device,
        "torch": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cuda_build": torch.version.cuda,
        "torch_threads": torch.get_num_threads(),
    }
    if device.startswith("cuda"):
        info["gpu_name"] = torch.cuda.get_device_name(0)
        info["gpu_capability"] = "sm_%d%d" % torch.cuda.get_device_capability(0)
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description="USV 方案C PPO 训练")
    parser.add_argument("--run-name", default=f"run_{time.strftime('%Y%m%d_%H%M%S')}")
    parser.add_argument("--config", default=None, help="覆盖 YAML（ppo_override/env_override）")
    parser.add_argument("--total-steps", type=int, default=None, help="覆盖课程总步数")
    parser.add_argument("--stage", default=None, help="只训练指定课程阶段")
    parser.add_argument("--n-envs", type=int, default=None)
    parser.add_argument("--resume", default=None, help="model.zip 路径（需同目录 vecnormalize.pkl）")
    parser.add_argument("--no-subproc", action="store_true")
    parser.add_argument("--device", default=None,
                        help="覆盖 ppo.yaml 的 device：cpu | cuda | auto（默认取配置，即 cpu）")
    parser.add_argument("--finetune-lr", type=float, default=None,
                        help="续训峰值学习率；仅 --resume 时有效，需单一课程阶段")
    parser.add_argument("--seed", type=int, default=None, help="覆盖 ppo.yaml 的 seed")
    args = parser.parse_args()

    ppo_cfg, env_cfg = load_configs(args.config)
    if args.n_envs:
        ppo_cfg["n_envs"] = args.n_envs
    if args.seed is not None:
        ppo_cfg["seed"] = args.seed
    n_envs = ppo_cfg["n_envs"]
    seed = ppo_cfg["seed"]
    device = resolve_device(args.device or ppo_cfg.get("device", "cpu"))
    print(f"device={device}（{describe_device(device)}）")

    run_dir = RL_MODELS / args.run_name
    tb_dir = RL_RUNS / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    stages = [s for s in ppo_cfg["curriculum"] if args.stage in (None, s["name"])]
    if args.total_steps:
        per = args.total_steps // len(stages)
        for s in stages:
            s["total_steps"] = per

    eval_cfg = ppo_cfg["eval"]
    policy_cfg = ppo_cfg.get("policy_kwargs", {})
    equivariant_z2_se2 = bool(policy_cfg.get("equivariant_z2_se2", False))
    policy_cls = EquivariantActorCriticPolicy if equivariant_z2_se2 else "MlpPolicy"
    vecnorm_cls = SymmetricVecNormalize if equivariant_z2_se2 else VecNormalize
    fusion_cfg = ppo_cfg.get("fusion")
    eval_env_cfg = dict(env_cfg)
    eval_env_cfg["path_type"] = eval_cfg["path_type"]
    eval_env = vecnorm_cls(
        DummyVecEnv([make_env_fn(eval_env_cfg, seed + 1000, fusion_cfg=fusion_cfg)]),
        training=False, norm_reward=False,
        norm_obs=ppo_cfg["vecnormalize"]["norm_obs"],
        clip_obs=ppo_cfg["vecnormalize"]["clip_obs"],
        gamma=ppo_cfg["vecnormalize"]["gamma"],
    )

    vn = ppo_cfg["vecnormalize"]
    train_env = vecnorm_cls(
        build_vec_env(env_cfg, n_envs, seed, not args.no_subproc, fusion_cfg=fusion_cfg),
        norm_obs=vn["norm_obs"], norm_reward=vn["norm_reward"],
        clip_obs=vn["clip_obs"], gamma=vn["gamma"],
    )

    activation = {
        "tanh": torch.nn.Tanh, "relu": torch.nn.ReLU,
    }[policy_cfg["activation_fn"]]
    policy_kwargs = dict(net_arch=policy_cfg["net_arch"], activation_fn=activation)
    if "log_std_init" in policy_cfg:
        policy_kwargs["log_std_init"] = float(policy_cfg["log_std_init"])
    ppo_kw = ppo_cfg["ppo"]
    lr = ppo_kw["learning_rate"]
    lr_schedule = ppo_kw.get("lr_schedule", "linear")
    schedule = linear_schedule_fn(lr) if lr_schedule == "linear" else lr

    if ppo_kw["n_steps"] * n_envs % ppo_kw["batch_size"] != 0:
        raise SystemExit(
            f"n_steps*n_envs 必须能被 batch_size 整除："
            f"{ppo_kw['n_steps']}*{n_envs} % {ppo_kw['batch_size']} != 0"
        )

    model = PPO(
        policy_cls, train_env,
        policy_kwargs=policy_kwargs,
        learning_rate=schedule,
        n_steps=ppo_kw["n_steps"], batch_size=ppo_kw["batch_size"],
        n_epochs=ppo_kw["n_epochs"], gamma=ppo_kw["gamma"],
        gae_lambda=ppo_kw["gae_lambda"], clip_range=ppo_kw["clip_range"],
        ent_coef=ppo_kw["ent_coef"], vf_coef=ppo_kw["vf_coef"],
        max_grad_norm=ppo_kw["max_grad_norm"],
        seed=seed, device=device, tensorboard_log=str(tb_dir), verbose=1,
    )
    resume_meta = None
    if args.resume:
        # 先探一次归档（不带 env，只读权重）：拿到 base_num_timesteps 才能构造
        # 按段归一化的学习率调度，并能在真正加载前校验 policy_kwargs 一致性。
        probe = PPO.load(args.resume, device=device)
        base_steps = int(probe.num_timesteps)
        archived_kw = dict(probe.policy_kwargs or {})
        archived_equivariant = probe.policy.__class__ is EquivariantActorCriticPolicy
        del probe
        if archived_equivariant != equivariant_z2_se2:
            raise SystemExit(
                f"--resume 归档的 equivariant_z2_se2={archived_equivariant} "
                f"与当前配置 equivariant_z2_se2={equivariant_z2_se2} 不一致。"
            )
        archived_act = getattr(archived_kw.get("activation_fn"), "__name__", None)
        if (archived_kw.get("net_arch") != policy_kwargs["net_arch"]
                or archived_act != policy_kwargs["activation_fn"].__name__):
            raise SystemExit(
                f"--resume 归档的 policy_kwargs={archived_kw} 与当前配置 "
                f"{{'net_arch': {policy_kwargs['net_arch']}, 'activation_fn': "
                f"{policy_kwargs['activation_fn'].__name__}}} 不一致；"
                "PPO.load 会直接拒绝，请先修正配置或换归档。"
            )

        if args.finetune_lr is not None:
            if len(stages) != 1:
                raise SystemExit(
                    f"--resume + --finetune-lr 只支持单一课程阶段（当前 {len(stages)} 个），"
                    "否则段内 progress_remaining 的起点无法确定"
                )
            segment_steps = int(stages[0]["total_steps"])
            resolved_lr = (
                segment_linear_schedule_fn(float(args.finetune_lr), base_steps, segment_steps)
                if lr_schedule == "linear" else float(args.finetune_lr)
            )
        else:
            segment_steps = int(sum(s["total_steps"] for s in stages))
            resolved_lr = schedule
        p0 = segment_steps / float(base_steps + segment_steps)

        # SB3 2.9: PPO.load 先 data 后 kwargs 更新 __dict__，再 _setup_model()，
        # 因此这里显式传的超参真正生效（不会静默沿用归档超参）。
        load_kwargs = dict(
            learning_rate=resolved_lr,
            n_steps=ppo_kw["n_steps"], batch_size=ppo_kw["batch_size"],
            n_epochs=ppo_kw["n_epochs"], gamma=ppo_kw["gamma"],
            gae_lambda=ppo_kw["gae_lambda"], clip_range=ppo_kw["clip_range"],
            ent_coef=ppo_kw["ent_coef"], vf_coef=ppo_kw["vf_coef"],
            max_grad_norm=ppo_kw["max_grad_norm"],
        )
        model = PPO.load(args.resume, env=train_env, device=device,
                         tensorboard_log=str(tb_dir), **load_kwargs)
        vn_path = Path(args.resume).parent / "vecnormalize.pkl"
        if vn_path.exists():
            train_env = VecNormalize.load(str(vn_path), train_env.venv)
            model.set_env(train_env)
        lr_obj = model.learning_rate
        effective_lr = float(lr_obj(p0)) if callable(lr_obj) else float(lr_obj)
        peak_lr = float(args.finetune_lr) if args.finetune_lr is not None else float(
            lr if lr_schedule == "linear" else model.learning_rate
        )
        print(f"resume: base_steps={base_steps} p0={p0:.4f} "
              f"effective_lr@first_update={effective_lr:.3e}")
        expected_lr = float(args.finetune_lr) if args.finetune_lr is not None else effective_lr
        assert abs(effective_lr - expected_lr) < 1e-12, (
            f"续训学习率未生效：期望 {expected_lr:.3e}，实际 {effective_lr:.3e}"
        )
        resume_meta = {
            "path": str(Path(args.resume).resolve()),
            "base_num_timesteps": base_steps,
            "peak_lr": peak_lr,
            "p0": p0,
            "effective_lr_first_update": effective_lr,
            "effective_params": {
                "n_steps": ppo_kw["n_steps"], "batch_size": ppo_kw["batch_size"],
                "gamma": ppo_kw["gamma"], "clip_range": ppo_kw["clip_range"],
                "ent_coef": ppo_kw["ent_coef"], "vf_coef": ppo_kw["vf_coef"],
                "max_grad_norm": ppo_kw["max_grad_norm"],
            },
        }

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
        train_env.venv = build_vec_env(
            stage_env_cfg, n_envs, seed + 100 * (si + 1), not args.no_subproc, fusion_cfg=fusion_cfg,
        )
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
        "run_name": args.run_name,
        "n_envs": n_envs,
        "seed": seed,
        "total_steps": total_done,
        "wall_time_s": round(time.time() - t0, 1),
        "stages": [s["name"] for s in stages],
        # --- 以下为 provenance 补全：旧版 meta 只有上面 6 个字段，
        #     不含奖励权重/课程覆盖/device，导致无法从产物反推当时配置（见评审 D18）---
        "module": "usv_rl.train",
        "device": describe_device(device),
        "stage_overrides": {
            s["name"]: s.get("env_overrides", {}) for s in stages
        },
        "stage_total_steps": {s["name"]: s["total_steps"] for s in stages},
        "config": {
            "ppo": ppo_cfg.get("ppo", {}),
            "policy_kwargs": ppo_cfg.get("policy_kwargs", {}),
            "vecnormalize": ppo_cfg.get("vecnormalize", {}),
            "eval": ppo_cfg.get("eval", {}),
        },
        "env": env_cfg,
        "fusion": ppo_cfg.get("fusion", {}),
        "resume": resume_meta,
        "cli": {
            "config": args.config, "total_steps": args.total_steps,
            "stage": args.stage, "n_envs": args.n_envs,
            "no_subproc": args.no_subproc, "resume": args.resume,
            "device": args.device,
        },
    }
    (run_dir / "train_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"\n训练完成: { {k: meta[k] for k in ('run_name', 'n_envs', 'seed', 'total_steps', 'wall_time_s')} }")


if __name__ == "__main__":
    main()
