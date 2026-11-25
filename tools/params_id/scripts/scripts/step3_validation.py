#!/usr/bin/env python3
"""
Stage 3: Model Validation
=========================
Validate identified Fossen 3-DOF model:
  1. Open-loop simulation on unseen data segments
  2. Compare simulated vs actual velocities and trajectory
  3. Compute RMSE, R^2 metrics
"""

import os
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Import model from step2
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from step2_identification import (
    FossenModel, pwm_to_normalized,
    BOAT_MASS, BOAT_LENGTH, BOAT_WIDTH, X_G, CG_FROM_STERN
)


def rotation_matrix(psi):
    c, s = np.cos(psi), np.sin(psi)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def validate_model(model, data, dt, seg_len=100):
    """
    Validate model on data segments.
    
    Uses longer segments than identification to test prediction quality.
    """
    print("\n=== Model Validation ===")
    
    # Prepare data
    valid = data.dropna(subset=['u', 'v', 'r', 'pwm_left', 'pwm_right', 'gps_speed']).copy()
    valid['n_left'] = pwm_to_normalized(valid['pwm_left'].values)
    valid['n_right'] = pwm_to_normalized(valid['pwm_right'].values)
    
    # Select segments where boat is moving
    moving = valid['gps_speed'] > 0.2
    
    # Extract segments
    segments = []
    i = 0
    while i < len(valid):
        if moving.iloc[i]:
            j = i
            while j < len(valid) and moving.iloc[j] and j - i < seg_len * 2:
                j += 1
            seg = valid.iloc[i:j]
            if len(seg) >= seg_len:
                segments.append(seg.iloc[:seg_len].copy())
            i = j
        else:
            i += 1
    
    print(f"  Found {len(segments)} validation segments (length={seg_len}, dt={dt:.3f}s)")
    
    # Simulate each segment
    all_results = []
    for idx, seg in enumerate(segments):
        nu0 = np.array([seg['u'].iloc[0], seg['v'].iloc[0], seg['r'].iloc[0]])
        n_left = seg['n_left'].values
        n_right = seg['n_right'].values
        
        try:
            nu_sim = model.simulate(nu0, n_left[:-1], n_right[:-1], dt)
        except Exception:
            continue
        
        N = min(len(nu_sim), len(seg))
        if np.any(np.isnan(nu_sim[:N])):
            continue
        
        # Also simulate position (kinematics)
        psi0 = seg['psi'].iloc[0] if 'psi' in seg.columns else 0
        x0 = seg['x_n'].iloc[0] if 'x_n' in seg.columns else 0
        y0 = seg['y_e'].iloc[0] if 'y_e' in seg.columns else 0
        
        x_sim = np.zeros(N)
        y_sim = np.zeros(N)
        psi_sim = np.zeros(N)
        x_sim[0], y_sim[0], psi_sim[0] = x0, y0, psi0
        
        for k in range(1, N):
            u_k = nu_sim[k-1, 0]
            v_k = nu_sim[k-1, 1]
            r_k = nu_sim[k-1, 2]
            
            x_sim[k] = x_sim[k-1] + dt * (u_k * np.cos(psi_sim[k-1]) - v_k * np.sin(psi_sim[k-1]))
            y_sim[k] = y_sim[k-1] + dt * (u_k * np.sin(psi_sim[k-1]) + v_k * np.cos(psi_sim[k-1]))
            psi_sim[k] = psi_sim[k-1] + dt * r_k
            psi_sim[k] = np.arctan2(np.sin(psi_sim[k]), np.cos(psi_sim[k]))
        
        result = {
            'seg_idx': idx,
            'time': (seg['time'].values[:N] - seg['time'].values[0]),
            'u_actual': seg['u'].values[:N],
            'v_actual': seg['v'].values[:N],
            'r_actual': seg['r'].values[:N],
            'u_sim': nu_sim[:N, 0],
            'v_sim': nu_sim[:N, 1],
            'r_sim': nu_sim[:N, 2],
            'x_actual': seg['x_n'].values[:N] if 'x_n' in seg.columns else np.zeros(N),
            'y_actual': seg['y_e'].values[:N] if 'y_e' in seg.columns else np.zeros(N),
            'psi_actual': seg['psi'].values[:N] if 'psi' in seg.columns else np.zeros(N),
            'x_sim': x_sim,
            'y_sim': y_sim,
            'psi_sim': psi_sim,
        }
        all_results.append(result)
    
    print(f"  Successfully simulated: {len(all_results)} / {len(segments)} segments")
    return all_results


