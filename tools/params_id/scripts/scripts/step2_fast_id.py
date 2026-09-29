#!/usr/bin/env python3
"""
Fast Parameter Identification for Fossen 3-DOF Model
====================================================
Uses simple linear regression on acceleration data to find parameters quickly.
Outputs results in ROS2 YAML format for MPC node.
"""

import os
import json
import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear

# Known boat parameters
BOAT_MASS = 14.2         # kg
BOAT_LENGTH = 1.2        # m
BOAT_WIDTH = 0.6         # m
CG_FROM_STERN = 0.48     # m
X_G = BOAT_LENGTH / 2 - CG_FROM_STERN  # 0.12 m
IZ_INIT = (1.0 / 12.0) * BOAT_MASS * (BOAT_LENGTH**2 + BOAT_WIDTH**2)

# Assume reasonable actuator bounds for mapping PWM to force
# You can tweak these later in your MPC yaml
MAX_THRUST_N = 25.0      # N per motor
THRUSTER_SEP = 0.5       # m


def pwm_to_normalized(pwm, deadzone=30):
    pwm = np.asarray(pwm, dtype=float)
    n = np.zeros_like(pwm)
    fwd = pwm > (1500 + deadzone)
    n[fwd] = (pwm[fwd] - 1500 - deadzone) / (500 - deadzone)
    rev = pwm < (1500 - deadzone)
    n[rev] = (pwm[rev] - 1500 + deadzone) / (500 - deadzone)
    return np.clip(n, -1.0, 1.0)


