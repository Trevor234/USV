#!/usr/bin/env python3
"""
阶段1：ArduRover DataFlash (.bin) 日志解析
============================================
从 H743 飞控的 .bin 日志中提取水面无人艇参数辨识所需数据：
  - ATT:  姿态（Yaw 艏向角）
  - GPS:  位置（Lat, Lng, Spd, GCrs）
  - RCOU: 推进器PWM输出（C1=左推, C3=右推）
  - IMU/GYR: 角速度（GyrZ = 艏摇角速度 r）
  - XKF1/NKF1: EKF速度估计（VN, VE = 北/东向速度）

船体参数：
  - 质量: 14.2 kg
  - 长: 1.2m, 宽: 0.6m
  - 重心距船尾: 0.48m
  - 推进方式: 差速推进（左C1=73, 右C3=74）

输出: processed_data.csv（统一时间轴的辨识用数据）
"""

import os
import sys
import glob
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from scipy.signal import butter, filtfilt
import matplotlib
matplotlib.use('Agg')  # 非交互式后端
import matplotlib.pyplot as plt

# ============================================================
# 配置
# ============================================================
# 船体参数
BOAT_MASS = 14.2        # kg
BOAT_LENGTH = 1.2       # m
BOAT_WIDTH = 0.6        # m
CG_FROM_STERN = 0.48    # m (重心距船尾)
THRUSTER_SEPARATION = 0.5  # m (两个推进器之间的横向距离，估计值)

# PWM 配置
PWM_NEUTRAL = 1500      # 中位 PWM
PWM_MIN = 1100          # 最小 PWM
PWM_MAX = 1900          # 最大 PWM
MAX_THRUST = 20.0       # N (单个推进器最大推力，估计值)

# 重采样频率
RESAMPLE_HZ = 10        # Hz

# 滤波器参数
FILTER_CUTOFF = 2.0     # Hz (低通截止频率)
FILTER_ORDER = 3


def pwm_to_thrust(pwm):
    """
    将 PWM 信号转换为推力 (N)
    
    假设线性映射（简化模型）：
      - PWM=1500 → 0 N
      - PWM=1900 → +MAX_THRUST N（前进）
      - PWM=1100 → -MAX_THRUST N（后退）
    
    实际中可能需要根据推进器特性曲线修正（二次关系更常见）
    """
    # 归一化到 [-1, 1]
    normalized = (np.asarray(pwm, dtype=float) - PWM_NEUTRAL) / (PWM_MAX - PWM_NEUTRAL)
    normalized = np.clip(normalized, -1.0, 1.0)
    
    # 二次推力模型: T = k * |n| * n （更贴近螺旋桨特性）
    thrust = MAX_THRUST * np.sign(normalized) * normalized**2
    return thrust


def gps_to_ned(lat, lon, lat0, lon0):
    """
    将 GPS 经纬度 (度) 转换为相对于参考点的 NED 本地坐标 (m)
    
    使用简化的平面近似（适用于小范围区域）
    """
    lat_rad = np.radians(lat0)
    
    # 地球半径
    R_earth = 6371000.0  # m
    
    # 经纬度差转换为米
    d_lat = np.radians(lat - lat0)
    d_lon = np.radians(lon - lon0)
    
    north = d_lat * R_earth
    east = d_lon * R_earth * np.cos(lat_rad)
    
    return north, east


def butter_lowpass_filter(data, cutoff, fs, order=3):
    """巴特沃斯低通滤波器"""
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    if normal_cutoff >= 1.0:
        return data  # 截止频率过高，不滤波
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    # 处理 NaN
    mask = ~np.isnan(data)
    if mask.sum() < order * 3:
        return data
    filtered = data.copy()
    filtered[mask] = filtfilt(b, a, data[mask])
    return filtered


