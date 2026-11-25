# 教程实操示例脚本

全部脚本已在 `usv_rl/.venv` 环境实测通过（2026-09-30）。运行方式：

```bash
cd ~/USV/usv_rl && source .venv/bin/activate
python docs/examples/gamma_demo.py            # 第 2 章：γ 的作用
python docs/examples/reinforce_cartpole.py    # 第 3 章：裸策略梯度（约 3 分钟，慢且抖是特性）
python docs/examples/ppo_numpy.py             # 第 3 章：手写迷你 PPO（约 10 分钟，10→250+ 步）
python docs/examples/train_reach1d.py         # 第 4 章：自定义环境 + check_env + SB3
python docs/examples/dynamics_demo.py         # 第 5 章：Fossen 模型推力-速度曲线（需在 usv_rl 目录运行）
```

对应教程：`usv_rl/docs/rl_tutorial.md`