def fast_identify(data_path, results_dir):
    print("Loading data...")
    df = pd.read_csv(data_path)
    
    # Filter moving data
    df = df[df['gps_speed'] > 0.2].copy()
    
    # Calculate forces based on assumed thruster model
    n_left = pwm_to_normalized(df['pwm_left'].values)
    n_right = pwm_to_normalized(df['pwm_right'].values)
    
    T_left = MAX_THRUST_N * np.sign(n_left) * n_left**2
    T_right = MAX_THRUST_N * np.sign(n_right) * n_right**2
    
    tau_X = T_left + T_right
    tau_N = (T_right - T_left) * THRUSTER_SEP / 2.0
    
    u, v, r = df['u'].values, df['v'].values, df['r'].values
    u_dot, v_dot, r_dot = df['u_dot'].values, df['v_dot'].values, df['r_dot'].values
    m, xg = BOAT_MASS, X_G
    
    print("Running linear regressions...")
    
    # --- SURGE EQUATION ---
    # m*u_dot - m*v*r - m*xg*r^2 = tau_X - Xud*u_dot - Xu*u - Xuu*|u|u + Yvd*v*r
    # We rearrange to solve for: [Xud, Xu, Xuu, Yvd] (Note: Yvd appears in Coriolis)
    # y_surge = tau_X - m*u_dot + m*v*r + m*xg*r^2
    y_surge = tau_X - m*u_dot + m*v*r + m*xg*r**2
    A_surge = np.column_stack([
        u_dot,            # for -Xud
        u,                # for -Xu
        np.abs(u)*u,      # for -Xuu
        -v*r              # for -Yvd (Coriolis term)
    ])
    
    # Bounds: Xud>0, Xu<0, Xuu<0, Yvd>0.  So -Xud<0, -Xu>0, -Xuu>0, -Yvd<0
    lb_surge = [-20, 0.1, 0.1, -30]
    ub_surge = [-0.1, 30, 50, -0.1]
    res_surge = lsq_linear(A_surge, y_surge, bounds=(lb_surge, ub_surge))
    
    Xud = -res_surge.x[0]
    Xu = -res_surge.x[1]
    Xuu = -res_surge.x[2]
    Yvd = -res_surge.x[3]
    
    # --- SWAY EQUATION ---
    # m*v_dot + m*xg*r_dot + m*u*r = 0 - Yvd*v_dot - Yv*v - Yvv*|v|v - Yr*r + Xud*u*r
    # Since tau_Y = 0, y_sway = - m*v_dot - m*xg*r_dot - m*u*r + Xud*u*r
    y_sway = - m*v_dot - m*xg*r_dot - m*u*r + Xud*u*r
    A_sway = np.column_stack([
        v_dot,            # for Yvd (we already have it, but let's see if it matches, or we just constrain it)
        v,                # for Yv
        np.abs(v)*v,      # for Yvv
        r                 # for Yr
    ])
    
    lb_sway = [Yvd*0.9, 0.1, 0.1, -10]
    ub_sway = [Yvd*1.1, 50, 100, 10]
    res_sway = lsq_linear(A_sway, y_sway, bounds=(lb_sway, ub_sway))
    Yv = -res_sway.x[1]
    Yvv = -res_sway.x[2]
    Yr = -res_sway.x[3]
    
    # --- YAW EQUATION ---
    # m*xg*v_dot + Iz*r_dot + m*xg*u*r = tau_N - Nrd*r_dot - Nr*r - Nrr*|r|r - Nv*v - (Xud-Yvd)*u*v
    y_yaw = tau_N - m*xg*v_dot - m*xg*u*r - (Xud-Yvd)*u*v
    A_yaw = np.column_stack([
        r_dot,            # for -(Iz+Nrd)
        r,                # for -Nr
        np.abs(r)*r,      # for -Nrr
        v                 # for -Nv
    ])
    
    lb_yaw = [-20, 0.01, 0.01, -10]
    ub_yaw = [-0.1, 20, 30, 10]
    res_yaw = lsq_linear(A_yaw, y_yaw, bounds=(lb_yaw, ub_yaw))
    
    Iz_plus_Nrd = -res_yaw.x[0]
    Iz = IZ_INIT
    Nrd = max(0.1, Iz_plus_Nrd - Iz)
    Nr = -res_yaw.x[1]
    Nrr = -res_yaw.x[2]
    Nv = -res_yaw.x[3]
    
    # Store parameters
    params = {
        'mass': BOAT_MASS, 'length': BOAT_LENGTH, 'width': BOAT_WIDTH,
        'x_g': X_G, 'Iz': float(Iz),
        'Xud': float(Xud), 'Yvd': float(Yvd), 'Nrd': float(Nrd),
        'Xu': float(Xu), 'Yv': float(Yv), 'Nr': float(Nr),
        'Xuu': float(Xuu), 'Yvv': float(Yvv), 'Nrr': float(Nrr),
        'Yr': float(Yr), 'Nv': float(Nv),
        'K_T': MAX_THRUST_N, 'd_T': THRUSTER_SEP
    }
    
    print("\nIdentified Parameters:")
    for k, v in params.items():
        print(f"  {k}: {v:.4f}")
    
    # Save to JSON
    with open(os.path.join(results_dir, 'identified_params.json'), 'w') as f:
        json.dump(params, f, indent=2)
        
    # Save to ROS2 YAML format
    yaml_path = os.path.join(results_dir, 'usv_params.yaml')
    with open(yaml_path, 'w') as f:
        f.write("/**:\n")
        f.write("  ros__parameters:\n")
        f.write("    # --- Vessel Physical Parameters ---\n")
        f.write(f"    mass: {BOAT_MASS}\n")
        f.write(f"    length: {BOAT_LENGTH}\n")
        f.write(f"    width: {BOAT_WIDTH}\n")
        f.write(f"    x_g: {X_G}\n")
        f.write(f"    Iz: {Iz:.4f}\n\n")
        
        f.write("    # --- Hydrodynamic Parameters (Fossen) ---\n")
        f.write("    # Added mass (M_total = M_rb + M_a)\n")
        f.write(f"    Xud: {Xud:.4f}\n")
        f.write(f"    Yvd: {Yvd:.4f}\n")
        f.write(f"    Nrd: {Nrd:.4f}\n\n")
        
        f.write("    # Linear damping (negative convention)\n")
        f.write(f"    Xu: {Xu:.4f}\n")
        f.write(f"    Yv: {Yv:.4f}\n")
        f.write(f"    Nr: {Nr:.4f}\n")
        f.write(f"    Yr: {Yr:.4f}\n")
        f.write(f"    Nv: {Nv:.4f}\n\n")
        
        f.write("    # Nonlinear damping (negative convention)\n")
        f.write(f"    Xuu: {Xuu:.4f}\n")
        f.write(f"    Yvv: {Yvv:.4f}\n")
        f.write(f"    Nrr: {Nrr:.4f}\n\n")
        
        f.write("    # --- Actuator Mapping ---\n")
        f.write(f"    K_T: {MAX_THRUST_N:.1f}      # Max thrust per motor (N)\n")
        f.write(f"    d_T: {THRUSTER_SEP:.2f}       # Thruster separation (m)\n")
        f.write("    pwm_deadzone: 30\n")
        
    print(f"\n[OK] Saved fast identified parameters to {yaml_path}")


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(script_dir)
    fast_identify(
        os.path.join(base_dir, 'data', 'processed_data.csv'),
        os.path.join(base_dir, 'results')
    )
