#!/usr/bin/env python3
"""
Stage 2 (Improved): Fossen 3-DOF Model Parameter Identification
================================================================
Key improvements over v1:
  1. Thrust coefficient (K_thrust) as identifiable parameter
  2. Thruster separation (d) as identifiable parameter  
  3. Filters out stationary periods (GPS speed < 0.15 m/s)
  4. Uses differential evolution (global) + local refinement
  5. Wider parameter bounds
  6. Separate surge-only and coupled identification
  7. Simulation-based cost (integrates ODE, compares trajectory)
"""

import os
import json
import numpy as np
import pandas as pd
from scipy.optimize import least_squares, differential_evolution
from scipy.signal import butter, filtfilt
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ============================================================
# Known boat parameters
# ============================================================
BOAT_MASS = 14.2         # kg
BOAT_LENGTH = 1.2        # m
BOAT_WIDTH = 0.6         # m
CG_FROM_STERN = 0.48     # m
X_G = BOAT_LENGTH / 2 - CG_FROM_STERN  # 0.12 m forward of midship

# Rough Iz estimate (rectangular body)
IZ_INIT = (1.0 / 12.0) * BOAT_MASS * (BOAT_LENGTH**2 + BOAT_WIDTH**2)  # ~2.13


def pwm_to_normalized(pwm, deadzone=30):
    """
    Convert PWM (us) to normalized input [-1, 1].
    Handles deadzone around neutral (1500).
    """
    pwm = np.asarray(pwm, dtype=float)
    n = np.zeros_like(pwm)
    
    # Forward
    fwd = pwm > (1500 + deadzone)
    n[fwd] = (pwm[fwd] - 1500 - deadzone) / (500 - deadzone)
    
    # Reverse
    rev = pwm < (1500 - deadzone)
    n[rev] = (pwm[rev] - 1500 + deadzone) / (500 - deadzone)
    
    return np.clip(n, -1.0, 1.0)


class FossenModel:
    """Fossen 3-DOF model with parameterized thrust."""
    
    def __init__(self, theta):
        """
        theta: parameter dict with keys:
          Hydrodynamic: Xu, Yv, Nr, Xuu, Yvv, Nrr, Yr, Nv
          Added mass: Xud, Yvd, Nrd
          Thrust: K_T (thrust coefficient), d_T (thruster separation)
          Inertia: Iz
        """
        self.m = BOAT_MASS
        self.xg = X_G
        self.theta = theta
        
        Iz = theta['Iz']
        Xud = theta['Xud']
        Yvd = theta['Yvd']
        Nrd = theta['Nrd']
        
        # Mass matrix (simplified: ignore off-diagonal added mass for robustness)
        self.M = np.array([
            [self.m + Xud, 0,              0],
            [0,            self.m + Yvd,    self.m * self.xg],
            [0,            self.m * self.xg, Iz + Nrd]
        ])
        self.M_inv = np.linalg.inv(self.M)
    
    def forces(self, nu, n_left, n_right):
        """
        Compute total forces: tau - C(nu)*nu - D(nu)*nu
        
        nu: [u, v, r]
        n_left, n_right: normalized thruster inputs [-1, 1]
        """
        u, v, r = nu
        th = self.theta
        
        # Thrust model: T = K_T * |n| * n  (quadratic in normalized input)
        K_T = th['K_T']
        d_T = th['d_T']
        
        T_left = K_T * np.sign(n_left) * n_left**2
        T_right = K_T * np.sign(n_right) * n_right**2
        
        tau_X = T_left + T_right
        tau_Y = 0.0
        tau_N = (T_right - T_left) * d_T / 2.0
        
        # Damping: D(nu) * nu
        Xu = th['Xu']
        Yv = th['Yv']
        Nr = th['Nr']
        Xuu = th['Xuu']
        Yvv = th['Yvv']
        Nrr = th['Nrr']
        Yr = th['Yr']
        Nv = th['Nv']
        
        damp_X = Xu * u + Xuu * abs(u) * u
        damp_Y = Yv * v + Yvv * abs(v) * v + Yr * r
        damp_N = Nr * r + Nrr * abs(r) * r + Nv * v
        
        # Coriolis (simplified for small boat)
        m = self.m
        xg = self.xg
        Xud = th['Xud']
        Yvd = th['Yvd']
        
        cor_X = -m * v * r - m * xg * r**2 + Yvd * v * r
        cor_Y = m * u * r - Xud * u * r
        cor_N = m * xg * u * r + (Xud - Yvd) * u * v
        
        # RHS = tau - D*nu - C*nu
        fx = tau_X - damp_X - cor_X
        fy = tau_Y - damp_Y - cor_Y
        fn = tau_N - damp_N - cor_N
        
        return np.array([fx, fy, fn])
    
    def dynamics(self, nu, n_left, n_right):
        """Compute nu_dot = M^-1 * forces"""
        f = self.forces(nu, n_left, n_right)
        return self.M_inv @ f
    
    def simulate(self, nu0, n_left_seq, n_right_seq, dt):
        """
        Open-loop simulation.
        
        nu0: initial [u, v, r]
        n_left_seq, n_right_seq: (N,) normalized inputs
        dt: time step
        
        Returns: (N+1, 3) velocity trajectory
        """
        N = len(n_left_seq)
        nu_traj = np.zeros((N + 1, 3))
        nu_traj[0] = nu0
        
        nu = nu0.copy()
        for i in range(N):
            # RK4
            k1 = self.dynamics(nu, n_left_seq[i], n_right_seq[i])
            k2 = self.dynamics(nu + 0.5*dt*k1, n_left_seq[i], n_right_seq[i])
            k3 = self.dynamics(nu + 0.5*dt*k2, n_left_seq[i], n_right_seq[i])
            k4 = self.dynamics(nu + dt*k3, n_left_seq[i], n_right_seq[i])
            nu = nu + (dt/6.0) * (k1 + 2*k2 + 2*k3 + k4)
            nu_traj[i+1] = nu
        
        return nu_traj


