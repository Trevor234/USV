# 手写迷你 PPO（NumPy 单隐层，CartPole）— 对应教程第 3 章全部公式
import gymnasium as gym
import numpy as np

env = gym.make("CartPole-v1")
nS, nA, nH = 4, 2, 32
W1 = np.random.randn(nS, nH) * 0.3; b1 = np.zeros(nH)
W2 = np.random.randn(nH, nA) * 0.1; b2 = np.zeros(nA)
wv = np.random.randn(nH) * 0.1;     bv = 0.0
gamma, lam, clip_e, lr = 0.99, 0.95, 0.2, 0.02

mu, var = np.zeros(nS), np.ones(nS)
def norm(x):
    global mu, var
    mu = 0.99*mu + 0.01*x; var = 0.99*var + 0.01*(x-mu)**2
    return (x-mu)/np.sqrt(var+1e-8)

def forward(s):
    h = np.tanh(s @ W1 + b1)
    z = h @ W2 + b2
    e = np.exp(z - z.max()); p = e/e.sum()
    return h, p, h @ wv + bv

P = {"W1":W1,"b1":b1,"W2":W2,"b2":b2,"wv":wv,"bv":bv}
M = {k: np.zeros_like(x) for k,x in P.items()}
V = {k: np.zeros_like(x) for k,x in P.items()}
t_adam = 0
def adam_update(grads, lr):   # 梯度上升（价值头传负梯度即为下降）
    global t_adam, M, V
    t_adam += 1
    for k in P:
        M[k] = 0.9*M[k] + 0.1*grads[k]
        V[k] = 0.999*V[k] + 0.001*grads[k]**2
        P[k] += lr * (M[k]/(1-0.9**t_adam)) / (np.sqrt(V[k]/(1-0.999**t_adam))+1e-8)

def collect(n_steps=2048):
    B = {k: [] for k in "sapvrd"}
    s, _ = env.reset()
    for _ in range(n_steps):
        sn = norm(s)
        _, p, v = forward(sn)
        a = np.random.choice(nA, p=p)
        s2, r, term, trunc, _ = env.step(a)
        B["s"].append(sn); B["a"].append(a); B["p"].append(p[a])
        B["v"].append(v);  B["r"].append(r); B["d"].append(term)
        s = s2
        if term or trunc: s, _ = env.reset()
    return [np.array(B[k]) for k in "sapvrd"]

def gae(Vv, R, D):
    n = len(R); adv = np.zeros(n); last = 0.0
    for t in reversed(range(n)):
        v_next = 0.0 if D[t] else (Vv[t+1] if t+1 < n else Vv[t])
        delta = R[t] + gamma*v_next - Vv[t]
        adv[t] = last = delta + gamma*lam*last
    return adv, adv + Vv

for it in range(250):
    S,A,OLDP,Vv,R,D = collect()          # 每轮采新数据（标准 PPO 循环）
    ADV, RET = gae(Vv, R, D)
    ADV = (ADV - ADV.mean())/(ADV.std()+1e-8)
    for epoch in range(10):                # 同批数据重用 4 遍（clip 保证安全）
        G = {k: np.zeros_like(x) for k,x in P.items()}
        n = len(S)
        for i in range(n):
            s = S[i]
            h = np.tanh(s @ W1 + b1)
            z = h @ W2 + b2
            e = np.exp(z - z.max()); p = e/e.sum()
            v = h @ wv + bv
            rho = p[A[i]]/(OLDP[i]+1e-8)
            adv = ADV[i]
            active = (adv >= 0 and rho <= 1+clip_e) or (adv < 0 and rho >= 1-clip_e)
            coef = adv if active else 0.0
            dz = (np.eye(nA)[A[i]] - p) * coef
            dh = W2 @ dz
            G["W2"] += np.outer(h, dz); G["b2"] += dz
            dv_scalar = 2*(v - RET[i])
            dh_total = dh - dv_scalar*wv
            G["wv"] -= dv_scalar*h; G["bv"] -= dv_scalar  # 价值头直接路径取负（下降）
            G["W1"] += np.outer(s, dh_total*(1-h**2)); G["b1"] += dh_total*(1-h**2)
        for k in G: G[k] /= n
        adam_update(G, lr)
    if it % 25 == 0:
        s_, _ = env.reset(); done_, steps_ = False, 0
        while not done_ and steps_ < 500:
            _, pv, _ = forward(norm(s_))
            s_, r_, term_, trunc_, _ = env.step(np.argmax(pv))
            steps_ += 1; done_ = term_ or trunc_
        print(f"iter {it:3d}  贪心评估步数 {steps_}")
