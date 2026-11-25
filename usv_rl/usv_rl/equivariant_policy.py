"""SE(2) invariance and port-starboard equivariance for ppo-obs-v2."""
from __future__ import annotations

import numpy as np
import torch
from gymnasium.spaces import Box
from stable_baselines3.common.distributions import DiagGaussianDistribution
from stable_baselines3.common.policies import ActorCriticPolicy
from stable_baselines3.common.running_mean_std import RunningMeanStd
from stable_baselines3.common.vec_env import VecNormalize
from stable_baselines3.common.vec_env.base_vec_env import VecEnvStepReturn


ODD_OBS_IDXS = (1, 2, 5, 8) + tuple(9 + 4 * k + 1 for k in range(8)) + tuple(
    9 + 4 * k + 2 for k in range(8)
)
SE2_MASK = np.ones(43, dtype=np.float32)
SE2_MASK[3:5] = 0.0

ACTION_SWAP_MATRIX = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float32)
Z2_PERM_MATRIX = np.eye(43, dtype=np.float32)
Z2_PERM_MATRIX[ODD_OBS_IDXS, ODD_OBS_IDXS] = -1.0
Z2_PERM_MATRIX[41:43, 41:43] = ACTION_SWAP_MATRIX


def mirror_obs_np(obs: np.ndarray) -> np.ndarray:
    """Mirror body-frame channels and swap the previous thrusts."""
    return obs @ Z2_PERM_MATRIX


def canonicalize_se2_np(obs: np.ndarray) -> np.ndarray:
    """Remove absolute heading from the observation."""
    return obs * SE2_MASK


def symmetrize_obs_rms(rms: RunningMeanStd) -> None:
    """Project normalization statistics onto the observation symmetries."""
    rms.mean[3:5] = 0.0
    rms.var[3:5] = 1.0
    rms.mean[list(ODD_OBS_IDXS)] = 0.0
    rms.mean[41:43] = rms.mean[41:43].mean()
    rms.var[41:43] = rms.var[41:43].mean()


class SymmetricVecNormalize(VecNormalize):
    """VecNormalize with reflection-symmetric running observation statistics."""

    @staticmethod
    def _update_obs_rms(obs: np.ndarray, rms: RunningMeanStd) -> None:
        if obs.shape[1:] == SE2_MASK.shape:
            rms.update(np.concatenate((obs, mirror_obs_np(obs)), axis=0))
            symmetrize_obs_rms(rms)
        else:
            # Preserve standard normalization for other fields in Dict observations.
            rms.update(obs)

    def _update_obs(self, obs: np.ndarray | dict[str, np.ndarray]) -> None:
        if self.training and self.norm_obs:
            if isinstance(obs, dict):
                for key, rms in self.obs_rms.items():
                    self._update_obs_rms(obs[key], rms)
            else:
                self._update_obs_rms(obs, self.obs_rms)

    def reset(self) -> np.ndarray | dict[str, np.ndarray]:
        obs = self.venv.reset()
        self.old_obs = obs
        self.returns = np.zeros(self.num_envs)
        self._update_obs(obs)
        return self.normalize_obs(obs)

    def step_wait(self) -> VecEnvStepReturn:
        obs, rewards, dones, infos = self.venv.step_wait()
        self.old_obs = obs
        self.old_reward = rewards
        self._update_obs(obs)
        obs = self.normalize_obs(obs)

        if self.training:
            self._update_reward(rewards)
        rewards = self.normalize_reward(rewards)

        for idx, done in enumerate(dones):
            if done and "terminal_observation" in infos[idx]:
                infos[idx]["terminal_observation"] = self.normalize_obs(infos[idx]["terminal_observation"])
        self.returns[dones] = 0.0
        return obs, rewards, dones, infos


class EquivariantActorCriticPolicy(ActorCriticPolicy):
    """Average a diagonal Gaussian policy and critic over the reflection group."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not isinstance(self.observation_space, Box) or self.observation_space.shape != SE2_MASK.shape:
            raise ValueError("EquivariantActorCriticPolicy requires the ppo-obs-v2 Box(43)")
        if not isinstance(self.action_dist, DiagGaussianDistribution) or self.action_space.shape != (2,):
            raise ValueError("EquivariantActorCriticPolicy requires a two-action diagonal Gaussian (use_sde=False)")
        self.register_buffer("se2_mask", torch.tensor(SE2_MASK))
        self.register_buffer("z2_perm_mat", torch.tensor(Z2_PERM_MATRIX))
        self.register_buffer("action_swap_mat", torch.tensor(ACTION_SWAP_MATRIX))

    def _sym_log_std(self) -> torch.Tensor:
        return 0.5 * (self.log_std + self.log_std @ self.action_swap_mat)

    def _equivariant_latent(self, obs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        obs_c = obs * self.se2_mask
        obs_m = obs_c @ self.z2_perm_mat
        features = self.extract_features(torch.cat((obs_c, obs_m), dim=0))
        if self.share_features_extractor:
            latent_pi, latent_vf = self.mlp_extractor(features)
        else:
            pi_features, vf_features = features
            latent_pi = self.mlp_extractor.forward_actor(pi_features)
            latent_vf = self.mlp_extractor.forward_critic(vf_features)

        mean_c, mean_m = self.action_net(latent_pi).chunk(2, dim=0)
        value_c, value_m = self.value_net(latent_vf).chunk(2, dim=0)
        mean_actions = 0.5 * (mean_c + mean_m @ self.action_swap_mat)
        values = 0.5 * (value_c + value_m)
        return mean_actions, values

    def forward(
        self, obs: torch.Tensor, deterministic: bool = False,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        mean_actions, values = self._equivariant_latent(obs)
        dist = self.action_dist.proba_distribution(mean_actions, self._sym_log_std())
        actions = dist.get_actions(deterministic=deterministic)
        return actions.reshape(-1, *self.action_space.shape), values, dist.log_prob(actions)

    def _predict(self, observation: torch.Tensor, deterministic: bool = False) -> torch.Tensor:
        return self.get_distribution(observation).get_actions(deterministic=deterministic)

    def evaluate_actions(
        self, obs: torch.Tensor, actions: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        mean_actions, values = self._equivariant_latent(obs)
        dist = self.action_dist.proba_distribution(mean_actions, self._sym_log_std())
        return values, dist.log_prob(actions), dist.entropy()

    def get_distribution(self, obs: torch.Tensor) -> DiagGaussianDistribution:
        mean_actions, _ = self._equivariant_latent(obs)
        return self.action_dist.proba_distribution(mean_actions, self._sym_log_std())

    def predict_values(self, obs: torch.Tensor) -> torch.Tensor:
        _, values = self._equivariant_latent(obs)
        return values
