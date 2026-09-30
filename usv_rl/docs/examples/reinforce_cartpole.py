import gymnasium as gym
import numpy as np

env = gym.make("CartPole-v1")
nS, nA = env.observation_space.shape[0], env.action_space.n

W = np.zeros((nS, nA))
v = np.zeros(nS + 1)
lr_w, lr_v, gamma = 0.1, 0.1, 0.99

# 观测运行归一化（均值/方差随采样更新）
mu, var, cnt = np.zeros(nS), np.ones(nS), 1e-4
def norm(x):
    global mu, var, cnt
    mu = 0.99 * mu + 0.01 * x
    var = 0.99 * var + 0.01 * (x - mu) ** 2
    cnt += 1
    return (x - mu) / np.sqrt(var + 1e-8)

def softmax(z):
    z = z - z.max()
    e = np.exp(z)
    return e / e.sum()

for ep in range(1000):
    lr = 0.1 * max(0.05, 1.0 - ep / 900)  # 线性衰减 0.1→0.005
    s, _ = env.reset(seed=ep)
    done, traj = False, []
    while not done:
        sn = norm(s)
        p = softmax(sn @ W)
        a = np.random.choice(nA, p=p)
        s2, r, term, trunc, _ = env.step(a)
        traj.append((sn, a, r, np.r_[sn, 1.0]))
        done = term or trunc
        s = s2

    G = np.zeros(len(traj))
    G[-1] = traj[-1][2]
    for t in range(len(traj) - 2, -1, -1):
        G[t] = traj[t][2] + gamma * G[t + 1]
    G = (G - G.mean()) / (G.std() + 1e-8)

    grad_w = np.zeros_like(W)
    grad_v = np.zeros_like(v)
    for (s_t, a_t, _, feat_t), G_t in zip(traj, G):
        p_t = softmax(s_t @ W)
        grad_logp = -np.outer(s_t, p_t)
        grad_logp[:, a_t] += s_t
        A_t = G_t - v @ feat_t
        grad_w += grad_logp * A_t
        grad_v += 2 * (v @ feat_t - G_t) * feat_t
    W += lr * grad_w / len(traj)
    v -= lr * grad_v / len(traj)

    if ep % 100 == 0 or ep == 999:
        print(f"ep {ep:4d}  步数 {len(traj):4d}")
