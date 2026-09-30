from stable_baselines3 import PPO
from gymnasium.utils.env_checker import check_env
from reach1d import Reach1DEnv

check_env(Reach1DEnv(), skip_render_check=True)
env = Reach1DEnv()
model = PPO("MlpPolicy", env, n_steps=1024, batch_size=1024, verbose=0)
model.learn(total_timesteps=60_000)

for ep in range(3):
    obs, _ = env.reset(seed=100 + ep)
    done, total = False, 0.0
    while not done:
        a, _ = model.predict(obs, deterministic=True)
        obs, r, term, trunc, info = env.step(a)
        total += r
        done = term or trunc
    print(f"ep{ep}: 累计奖励 {total:.2f}, 终态 err={info['err']:.3f}")
