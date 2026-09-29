"""策略导出 ONNX — 部署侧 rl_policy_node 的推理资产。

把 SB3 PPO 策略 + VecNormalize 观测归一化折叠成单个 ONNX 图：
    输入  raw_obs (float32, 43 维)   ← rl_policy_node 直接喂原始观测
    输出  thrust [T_L, T_R] (float32, 2 维, 已映射到 ±25 N 物理量纲)

内部: obs → (obs-mean)/sqrt(var+eps) → clip(±clip_obs) → MLP → 高斯均值
      → clip(±1) → 反缩放到动作空间（确定性推理，不采样）。

用法:
    python -m usv_rl.export_policy --model models/v1/best/best_model.zip \
        --vecnorm models/v1/best/vecnormalize.pkl --out models/v1/policy.onnx
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn


class DeterministicActor(nn.Module):
    """SB3 PPO 策略 + VecNormalize 观测归一化 + 动作反缩放的单图封装。"""

    def __init__(self, policy, obs_mean, obs_var, act_low, act_high,
                 clip_obs: float = 10.0, eps: float = 1e-8) -> None:
        super().__init__()
        # policy_net (含激活) + action_net（单层 Linear→均值头；无子模块，须整层加入）
        layers = list(policy.mlp_extractor.policy_net.children()) + [policy.action_net]
        self.net = nn.Sequential(*layers)
        self.register_buffer("obs_mean", torch.as_tensor(obs_mean, dtype=torch.float32))
        self.register_buffer("obs_var", torch.as_tensor(obs_var, dtype=torch.float32))
        self.register_buffer("act_low", torch.as_tensor(act_low, dtype=torch.float32))
        self.register_buffer("act_high", torch.as_tensor(act_high, dtype=torch.float32))
        self.clip_obs = clip_obs
        self.eps = eps

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        norm = (obs - self.obs_mean) / torch.sqrt(self.obs_var + self.eps)
        norm = torch.clamp(norm, -self.clip_obs, self.clip_obs)
        mean = self.net(norm)
        # 动作空间归一化 [-1,1]：SB3 predict 输出 clip 后的归一化动作，
        # 这里折叠反缩放，使 ONNX 直接输出物理推力 N
        a01 = torch.clamp(mean, -1.0, 1.0)
        return self.act_low + (a01 + 1.0) * 0.5 * (self.act_high - self.act_low)


def export(model_path: str, vecnorm_path: str, out_path: str, opset: int = 13) -> Path:
    from stable_baselines3 import PPO

    model = PPO.load(model_path, device="cpu")
    policy = model.policy
    policy.eval()

    vn_path = Path(vecnorm_path)
    if vn_path.exists():
        import pickle
        with open(vn_path, "rb") as f:
            vn = pickle.load(f)
        obs_mean = np.asarray(vn.obs_rms.mean, dtype=np.float64)
        obs_var = np.asarray(vn.obs_rms.var, dtype=np.float64)
        clip_obs = float(vn.clip_obs)
    else:
        print(f"警告: {vn_path} 不存在，导出图将不含观测归一化（推理侧需自行归一化）")
        obs_space = model.observation_space
        obs_mean = np.zeros(obs_space.shape, dtype=np.float64)
        obs_var = np.ones(obs_space.shape, dtype=np.float64)
        clip_obs = 1e9

    act_low = np.asarray(model.action_space.low, dtype=np.float32)
    act_high = np.asarray(model.action_space.high, dtype=np.float32)

    actor = DeterministicActor(
        policy, obs_mean, obs_var, act_low, act_high, clip_obs=clip_obs
    )
    actor.eval()

    obs_dim = int(np.prod(model.observation_space.shape))
    dummy = torch.zeros(1, obs_dim, dtype=torch.float32)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        actor, dummy, str(out),
        input_names=["obs"], output_names=["thrust"],
        dynamic_axes={"obs": {0: "batch"}, "thrust": {0: "batch"}},
        opset_version=opset, do_constant_folding=True,
        dynamo=False,  # torch>=2.9 默认 dynamo 导出器，对 Sequential+buffer 折叠不稳定
    )
    _verify(actor, model, out, obs_dim, act_low, act_high)
    return out


def _verify(actor, sb3_model, out: Path, obs_dim: int, act_low, act_high) -> None:
    """导出后用 onnxruntime 与 SB3 predict 对拍（确定性模式）。"""
    import onnxruntime as ort

    sess = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(0)
    max_diff = 0.0
    for _ in range(64):
        raw = rng.normal(0, 2.0, (1, obs_dim)).astype(np.float32)
        onnx_out = sess.run(["thrust"], {"obs": raw})[0]

        # SB3 参考路径：手动归一化 → predict(deterministic=mean) → clip 后反缩放
        norm = np.clip(
            (raw - actor.obs_mean.numpy()) / np.sqrt(actor.obs_var.numpy() + 1e-8),
            -actor.clip_obs, actor.clip_obs,
        ).astype(np.float32)
        a01 = np.clip(sb3_model.predict(norm, deterministic=True)[0], -1.0, 1.0)
        torch_act = act_low + (a01 + 1.0) * 0.5 * (act_high - act_low)
        max_diff = max(max_diff, float(np.max(np.abs(onnx_out - torch_act))))
    print(f"ONNX 导出完成: {out}  (与 SB3 predict 最大差 {max_diff:.2e} N)")
    assert max_diff < 1e-3, f"ONNX 与 SB3 推理不一致: {max_diff}"


def main() -> None:
    parser = argparse.ArgumentParser(description="PPO 策略导出 ONNX（部署用）")
    parser.add_argument("--model", required=True)
    parser.add_argument("--vecnorm", default=None,
                        help="vecnormalize.pkl（默认取 model 同目录）")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    model_path = Path(args.model)
    vecnorm = args.vecnorm or str(model_path.parent / "vecnormalize.pkl")
    out = args.out or str(model_path.parent / "policy.onnx")
    export(str(model_path), vecnorm, out)


if __name__ == "__main__":
    main()
