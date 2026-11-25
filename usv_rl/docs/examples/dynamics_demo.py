import numpy as np
from usv_rl.dynamics import USVDynamicModel, HydroParams

model = USVDynamicModel(dt=0.2, rk4_substeps=4)
state = np.zeros(6)
print(" t(s) |   u(m/s) |  位置x")
for k in range(13):
    print(f"{k*0.2:4.1f} | {state[3]:7.3f} | {state[0]:7.3f}")
    state = model.forward(state, np.array([10.0, 10.0]))