def parse_bin_file(filepath):
    """
    解析单个 .bin DataFlash 日志文件
    返回各消息类型的 DataFrame 字典
    """
    from pymavlink import mavutil
    
    print(f"  正在解析: {os.path.basename(filepath)}")
    print(f"  文件大小: {os.path.getsize(filepath) / 1024 / 1024:.1f} MB")
    
    mlog = mavutil.mavlink_connection(filepath)
    
    # 存储各类型消息
    data = {
        'ATT': [],    # 姿态
        'GPS': [],    # GPS
        'RCOU': [],   # RC输出
        'IMU': [],    # IMU
        'XKF1': [],   # EKF状态（ArduPilot 4.x）
        'NKF1': [],   # EKF状态（ArduPilot 3.x）
        'AHRS': [],   # AHRS航向
    }
    
    msg_count = 0
    while True:
        try:
            m = mlog.recv_match()
        except Exception as e:
            print(f"  读取消息时出错: {e}")
            break
            
        if m is None:
            break
        
        msg_type = m.get_type()
        msg_count += 1
        
        if msg_count % 100000 == 0:
            print(f"    已处理 {msg_count} 条消息...")
        
        try:
            if msg_type == 'ATT':
                data['ATT'].append({
                    'timestamp': m._timestamp,
                    'Roll': getattr(m, 'Roll', None),
                    'Pitch': getattr(m, 'Pitch', None),
                    'Yaw': getattr(m, 'Yaw', None),
                    'DesYaw': getattr(m, 'DesYaw', None),
                    'ErrYaw': getattr(m, 'ErrYaw', None),
                })
            elif msg_type == 'GPS':
                status = getattr(m, 'Status', 0)
                if status >= 3:  # 至少 3D Fix
                    data['GPS'].append({
                        'timestamp': m._timestamp,
                        'Lat': getattr(m, 'Lat', None),
                        'Lng': getattr(m, 'Lng', None),
                        'Alt': getattr(m, 'Alt', None),
                        'Spd': getattr(m, 'Spd', None),
                        'GCrs': getattr(m, 'GCrs', None),
                        'NSats': getattr(m, 'NSats', None),
                        'HDop': getattr(m, 'HDop', None),
                    })
            elif msg_type == 'RCOU':
                data['RCOU'].append({
                    'timestamp': m._timestamp,
                    'C1': getattr(m, 'C1', None),  # 左推进器
                    'C2': getattr(m, 'C2', None),
                    'C3': getattr(m, 'C3', None),  # 右推进器
                    'C4': getattr(m, 'C4', None),
                })
            elif msg_type == 'IMU':
                data['IMU'].append({
                    'timestamp': m._timestamp,
                    'GyrX': getattr(m, 'GyrX', None),
                    'GyrY': getattr(m, 'GyrY', None),
                    'GyrZ': getattr(m, 'GyrZ', None),
                    'AccX': getattr(m, 'AccX', None),
                    'AccY': getattr(m, 'AccY', None),
                    'AccZ': getattr(m, 'AccZ', None),
                })
            elif msg_type in ('XKF1', 'NKF1'):
                data[msg_type].append({
                    'timestamp': m._timestamp,
                    'VN': getattr(m, 'VN', None),    # 北向速度
                    'VE': getattr(m, 'VE', None),    # 东向速度
                    'VD': getattr(m, 'VD', None),    # 下向速度
                })
            elif msg_type == 'AHRS':
                data['AHRS'].append({
                    'timestamp': m._timestamp,
                    'Yaw': getattr(m, 'Yaw', None),
                })
        except Exception as e:
            pass  # 跳过解析失败的消息
    
    print(f"  总消息数: {msg_count}")
    
    # 转换为 DataFrame
    dfs = {}
    for key, records in data.items():
        if records:
            df = pd.DataFrame(records)
            df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
            df = df.dropna(subset=['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)
            dfs[key] = df
            print(f"    {key}: {len(df)} 条记录")
    
    return dfs


def merge_and_resample(dfs, target_hz=RESAMPLE_HZ):
    """
    将不同频率的消息时间对齐，重采样到统一频率
    """
    print(f"\n=== 时间对齐与重采样 (目标: {target_hz} Hz) ===")
    
    # 找到所有数据的公共时间范围
    t_starts = []
    t_ends = []
    for key, df in dfs.items():
        if len(df) > 0:
            t_starts.append(df['timestamp'].min())
            t_ends.append(df['timestamp'].max())
    
    t_start = max(t_starts)
    t_end = min(t_ends)
    duration = t_end - t_start
    print(f"  公共时间范围: {duration:.1f} 秒")
    
    if duration < 5:
        print("  警告: 数据时间范围过短!")
        return None
    
    # 创建统一时间轴
    dt = 1.0 / target_hz
    t_uniform = np.arange(t_start + 1.0, t_end - 1.0, dt)  # 留边裕量
    n_samples = len(t_uniform)
    print(f"  统一时间轴: {n_samples} 个采样点, 间隔 {dt:.3f}s")
    
    result = pd.DataFrame({'timestamp': t_uniform})
    result['time'] = t_uniform - t_uniform[0]  # 相对时间（从0开始）
    
    # ---- 插值 ATT ----
    if 'ATT' in dfs and len(dfs['ATT']) > 10:
        df = dfs['ATT']
        t = df['timestamp'].values
        
        # Yaw (度) → 弧度，处理角度绕转
        yaw_deg = df['Yaw'].values
        yaw_rad = np.radians(yaw_deg)
        # 使用 sin/cos 插值避免 360→0 跳变
        sin_yaw = np.sin(yaw_rad)
        cos_yaw = np.cos(yaw_rad)
        
        f_sin = interp1d(t, sin_yaw, kind='linear', bounds_error=False, fill_value='extrapolate')
        f_cos = interp1d(t, cos_yaw, kind='linear', bounds_error=False, fill_value='extrapolate')
        
        result['psi'] = np.arctan2(f_sin(t_uniform), f_cos(t_uniform))  # 弧度
        
        if 'DesYaw' in df.columns and df['DesYaw'].notna().sum() > 10:
            des_yaw_rad = np.radians(df['DesYaw'].values)
            f_des_sin = interp1d(t, np.sin(des_yaw_rad), kind='linear', bounds_error=False, fill_value='extrapolate')
            f_des_cos = interp1d(t, np.cos(des_yaw_rad), kind='linear', bounds_error=False, fill_value='extrapolate')
            result['psi_des'] = np.arctan2(f_des_sin(t_uniform), f_des_cos(t_uniform))
        
        print("  [OK] ATT 数据已插值")
    
    # ---- 插值 GPS ----
    if 'GPS' in dfs and len(dfs['GPS']) > 10:
        df = dfs['GPS']
        t = df['timestamp'].values
        lat = df['Lat'].values
        lng = df['Lng'].values
        
        # 参考点：取第一个有效GPS点
        lat0, lon0 = lat[0], lng[0]
        north, east = gps_to_ned(lat, lng, lat0, lon0)
        
        f_n = interp1d(t, north, kind='linear', bounds_error=False, fill_value='extrapolate')
        f_e = interp1d(t, east, kind='linear', bounds_error=False, fill_value='extrapolate')
        
        result['x_n'] = f_n(t_uniform)  # 北向位置 (m)
        result['y_e'] = f_e(t_uniform)  # 东向位置 (m)
        
        # GPS 地速
        if 'Spd' in df.columns and df['Spd'].notna().sum() > 10:
            f_spd = interp1d(t, df['Spd'].values, kind='linear', bounds_error=False, fill_value='extrapolate')
            result['gps_speed'] = f_spd(t_uniform)
        
        # GPS 航向
        if 'GCrs' in df.columns and df['GCrs'].notna().sum() > 10:
            gcrs_rad = np.radians(df['GCrs'].values)
            f_gc_sin = interp1d(t, np.sin(gcrs_rad), kind='linear', bounds_error=False, fill_value='extrapolate')
            f_gc_cos = interp1d(t, np.cos(gcrs_rad), kind='linear', bounds_error=False, fill_value='extrapolate')
            result['gps_course'] = np.arctan2(f_gc_sin(t_uniform), f_gc_cos(t_uniform))
        
        # 保存参考点
        result.attrs['lat0'] = lat0
        result.attrs['lon0'] = lon0
        
        print(f"  [OK] GPS 数据已插值 (参考点: {lat0:.6f}, {lon0:.6f})")
    
    # ---- 插值 RCOU ----
    if 'RCOU' in dfs and len(dfs['RCOU']) > 10:
        df = dfs['RCOU']
        t = df['timestamp'].values
        
        # 左推进器 (C1) 和右推进器 (C3) 的 PWM
        for ch, name in [('C1', 'pwm_left'), ('C3', 'pwm_right')]:
            if ch in df.columns and df[ch].notna().sum() > 10:
                f_ch = interp1d(t, df[ch].values, kind='zero', bounds_error=False, fill_value=PWM_NEUTRAL)
                result[name] = f_ch(t_uniform)
        
        # PWM → 推力
        if 'pwm_left' in result.columns and 'pwm_right' in result.columns:
            result['T_left'] = pwm_to_thrust(result['pwm_left'].values)
            result['T_right'] = pwm_to_thrust(result['pwm_right'].values)
            
            # 计算广义力
            # τ_X = T_left + T_right (纵荡力)
            # τ_Y = 0 (差速推进无横向力)
            # τ_N = (T_right - T_left) * d/2 (艏摇力矩)
            d = THRUSTER_SEPARATION
            result['tau_X'] = result['T_left'] + result['T_right']
            result['tau_Y'] = 0.0
            result['tau_N'] = (result['T_right'] - result['T_left']) * d / 2.0
        
        print("  [OK] RCOU 数据已插值并转换为推力")
    
    # ---- 插值 IMU (角速度) ----
    if 'IMU' in dfs and len(dfs['IMU']) > 10:
        df = dfs['IMU']
        t = df['timestamp'].values
        
        if 'GyrZ' in df.columns and df['GyrZ'].notna().sum() > 10:
            f_gz = interp1d(t, df['GyrZ'].values, kind='linear', bounds_error=False, fill_value=0)
            result['r'] = f_gz(t_uniform)  # 艏摇角速度 (rad/s)
        
        if 'AccX' in df.columns and df['AccX'].notna().sum() > 10:
            f_ax = interp1d(t, df['AccX'].values, kind='linear', bounds_error=False, fill_value=0)
            result['acc_x'] = f_ax(t_uniform)  # 纵荡加速度 (m/s²)
        
        if 'AccY' in df.columns and df['AccY'].notna().sum() > 10:
            f_ay = interp1d(t, df['AccY'].values, kind='linear', bounds_error=False, fill_value=0)
            result['acc_y'] = f_ay(t_uniform)  # 横荡加速度 (m/s²)
        
        print("  [OK] IMU 数据已插值")
    
    # ---- 插值 EKF 速度 ----
    ekf_key = 'XKF1' if 'XKF1' in dfs and len(dfs.get('XKF1', [])) > 10 else \
              ('NKF1' if 'NKF1' in dfs and len(dfs.get('NKF1', [])) > 10 else None)
    
    if ekf_key:
        df = dfs[ekf_key]
        t = df['timestamp'].values
        
        # EKF 输出的是 NED 速度，需要转到船体坐标系
        if 'VN' in df.columns and 'VE' in df.columns:
            f_vn = interp1d(t, df['VN'].values, kind='linear', bounds_error=False, fill_value=0)
            f_ve = interp1d(t, df['VE'].values, kind='linear', bounds_error=False, fill_value=0)
            
            result['v_north'] = f_vn(t_uniform)
            result['v_east'] = f_ve(t_uniform)
            
            # NED 速度 → 船体坐标系速度
            if 'psi' in result.columns:
                psi = result['psi'].values
                result['u'] = result['v_north'] * np.cos(psi) + result['v_east'] * np.sin(psi)   # 纵荡速度
                result['v'] = -result['v_north'] * np.sin(psi) + result['v_east'] * np.cos(psi)  # 横荡速度
            
            print(f"  [OK] {ekf_key} EKF 速度数据已插值并转换到船体坐标系")
    else:
        # 如果没有 EKF 速度，从 GPS 位置数值微分获取
        if 'x_n' in result.columns and 'y_e' in result.columns:
            vn = np.gradient(result['x_n'].values, dt)
            ve = np.gradient(result['y_e'].values, dt)
            result['v_north'] = vn
            result['v_east'] = ve
            
            if 'psi' in result.columns:
                psi = result['psi'].values
                result['u'] = vn * np.cos(psi) + ve * np.sin(psi)
                result['v'] = -vn * np.sin(psi) + ve * np.cos(psi)
            
            print("  [OK] 从 GPS 位置微分获取速度")
    
    # ---- 低通滤波 ----
    print("\n=== 低通滤波 ===")
    cols_to_filter = ['u', 'v', 'r', 'acc_x', 'acc_y', 'x_n', 'y_e']
    for col in cols_to_filter:
        if col in result.columns:
            result[col] = butter_lowpass_filter(result[col].values, FILTER_CUTOFF, target_hz, FILTER_ORDER)
            print(f"  [OK] {col} 已滤波 (截止频率 {FILTER_CUTOFF} Hz)")
    
    # ---- 计算加速度 (从速度数值微分) ----
    if 'u' in result.columns:
        result['u_dot'] = np.gradient(result['u'].values, dt)
        result['u_dot'] = butter_lowpass_filter(result['u_dot'].values, 1.0, target_hz, 2)
    if 'v' in result.columns:
        result['v_dot'] = np.gradient(result['v'].values, dt)
        result['v_dot'] = butter_lowpass_filter(result['v_dot'].values, 1.0, target_hz, 2)
    if 'r' in result.columns:
        result['r_dot'] = np.gradient(result['r'].values, dt)
        result['r_dot'] = butter_lowpass_filter(result['r_dot'].values, 1.0, target_hz, 2)
    
    return result


def plot_data_overview(data, output_dir):
    """绘制数据概览图"""
    print("\n=== 绘制数据概览 ===")
    
    t = data['time'].values
    
    fig, axes = plt.subplots(4, 2, figsize=(16, 20))
    fig.suptitle('数据概览 - 水面无人艇日志', fontsize=16)
    
    # 1. 轨迹
    ax = axes[0, 0]
    if 'x_n' in data.columns and 'y_e' in data.columns:
        ax.plot(data['y_e'], data['x_n'], 'b-', linewidth=0.5)
        ax.plot(data['y_e'].iloc[0], data['x_n'].iloc[0], 'go', markersize=10, label='Start')
        ax.plot(data['y_e'].iloc[-1], data['x_n'].iloc[-1], 'ro', markersize=10, label='End')
        ax.set_xlabel('East (m)')
        ax.set_ylabel('North (m)')
        ax.set_title('Trajectory (NED)')
        ax.legend()
        ax.set_aspect('equal')
        ax.grid(True)
    
    # 2. 艏向角
    ax = axes[0, 1]
    if 'psi' in data.columns:
        ax.plot(t, np.degrees(data['psi']), 'b-', linewidth=0.5, label='Actual')
        if 'psi_des' in data.columns:
            ax.plot(t, np.degrees(data['psi_des']), 'r--', linewidth=0.5, label='Desired')
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Yaw (deg)')
        ax.set_title('Heading')
        ax.legend()
        ax.grid(True)
    
    # 3. 纵荡速度
    ax = axes[1, 0]
    if 'u' in data.columns:
        ax.plot(t, data['u'], 'b-', linewidth=0.5)
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('u (m/s)')
        ax.set_title('Surge Velocity')
        ax.grid(True)
    
    # 4. 横荡速度
    ax = axes[1, 1]
    if 'v' in data.columns:
        ax.plot(t, data['v'], 'r-', linewidth=0.5)
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('v (m/s)')
        ax.set_title('Sway Velocity')
        ax.grid(True)
    
    # 5. 艏摇角速度
    ax = axes[2, 0]
    if 'r' in data.columns:
        ax.plot(t, np.degrees(data['r']), 'g-', linewidth=0.5)
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('r (deg/s)')
        ax.set_title('Yaw Rate')
        ax.grid(True)
    
    # 6. PWM 输出
    ax = axes[2, 1]
    if 'pwm_left' in data.columns and 'pwm_right' in data.columns:
        ax.plot(t, data['pwm_left'], 'b-', linewidth=0.5, label='Left (C1)')
        ax.plot(t, data['pwm_right'], 'r-', linewidth=0.5, label='Right (C3)')
        ax.axhline(y=PWM_NEUTRAL, color='k', linestyle='--', alpha=0.3)
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('PWM (us)')
        ax.set_title('Thruster PWM Output')
        ax.legend()
        ax.grid(True)
    
    # 7. 推力
    ax = axes[3, 0]
    if 'tau_X' in data.columns and 'tau_N' in data.columns:
        ax.plot(t, data['tau_X'], 'b-', linewidth=0.5, label='τ_X (Surge)')
        ax.plot(t, data['tau_N'], 'r-', linewidth=0.5, label='τ_N (Yaw)')
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Force (N) / Torque (N·m)')
        ax.set_title('Generalized Forces')
        ax.legend()
        ax.grid(True)
    
    # 8. GPS 速度 vs 船体速度
    ax = axes[3, 1]
    if 'gps_speed' in data.columns and 'u' in data.columns:
        ax.plot(t, data['gps_speed'], 'g-', linewidth=0.5, label='GPS Speed')
        speed_body = np.sqrt(data['u']**2 + data['v']**2) if 'v' in data.columns else np.abs(data['u'])
        ax.plot(t, speed_body, 'b--', linewidth=0.5, label='Body Speed (√(u²+v²))')
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Speed (m/s)')
        ax.set_title('Speed Comparison')
        ax.legend()
        ax.grid(True)
    
    plt.tight_layout()
    plot_path = os.path.join(output_dir, 'data_overview.png')
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  [OK] 概览图已保存: {plot_path}")
    return plot_path


def main():
    """主函数"""
    # 日志目录
    log_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(log_dir, 'data')
    os.makedirs(output_dir, exist_ok=True)
    
    print("=" * 60)
    print("阶段1: ArduRover DataFlash 日志解析")
    print("=" * 60)
    
    # 找到目标 .bin 文件（2026-06-25 13:30~16:00）
    target_bins = []
    for f in sorted(glob.glob(os.path.join(log_dir, '2026-06-25*.bin'))):
        basename = os.path.basename(f)
        # 提取时间部分
        try:
            time_part = basename.replace('.bin', '').split(' ')[1]
            hour = int(time_part.split('-')[0])
            minute = int(time_part.split('-')[1])
            if (hour == 13 and minute >= 30) or (hour == 14) or (hour == 15):
                target_bins.append(f)
                print(f"  找到目标日志: {basename}")
        except (IndexError, ValueError):
            continue
    
    if not target_bins:
        print("  未找到目标时间范围内的 .bin 文件!")
        print("  尝试查找所有 .bin 文件...")
        target_bins = sorted(glob.glob(os.path.join(log_dir, '*.bin')))
        if target_bins:
            # 使用最大的那个
            target_bins = [max(target_bins, key=os.path.getsize)]
            print(f"  使用最大的日志: {os.path.basename(target_bins[0])}")
    
    # 解析所有目标日志
    all_dfs = {}
    for bin_file in target_bins:
        print(f"\n--- 解析 {os.path.basename(bin_file)} ---")
        dfs = parse_bin_file(bin_file)
        
        # 合并到总数据
        for key, df in dfs.items():
            if key in all_dfs:
                all_dfs[key] = pd.concat([all_dfs[key], df], ignore_index=True)
            else:
                all_dfs[key] = df
    
    # 按时间排序并去重
    for key in all_dfs:
        all_dfs[key] = all_dfs[key].sort_values('timestamp').drop_duplicates(subset='timestamp').reset_index(drop=True)
    
    print(f"\n合并后的数据统计:")
    for key, df in all_dfs.items():
        duration = df['timestamp'].max() - df['timestamp'].min()
        hz = len(df) / duration if duration > 0 else 0
        print(f"  {key}: {len(df)} 条, {duration:.1f}s, ~{hz:.1f} Hz")
    
    # 时间对齐与重采样
    merged = merge_and_resample(all_dfs)
    
    if merged is None:
        print("错误: 数据合并失败!")
        sys.exit(1)
    
    # 检查关键字段
    required_cols = ['time', 'psi', 'u', 'r', 'tau_X', 'tau_N']
    missing = [c for c in required_cols if c not in merged.columns]
    if missing:
        print(f"  警告: 缺少关键字段: {missing}")
        print(f"  可用字段: {list(merged.columns)}")
    
    # 保存处理后的数据
    csv_path = os.path.join(output_dir, 'processed_data.csv')
    merged.to_csv(csv_path, index=False)
    print(f"\n[OK] 处理后数据已保存: {csv_path}")
    print(f"  总采样点: {len(merged)}")
    print(f"  总时长: {merged['time'].iloc[-1]:.1f} 秒")
    print(f"  字段列表: {list(merged.columns)}")
    
    # 统计摘要
    print(f"\n=== 数据统计摘要 ===")
    for col in ['u', 'v', 'r', 'tau_X', 'tau_N', 'psi']:
        if col in merged.columns:
            vals = merged[col].dropna()
            print(f"  {col:>8s}: mean={vals.mean():>8.3f}, std={vals.std():>8.3f}, "
                  f"min={vals.min():>8.3f}, max={vals.max():>8.3f}")
    
    # 绘制概览图
    plot_path = plot_data_overview(merged, output_dir)
    
    print(f"\n{'=' * 60}")
    print("阶段1 完成！")
    print(f"{'=' * 60}")
    print(f"  输出文件:")
    print(f"    - {csv_path}")
    print(f"    - {plot_path}")


if __name__ == '__main__':
    main()