# ============================================================
# Parameter vector <-> dict conversion
# ============================================================
PARAM_NAMES = [
    'Xu', 'Yv', 'Nr',        # Linear damping (negative values expected)
    'Xuu', 'Yvv', 'Nrr',     # Nonlinear damping
    'Yr', 'Nv',               # Coupled damping
    'Xud', 'Yvd', 'Nrd',     # Added mass (positive convention here: M = m + Xud)
    'K_T',                    # Thrust coefficient (N per unit n^2)
    'd_T',                    # Thruster separation (m)
    'Iz',                     # Moment of inertia
]

# Bounds: (lower, upper)
PARAM_BOUNDS = {
    'Xu':  (-30, -0.1),     # Linear surge damping
    'Yv':  (-60, -0.1),     # Linear sway damping
    'Nr':  (-20, -0.01),    # Linear yaw damping
    'Xuu': (-50, -0.01),    # Nonlinear surge damping
    'Yvv': (-100, -0.01),   # Nonlinear sway damping
    'Nrr': (-20, -0.001),   # Nonlinear yaw damping
    'Yr':  (-10, 10),       # Sway-yaw coupling
    'Nv':  (-10, 10),       # Yaw-sway coupling
    'Xud': (0.1, 30),       # Added mass surge (positive)
    'Yvd': (0.5, 50),       # Added mass sway
    'Nrd': (0.05, 15),      # Added mass yaw
    'K_T': (1, 80),         # Thrust coefficient
    'd_T': (0.2, 0.8),      # Thruster separation
    'Iz':  (0.3, 8.0),      # Moment of inertia
}

PARAM_X0 = {
    'Xu': -5.0, 'Yv': -15.0, 'Nr': -3.0,
    'Xuu': -8.0, 'Yvv': -20.0, 'Nrr': -2.0,
    'Yr': -0.5, 'Nv': -0.5,
    'Xud': 2.0, 'Yvd': 10.0, 'Nrd': 1.5,
    'K_T': 20.0, 'd_T': 0.5, 'Iz': IZ_INIT,
}


def dict_to_vec(d):
    return np.array([d[k] for k in PARAM_NAMES])

def vec_to_dict(x):
    return {k: float(v) for k, v in zip(PARAM_NAMES, x)}

def get_bounds_arrays():
    lb = np.array([PARAM_BOUNDS[k][0] for k in PARAM_NAMES])
    ub = np.array([PARAM_BOUNDS[k][1] for k in PARAM_NAMES])
    return lb, ub

def get_bounds_list():
    return [PARAM_BOUNDS[k] for k in PARAM_NAMES]