def compute_metrics(results):
    """Compute aggregate metrics."""
    print("\n--- Validation Metrics ---")
    
    metrics = {}
    
    for var, name in [('u', 'Surge velocity'), ('v', 'Sway velocity'), ('r', 'Yaw rate')]:
        all_err = []
        all_actual = []
        for r in results:
            all_err.extend((r[f'{var}_sim'] - r[f'{var}_actual']).tolist())
            all_actual.extend(r[f'{var}_actual'].tolist())
        
        err = np.array(all_err)
        actual = np.array(all_actual)
        rmse = np.sqrt(np.mean(err**2))
        ss_res = np.sum(err**2)
        ss_tot = np.sum((actual - actual.mean())**2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 1e-10 else 0
        mae = np.mean(np.abs(err))
        
        metrics[f'{var}_rmse'] = rmse
        metrics[f'{var}_r2'] = r2
        metrics[f'{var}_mae'] = mae
        
        print(f"  {name:<18s}: RMSE={rmse:.4f}, MAE={mae:.4f}, R^2={r2:.4f}")
    
    # Position metrics
    all_pos_err = []
    for r in results:
        pos_err = np.sqrt((r['x_sim'] - r['x_actual'])**2 + (r['y_sim'] - r['y_actual'])**2)
        all_pos_err.extend(pos_err.tolist())
    
    pos_err = np.array(all_pos_err)
    metrics['position_rmse'] = float(np.sqrt(np.mean(pos_err**2)))
    metrics['position_max'] = float(pos_err.max())
    print(f"  {'Position':<18s}: RMSE={metrics['position_rmse']:.4f}m, Max={metrics['position_max']:.4f}m")
    
    # Heading metrics
    all_head_err = []
    for r in results:
        head_err = np.arctan2(
            np.sin(r['psi_sim'] - r['psi_actual']),
            np.cos(r['psi_sim'] - r['psi_actual'])
        )
        all_head_err.extend(head_err.tolist())
    
    head_err = np.array(all_head_err)
    metrics['heading_rmse_deg'] = float(np.degrees(np.sqrt(np.mean(head_err**2))))
    print(f"  {'Heading':<18s}: RMSE={metrics['heading_rmse_deg']:.2f} deg")
    
    return metrics


def plot_validation(results, metrics, output_dir):
    """Plot validation results."""
    print("\n=== Plotting Validation ===")
    
    # Pick 4 representative segments
    n_plot = min(4, len(results))
    plot_idx = np.linspace(0, len(results)-1, n_plot, dtype=int)
    
    fig, axes = plt.subplots(n_plot + 1, 3, figsize=(18, 4*(n_plot+1)))
    fig.suptitle('Model Validation: Simulated (red) vs Actual (blue)', fontsize=14)
    
    # Plot segments
    for row, idx in enumerate(plot_idx):
        r = results[idx]
        t = r['time']
        
        # Surge velocity
        ax = axes[row, 0]
        ax.plot(t, r['u_actual'], 'b-', lw=1, label='Actual')
        ax.plot(t, r['u_sim'], 'r--', lw=1, label='Sim')
        ax.set_ylabel('u (m/s)')
        if row == 0:
            ax.set_title('Surge Velocity')
            ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        
        # Yaw rate
        ax = axes[row, 1]
        ax.plot(t, np.degrees(r['r_actual']), 'b-', lw=1)
        ax.plot(t, np.degrees(r['r_sim']), 'r--', lw=1)
        ax.set_ylabel('r (deg/s)')
        if row == 0:
            ax.set_title('Yaw Rate')
        ax.grid(True, alpha=0.3)
        
        # Trajectory
        ax = axes[row, 2]
        ax.plot(r['y_actual'], r['x_actual'], 'b-', lw=1.5, label='Actual')
        ax.plot(r['y_sim'], r['x_sim'], 'r--', lw=1.5, label='Sim')
        ax.plot(r['y_actual'][0], r['x_actual'][0], 'go', ms=6)
        ax.set_ylabel('North (m)')
        ax.set_xlabel('East (m)')
        if row == 0:
            ax.set_title('Trajectory')
            ax.legend(fontsize=8)
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
    
    # Summary row: error distributions
    all_err_u = np.concatenate([r['u_sim'] - r['u_actual'] for r in results])
    all_err_r = np.concatenate([r['r_sim'] - r['r_actual'] for r in results])
    all_pos_err = np.concatenate([
        np.sqrt((r['x_sim']-r['x_actual'])**2 + (r['y_sim']-r['y_actual'])**2)
        for r in results
    ])
    
    ax = axes[-1, 0]
    ax.hist(all_err_u, bins=50, density=True, color='steelblue', alpha=0.7)
    ax.axvline(0, color='r', ls='--')
    ax.set_xlabel('u error (m/s)')
    ax.set_title(f'Surge Error (RMSE={metrics["u_rmse"]:.4f}, R2={metrics["u_r2"]:.4f})')
    ax.grid(True, alpha=0.3)
    
    ax = axes[-1, 1]
    ax.hist(np.degrees(all_err_r), bins=50, density=True, color='steelblue', alpha=0.7)
    ax.axvline(0, color='r', ls='--')
    ax.set_xlabel('r error (deg/s)')
    ax.set_title(f'Yaw Rate Error (RMSE={metrics["r_rmse"]:.4f}, R2={metrics["r_r2"]:.4f})')
    ax.grid(True, alpha=0.3)
    
    ax = axes[-1, 2]
    ax.hist(all_pos_err, bins=50, density=True, color='steelblue', alpha=0.7)
    ax.set_xlabel('Position error (m)')
    ax.set_title(f'Position Error (RMSE={metrics["position_rmse"]:.3f}m)')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plot_path = os.path.join(output_dir, 'validation_results.png')
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
    
    print("=" * 60)
    print("Stage 3: Model Validation")
    print("=" * 60)
    
    # Load data
    csv_path = os.path.join(data_dir, 'processed_data.csv')
    data = pd.read_csv(csv_path)
    print(f"  Loaded {len(data)} rows")
    
    dt = data['time'].diff().median()
    
    # Load parameters
    params_path = os.path.join(results_dir, 'identified_params.json')
    with open(params_path, 'r') as f:
        params_json = json.load(f)
    
    # Extract model params (exclude metadata and Fossen notation duplicates)
    from step2_identification import PARAM_NAMES
    theta = {k: params_json[k] for k in PARAM_NAMES if k in params_json}
    print(f"  Loaded {len(theta)} parameters")
    
    # Create model
    model = FossenModel(theta)
    
    # Validate
    results = validate_model(model, data, dt, seg_len=100)
    
    if not results:
        print("No valid validation segments!")
        return
    
    # Metrics
    metrics = compute_metrics(results)
    
    # Save
    metrics_path = os.path.join(results_dir, 'validation_metrics.json')
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"\n  [OK] Metrics saved: {metrics_path}")
    
    # Plot
    plot_path = plot_validation(results, metrics, results_dir)
    
    print(f"\n{'='*60}")
    print("Stage 3 Complete!")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
