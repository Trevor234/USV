#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
USV 推进器推力模型拟合脚本 (Fit Thrust-PWM Polynomial Model)
-----------------------------------------------------------
功能：
  1. 读取 calibrate_thrust.py 生成并由用户填入 measured_thrust_n 的 CSV 文件；
  2. 自动剔除中位死区，拟合正推和反推的分段二次函数；
  3. 读取并显示 WeAct 功率计实测基准电压；
  4. 输出多项式参数与最大/最小实测推力；
  5. 绘制推力-PWM 标定拟合曲线图并保存。
"""

import argparse
import csv
import sys
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit


def quadratic_fwd(pwm_diff, a, b):
    # 正推模型: T = a * (PWM - db_high)^2 + b * (PWM - db_high)
    return a * (pwm_diff**2) + b * pwm_diff


def quadratic_rev(pwm_diff, a, b):
    # 反推模型: T = -(a * (db_low - PWM)^2 + b * (db_low - PWM))
    return -(a * (pwm_diff**2) + b * pwm_diff)


def main():
    parser = argparse.ArgumentParser(description="推力-PWM 二次多项式拟合工具")
    parser.add_argument("csv_file", type=str, help="填有 measured_thrust_n 的 CSV 文件路径")
    parser.add_argument("--db-high", type=int, default=1525, help="正向起转死区上限 PWM (µs, 默认 1525)")
    parser.add_argument("--db-low", type=int, default=1475, help="反向起转死区下限 PWM (µs, 默认 1475)")
    parser.add_argument("--plot", action="store_true", default=True, help="是否保存拟合对比图 (默认保存)")
    args = parser.parse_args()

    pwms = []
    thrusts = []
    voltages = []

    try:
        with open(args.csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                thrust_str = row.get('measured_thrust_n', '').strip()
                if not thrust_str:
                    continue
                try:
                    t_val = float(thrust_str)
                    p_val = float(row['target_pwm'])
                    pwms.append(p_val)
                    thrusts.append(t_val)
                    v_str = row.get('avg_voltage_v', '').strip()
                    if v_str and v_str != 'N/A':
                        voltages.append(float(v_str))
                except ValueError:
                    continue
    except Exception as e:
        print(f"[错误] 读取 CSV 失败: {e}")
        sys.exit(1)

    if len(pwms) < 4:
        print("[错误] 有效实测数据点不足 4 个，请确认在 CSV 的 'measured_thrust_n' 列中填入了数值！")
        sys.exit(1)

    pwms = np.array(pwms)
    thrusts = np.array(thrusts)

    # 区分正推与反推
    mask_fwd = pwms > args.db_high
    mask_rev = pwms < args.db_low

    fwd_pwms, fwd_thrusts = pwms[mask_fwd], thrusts[mask_fwd]
    rev_pwms, rev_thrusts = pwms[mask_rev], thrusts[mask_rev]

    print("\n" + "=" * 62)
    print("                推进器推力模型拟合结果")
    print("=" * 62)
    if voltages:
        print(f"  * 标定基准工作电压 (Mean V): {np.mean(voltages):.2f} V (范围: {np.min(voltages):.2f}V ~ {np.max(voltages):.2f}V)")
    print(f"  * 中位死区设定: [{args.db_low} µs, {args.db_high} µs]")

    # 1. 拟合正推
    popt_fwd = [0.0, 0.0]
    if len(fwd_pwms) >= 2:
        x_fwd = fwd_pwms - args.db_high
        popt_fwd, _ = curve_fit(quadratic_fwd, x_fwd, fwd_thrusts)
        max_fwd_t = np.max(fwd_thrusts)
        print(f"\n【正推区间】(PWM > {args.db_high} µs)")
        print(f"  * 拟合方程: T = {popt_fwd[0]:.6e} * (PWM - {args.db_high})^2 + {popt_fwd[1]:.6e} * (PWM - {args.db_high})")
        print(f"  * 实测最大正推力 T_max: {max_fwd_t:.2f} N")
    else:
        print("\n  [提示] 正推数据不足，跳过正推拟合。")

    # 2. 拟合反推
    popt_rev = [0.0, 0.0]
    if len(rev_pwms) >= 2:
        x_rev = args.db_low - rev_pwms
        popt_rev, _ = curve_fit(quadratic_rev, x_rev, rev_thrusts)
        min_rev_t = np.min(rev_thrusts)
        print(f"\n【反推区间】(PWM < {args.db_low} µs)")
        print(f"  * 拟合方程: T = -({popt_rev[0]:.6e} * ({args.db_low} - PWM)^2 + {popt_rev[1]:.6e} * ({args.db_low} - PWM))")
        print(f"  * 实测最大反推力 T_min: {min_rev_t:.2f} N")
    else:
        print("\n  [提示] 反推数据不足，跳过反推拟合。")

    print("=" * 62)

    # 绘图
    if args.plot:
        plt.figure(figsize=(9, 5))
        plt.scatter(pwms, thrusts, color='red', label='Measured Points', zorder=5)

        # 绘制拟合线
        pwm_grid = np.linspace(pwms.min(), pwms.max(), 300)
        thrust_fit = []
        for p in pwm_grid:
            if p > args.db_high and len(fwd_pwms) >= 2:
                thrust_fit.append(quadratic_fwd(p - args.db_high, *popt_fwd))
            elif p < args.db_low and len(rev_pwms) >= 2:
                thrust_fit.append(quadratic_rev(args.db_low - p, *popt_rev))
            else:
                thrust_fit.append(0.0)

        plt.plot(pwm_grid, thrust_fit, 'b--', label='Fitted Model')
        plt.axhline(0, color='gray', linestyle=':', alpha=0.6)
        plt.axvline(args.db_low, color='orange', linestyle=':', label=f'Deadband Low ({args.db_low}us)')
        plt.axvline(args.db_high, color='orange', linestyle=':', label=f'Deadband High ({args.db_high}us)')
        plt.title('Thrust vs PWM Calibration Curve')
        plt.xlabel('PWM (µs)')
        plt.ylabel('Thrust (N)')
        plt.grid(True, alpha=0.3)
        plt.legend()
        out_fig = args.csv_file.replace('.csv', '_curve.png')
        plt.savefig(out_fig, dpi=200, bbox_inches='tight')
        print(f"[图像导出] 标定曲线已保存至: {out_fig}\n")


if __name__ == '__main__':
    main()