# ============================================================
# Identification
# ============================================================
def prepare_segments(data, seg_len=50, min_speed=0.15, dt=0.1):
    """
    Extract data segments suitable for identification.
    
    Criteria:
      - GPS speed > min_speed (not stationary)
      - Thrust is active for at least part of the segment
      - No NaN in key fields
    """
    required = ['u', 'v', 'r', 'pwm_left', 'pwm_right', 'gps_speed']
    valid = data.dropna(subset=required).copy()
    
    # Convert PWM to normalized input
    valid['n_left'] = pwm_to_normalized(valid['pwm_left'].values)
    valid['n_right'] = pwm_to_normalized(valid['pwm_right'].values)
    
    # Filter: moving & thrust active
    moving = valid['gps_speed'] > min_speed
    thrust_active = (valid['n_left'].abs() > 0.02) | (valid['n_right'].abs() > 0.02)
    
    # Find contiguous segments where both conditions are met
    active = moving & thrust_active
    segments = []
    
    i = 0
    while i < len(valid):
        if active.iloc[i]:
            j = i
            while j < len(valid) and j - i < seg_len * 3:
                if not active.iloc[j]:
                    break
                j += 1
            
            seg = valid.iloc[i:j]
            if len(seg) >= seg_len:
                # Take the first seg_len points
                segments.append(seg.iloc[:seg_len].copy())
            i = j
        else:
            i += 1
    
    print(f"  Found {len(segments)} valid segments of length {seg_len}")
    return segments


def segment_cost(theta_dict, seg, dt):
    """
    Cost for a single segment: simulate and compare with actual velocities.
    """
    try:
        model = FossenModel(theta_dict)
    except (np.linalg.LinAlgError, ValueError):
        return 1e6
    
    nu0 = np.array([seg['u'].iloc[0], seg['v'].iloc[0], seg['r'].iloc[0]])
    n_left = seg['n_left'].values
    n_right = seg['n_right'].values
    
    try:
        nu_sim = model.simulate(nu0, n_left[:-1], n_right[:-1], dt)
    except (FloatingPointError, OverflowError, ValueError):
        return 1e6
    
    # Compare simulated vs actual velocities
    u_actual = seg['u'].values
    v_actual = seg['v'].values
    r_actual = seg['r'].values
    
    N = min(len(nu_sim), len(u_actual))
    
    err_u = nu_sim[:N, 0] - u_actual[:N]
    err_v = nu_sim[:N, 1] - v_actual[:N]
    err_r = nu_sim[:N, 2] - r_actual[:N]
    
    # Check for NaN/Inf
    if np.any(np.isnan(nu_sim)) or np.any(np.isinf(nu_sim)):
        return 1e6
    
    # Weighted MSE (surge is most important, yaw rate second)
    cost = np.mean(err_u**2) * 3.0 + np.mean(err_v**2) * 1.0 + np.mean(err_r**2) * 2.0
    return cost


def total_cost_vec(x, segments, dt):
    """Cost function for optimization (vector input)."""
    theta = vec_to_dict(x)
    
    total = 0
    n_valid = 0
    for seg in segments:
        c = segment_cost(theta, seg, dt)
        if c < 1e5:
            total += c
            n_valid += 1
    
    if n_valid == 0:
        return 1e6
    
    return total / n_valid


def total_cost_residuals(x, segments, dt):
    """Residual vector for least_squares (simulation-based)."""
    theta = vec_to_dict(x)
    
    all_residuals = []
    for seg in segments:
        try:
            model = FossenModel(theta)
        except (np.linalg.LinAlgError, ValueError):
            all_residuals.extend([100.0] * len(seg) * 3)
            continue
        
        nu0 = np.array([seg['u'].iloc[0], seg['v'].iloc[0], seg['r'].iloc[0]])
        n_left = seg['n_left'].values
        n_right = seg['n_right'].values
        
        try:
            nu_sim = model.simulate(nu0, n_left[:-1], n_right[:-1], dt)
        except (FloatingPointError, OverflowError, ValueError):
            all_residuals.extend([100.0] * len(seg) * 3)
            continue
        
        N = min(len(nu_sim), len(seg))
        
        u_actual = seg['u'].values[:N]
        v_actual = seg['v'].values[:N]
        r_actual = seg['r'].values[:N]
        
        err_u = (nu_sim[:N, 0] - u_actual) * np.sqrt(3.0)
        err_v = (nu_sim[:N, 1] - v_actual) * 1.0
        err_r = (nu_sim[:N, 2] - r_actual) * np.sqrt(2.0)
        
        if np.any(np.isnan(err_u)) or np.any(np.isinf(err_u)):
            all_residuals.extend([100.0] * N * 3)
            continue
        
        all_residuals.extend(err_u.tolist())
        all_residuals.extend(err_v.tolist())
        all_residuals.extend(err_r.tolist())
    
    return np.array(all_residuals)


def identify(data, dt=0.1):
    """Main identification routine."""
    print("\n" + "=" * 60)
    print("Fossen 3-DOF Identification (Improved)")
    print("=" * 60)
    
    # Prepare segments
    segments = prepare_segments(data, seg_len=50, min_speed=0.15, dt=dt)
    
    if len(segments) < 5:
        print("WARNING: Too few valid segments. Trying with lower speed threshold...")
        segments = prepare_segments(data, seg_len=30, min_speed=0.05, dt=dt)
    
    if len(segments) == 0:
        print("ERROR: No valid segments found!")
        return None
    
    # Use subset for speed (max 100 segments)
    if len(segments) > 100:
        np.random.seed(42)
        idx = np.random.choice(len(segments), 100, replace=False)
        segments = [segments[i] for i in sorted(idx)]
        print(f"  Using {len(segments)} random segments for identification")
    
    # ---- Step 1: Global optimization with differential evolution ----
    print("\n--- Step 1: Global Search (Differential Evolution) ---")
    bounds = get_bounds_list()
    
    result_de = differential_evolution(
        total_cost_vec,
        bounds,
        args=(segments, dt),
        maxiter=150,
        popsize=20,
        tol=1e-6,
        seed=42,
        disp=True,
        polish=False,  # We'll do local refinement next
        workers=1,
    )
    
    print(f"  DE result: cost={result_de.fun:.6f}, success={result_de.success}")
    x_global = result_de.x
    
    # ---- Step 2: Local refinement with least_squares ----
    print("\n--- Step 2: Local Refinement (Least Squares) ---")
    lb, ub = get_bounds_arrays()
    
    result_ls = least_squares(
        total_cost_residuals,
        x_global,
        args=(segments, dt),
        bounds=(lb, ub),
        method='trf',
        verbose=1,
        max_nfev=3000,
        ftol=1e-10,
        xtol=1e-10,
    )
    
    x_final = result_ls.x
    theta_final = vec_to_dict(x_final)
    
    # ---- Print results ----
    print("\n" + "=" * 60)
    print("IDENTIFICATION RESULTS")
    print("=" * 60)
    
    print(f"\n  {'Parameter':<10s} {'Value':>12s} {'Bounds':>20s}")
    print(f"  {'-'*48}")
    for k in PARAM_NAMES:
        v = theta_final[k]
        lo, hi = PARAM_BOUNDS[k]
        at_bound = '*' if abs(v - lo) < 0.01 * abs(lo) or abs(v - hi) < 0.01 * abs(hi) else ' '
        print(f"  {k:<10s} {v:>12.4f}   [{lo:>8.2f}, {hi:>8.2f}] {at_bound}")
    
    # ---- Evaluate accuracy ----
    print("\n--- Model Accuracy ---")
    model = FossenModel(theta_final)
    
    total_err_u, total_err_v, total_err_r = [], [], []
    total_actual_u, total_actual_v, total_actual_r = [], [], []
    
    for seg in segments:
        nu0 = np.array([seg['u'].iloc[0], seg['v'].iloc[0], seg['r'].iloc[0]])
        n_left = seg['n_left'].values
        n_right = seg['n_right'].values
        
        try:
            nu_sim = model.simulate(nu0, n_left[:-1], n_right[:-1], dt)
        except Exception:
            continue
        
        N = min(len(nu_sim), len(seg))
        total_err_u.extend((nu_sim[:N, 0] - seg['u'].values[:N]).tolist())
        total_err_v.extend((nu_sim[:N, 1] - seg['v'].values[:N]).tolist())
        total_err_r.extend((nu_sim[:N, 2] - seg['r'].values[:N]).tolist())
        total_actual_u.extend(seg['u'].values[:N].tolist())
        total_actual_v.extend(seg['v'].values[:N].tolist())
        total_actual_r.extend(seg['r'].values[:N].tolist())
    
    for name, err, actual in [
        ('u (surge vel)', total_err_u, total_actual_u),
        ('v (sway vel)', total_err_v, total_actual_v),
        ('r (yaw rate)', total_err_r, total_actual_r),
    ]:
        err = np.array(err)
        actual = np.array(actual)
        rmse = np.sqrt(np.mean(err**2))
        ss_res = np.sum(err**2)
        ss_tot = np.sum((actual - actual.mean())**2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 1e-10 else 0
        print(f"  {name:<16s}: RMSE={rmse:.4f}, R^2={r2:.4f}")
    
    # ---- Mass matrix ----
    print(f"\n  Mass matrix M:")
    for row in model.M:
        print(f"    [{row[0]:>10.4f}, {row[1]:>10.4f}, {row[2]:>10.4f}]")
    
    # ---- Derived quantities ----
    print(f"\n  Thrust model:")
    print(f"    K_T = {theta_final['K_T']:.2f} N (max thrust per motor at full input)")
    print(f"    d_T = {theta_final['d_T']:.3f} m (thruster separation)")
    print(f"    Max surge force = {2*theta_final['K_T']:.1f} N")
    print(f"    Max yaw torque  = {theta_final['K_T']*theta_final['d_T']:.2f} N*m")
    
    return theta_final, model, segments


def plot_results(theta, segments, dt, output_dir):
    """Plot identification results with simulation comparison."""
    print("\n=== Plotting Results ===")
    model = FossenModel(theta)
    
    # Pick 6 representative segments
    n_plot = min(6, len(segments))
    plot_idx = np.linspace(0, len(segments)-1, n_plot, dtype=int)
    
    fig, axes = plt.subplots(n_plot, 3, figsize=(18, 4*n_plot))
    if n_plot == 1:
        axes = axes.reshape(1, -1)
    
    fig.suptitle('Identification: Simulated (red) vs Actual (blue)', fontsize=14)
    
    for row, idx in enumerate(plot_idx):
        seg = segments[idx]
        nu0 = np.array([seg['u'].iloc[0], seg['v'].iloc[0], seg['r'].iloc[0]])
        n_left = seg['n_left'].values
        n_right = seg['n_right'].values
        
        try:
            nu_sim = model.simulate(nu0, n_left[:-1], n_right[:-1], dt)
        except Exception:
            continue
        
        N = min(len(nu_sim), len(seg))
        t = np.arange(N) * dt
        
        for col, (name, unit, idx_v) in enumerate([
            ('u (surge)', 'm/s', 0), ('v (sway)', 'm/s', 1), ('r (yaw rate)', 'rad/s', 2)
        ]):
            ax = axes[row, col]
            actual_vals = seg[['u','v','r']].values[:N, idx_v]
            ax.plot(t, actual_vals, 'b-', linewidth=1, label='Actual')
            ax.plot(t, nu_sim[:N, idx_v], 'r--', linewidth=1, label='Sim')
            ax.set_ylabel(f'{name} ({unit})')
            if row == 0:
                ax.set_title(name)
            if row == n_plot - 1:
                ax.set_xlabel('Time (s)')
            if row == 0 and col == 0:
                ax.legend(fontsize=8)
            ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plot_path = os.path.join(output_dir, 'identification_results.png')
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [OK] Plot saved: {plot_path}")
    return plot_path


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(script_dir)
    data_dir = os.path.join(base_dir, 'data')
    results_dir = os.path.join(base_dir, 'results')
    os.makedirs(results_dir, exist_ok=True)
    
    # Load data
    csv_path = os.path.join(data_dir, 'processed_data.csv')
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found. Run step1 first.")
        return
    
    data = pd.read_csv(csv_path)
    print(f"Loaded {len(data)} rows from {csv_path}")
    
    dt = data['time'].diff().median()
    print(f"Time step: {dt:.4f} s")
    
    # Run identification
    result = identify(data, dt=dt)
    if result is None:
        print("Identification failed!")
        return
    
    theta, model, segments = result
    
    # Save parameters
    params_path = os.path.join(results_dir, 'identified_params.json')
    
    # Also compute Fossen standard form for ROS2 MPC node
    m = BOAT_MASS
    xg = X_G
    fossen_params = {
        # Direct identified values
        **theta,
        # Fossen standard notation (for reference)
        'X_u_dot': -theta['Xud'],   # Note sign convention
        'Y_v_dot': -theta['Yvd'],
        'N_r_dot': -theta['Nrd'],
        'X_u': theta['Xu'],
        'Y_v': theta['Yv'],
        'N_r': theta['Nr'],
        'X_uu': theta['Xuu'],
        'Y_vv': theta['Yvv'],
        'N_rr': theta['Nrr'],
        'Y_r': theta['Yr'],
        'N_v': theta['Nv'],
        # Mass matrix elements
        'M11': m + theta['Xud'],
        'M22': m + theta['Yvd'],
        'M23': m * xg,
        'M32': m * xg,
        'M33': theta['Iz'] + theta['Nrd'],
        # Metadata
        'metadata': {
            'boat_mass_kg': BOAT_MASS,
            'boat_length_m': BOAT_LENGTH,
            'boat_width_m': BOAT_WIDTH,
            'cg_from_stern_m': CG_FROM_STERN,
            'x_g_m': X_G,
            'max_thrust_per_motor_N': theta['K_T'],
            'thruster_separation_m': theta['d_T'],
            'n_segments_used': len(segments),
        }
    }
    
    with open(params_path, 'w', encoding='utf-8') as f:
        json.dump(fossen_params, f, indent=2)
    print(f"\n[OK] Parameters saved: {params_path}")
    
    # Save YAML for ROS2
    yaml_path = os.path.join(results_dir, 'vessel_params.yaml')
    with open(yaml_path, 'w', encoding='utf-8') as f:
        f.write("# Fossen 3-DOF Vessel Model Parameters\n")
        f.write("# Identified from ArduRover H743 flight log data\n")
        f.write(f"# Boat: {BOAT_MASS}kg, {BOAT_LENGTH}m x {BOAT_WIDTH}m\n")
        f.write("#\n")
        f.write("# Model: M*nu_dot + C(nu)*nu + D(nu)*nu = tau\n")
        f.write("# nu = [u, v, r]  (surge, sway, yaw rate)\n")
        f.write("# tau = [X, Y, N] (surge force, sway force, yaw moment)\n\n")
        f.write("vessel_model:\n")
        f.write("  ros__parameters:\n")
        f.write("    # Physical parameters\n")
        f.write(f"    mass: {BOAT_MASS}\n")
        f.write(f"    length: {BOAT_LENGTH}\n")
        f.write(f"    width: {BOAT_WIDTH}\n")
        f.write(f"    x_g: {X_G}\n")
        f.write(f"    Iz: {theta['Iz']:.6f}\n\n")
        f.write("    # Mass matrix M (3x3, row-major)\n")
        M = model.M
        f.write(f"    M: [{M[0,0]:.6f}, {M[0,1]:.6f}, {M[0,2]:.6f},\n")
        f.write(f"        {M[1,0]:.6f}, {M[1,1]:.6f}, {M[1,2]:.6f},\n")
        f.write(f"        {M[2,0]:.6f}, {M[2,1]:.6f}, {M[2,2]:.6f}]\n\n")
        f.write("    # Added mass (positive convention: M_total = m + Xud)\n")
        f.write(f"    Xud: {theta['Xud']:.6f}\n")
        f.write(f"    Yvd: {theta['Yvd']:.6f}\n")
        f.write(f"    Nrd: {theta['Nrd']:.6f}\n\n")
        f.write("    # Linear damping coefficients\n")
        f.write(f"    Xu: {theta['Xu']:.6f}\n")
        f.write(f"    Yv: {theta['Yv']:.6f}\n")
        f.write(f"    Nr: {theta['Nr']:.6f}\n")
        f.write(f"    Yr: {theta['Yr']:.6f}\n")
        f.write(f"    Nv: {theta['Nv']:.6f}\n\n")
        f.write("    # Nonlinear (quadratic) damping coefficients\n")
        f.write(f"    Xuu: {theta['Xuu']:.6f}\n")
        f.write(f"    Yvv: {theta['Yvv']:.6f}\n")
        f.write(f"    Nrr: {theta['Nrr']:.6f}\n\n")
        f.write("    # Thrust model: T = K_T * sign(n) * n^2\n")
        f.write(f"    K_T: {theta['K_T']:.6f}  # Max thrust per motor (N)\n")
        f.write(f"    d_T: {theta['d_T']:.6f}  # Thruster separation (m)\n")
        f.write(f"    max_surge_force: {2*theta['K_T']:.2f}  # N\n")
        f.write(f"    max_yaw_torque: {theta['K_T']*theta['d_T']:.4f}  # N*m\n")
    
    print(f"[OK] ROS2 YAML saved: {yaml_path}")
    
    # Plot
    plot_path = plot_results(theta, segments, dt, results_dir)
    
    print(f"\n{'='*60}")
    print("IDENTIFICATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Output files:")
    print(f"    - {params_path} (JSON)")
    print(f"    - {yaml_path} (ROS2 YAML)")
    print(f"    - {plot_path} (Plot)")


if __name__ == '__main__':
    main()
