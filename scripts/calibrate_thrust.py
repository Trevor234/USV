#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
USV 实船推力标定脚本 (Thrust Calibration Script)
-----------------------------------------------------------
功能：
  1. 通过 /mavros/rc/override 阶梯式下发 PWM 脉宽信号；
  2. 正推阶梯：从 1500 µs 逐步增加至 1900 µs（默认步长 20 µs，每阶 20s）；
  3. 中位过渡：在 1500 µs 保持 10s（水流沉降与安全冷却）；
  4. 反推阶梯：从 1500 µs 逐步降低至 1100 µs（默认步长 20 µs，每阶 20s）；
  5. 实时采集中 WeAct 功率计 (/usv/battery) 的母线电压(V)、放电电流(A)与功率(W)；
  6. 记录每个阶梯的工况数据并导出 CSV 模板供拟合；
  7. 冲突检查：自动检测并拦截 mpc_controller_node 双重发布导致的声音发抖、电机抽搐；
  8. 高频无抖动覆写（默认 20Hz 精确时钟循环），防止飞控 RC_OVERRIDE_TIME 超时回跳。
"""

import argparse
import csv
from datetime import datetime
import math
import os
import signal
import subprocess
import sys
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, qos_profile_sensor_data

try:
    from mavros_msgs.msg import OverrideRCIn, State
    from sensor_msgs.msg import BatteryState
except ImportError:
    print("[ERROR] 无法导入 mavros_msgs 或 sensor_msgs，请先 source ROS 2 工作空间！")
    sys.exit(1)


def check_conflicting_processes():
    """检查是否存在同时在发布 /mavros/rc/override 的 mpc_node 进程"""
    try:
        current_pid = os.getpid()
        res = subprocess.run(['pgrep', '-f', 'mpc_node'], stdout=subprocess.PIPE, text=True)
        pids = [int(p) for p in res.stdout.split() if int(p) != current_pid]
        return pids
    except Exception:
        return []


class ThrustCalibrator(Node):
    def __init__(self, args):
        super().__init__('thrust_calibrator_node')
        self.args = args

        # 通道与配置
        self.steering_idx = args.steering_ch  # 0 为 CH1
        self.throttle_idx = args.throttle_ch  # 2 为 CH3
        self.pwm_center = args.pwm_center
        self.rate_hz = args.rate
        self.pub_interval = 1.0 / self.rate_hz

        # WeAct 功率计读数监控 (/usv/battery)
        self.current_voltage = None
        self.current_current = None
        self.current_power = None
        self.voltage_samples = []
        self.current_samples = []
        self.power_samples = []
        self.battery_msg_count = 0

        # 飞控状态
        self.fcu_state = None

        qos_state = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=5
        )

        # 话题发布与订阅
        self.rc_pub = self.create_publisher(
            OverrideRCIn,
            '/mavros/rc/override',
            10
        )
        # 订阅 WeAct 功率计话题 (默认 /usv/battery，QoS 为 sensor_data)
        self.battery_sub = self.create_subscription(
            BatteryState,
            args.battery_topic,
            self._battery_cb,
            qos_profile_sensor_data
        )
        self.state_sub = self.create_subscription(
            State,
            '/mavros/state',
            self._state_cb,
            qos_state
        )

        # 控制变量
        self.active_pwm = self.pwm_center
        self.running = True
        self.is_overriding = False

        # 启动高频发布后台线程 (单调时钟漂移补偿，防止飞控 RC 覆写超时抖动)
        self.pub_thread = threading.Thread(target=self._publish_loop, daemon=True)
        self.pub_thread.start()

    def _battery_cb(self, msg: BatteryState):
        if not math.isnan(msg.voltage) and msg.voltage > 0.0:
            self.current_voltage = msg.voltage
            self.voltage_samples.append(msg.voltage)
            self.battery_msg_count += 1

            if not math.isnan(msg.current):
                self.current_current = msg.current
                self.current_samples.append(msg.current)
                power = msg.voltage * abs(msg.current)
                self.current_power = power
                self.power_samples.append(power)

    def _state_cb(self, msg: State):
        self.fcu_state = msg

    def _publish_loop(self):
        """精准周期时钟循环发布，消除 sleep 累积时钟抖动"""
        interval = 1.0 / self.rate_hz
        next_time = time.monotonic()
        while rclpy.ok() and self.running:
            if self.is_overriding:
                msg = OverrideRCIn()
                channels = [0] * 18
                # 舵量固定为中位 1500 (保持直行)
                channels[self.steering_idx] = self.pwm_center
                # 油门设定为当前阶梯 PWM
                channels[self.throttle_idx] = int(self.active_pwm)
                msg.channels = channels
                self.rc_pub.publish(msg)

            next_time += interval
            sleep_duration = next_time - time.monotonic()
            if sleep_duration > 0:
                time.sleep(sleep_duration)
            else:
                next_time = time.monotonic()

    def set_target_pwm(self, pwm: int):
        self.active_pwm = pwm
        self.is_overriding = True

    def release_channels(self):
        """释放 RC 控制权（发送全 0）"""
        self.is_overriding = False
        msg = OverrideRCIn()
        msg.channels = [0] * 18
        for _ in range(5):
            self.rc_pub.publish(msg)
            time.sleep(0.04)

    def emergency_stop(self):
        """急停：先回中，再释放"""
        self.get_logger().warn("[安全防护] 触发急停：回中 1500 µs 并释放 RC 控制权...")
        self.active_pwm = self.pwm_center
        time.sleep(0.5)
        self.release_channels()


def run_calibration(node: ThrustCalibrator, args):
    stages = []

    # 1. 正推阶梯: 1500 -> 1900 (步长 +step)
    if not args.skip_forward:
        fwd_pwms = list(range(args.pwm_center, args.pwm_max + 1, args.step))
        for p in fwd_pwms:
            stages.append(('FORWARD', p))

    # 2. 中位过渡冷却阶
    if not args.skip_forward and not args.skip_reverse:
        stages.append(('COOLDOWN', args.pwm_center))

    # 3. 反推阶梯: 1500 -> 1100 (步长 -step)
    if not args.skip_reverse:
        rev_pwms = list(range(args.pwm_center, args.pwm_min - 1, -args.step))
        for p in rev_pwms:
            stages.append(('REVERSE', p))

    total_steps = len(stages)
    print("\n" + "=" * 70)
    print("        USV 实船双机系柱推力阶梯标定程序 (Thrust Calibration)")
    print("=" * 70)
    print(f"  * 控制话题       : /mavros/rc/override (发送频率: {args.rate:.0f} Hz)")
    print(f"  * 转向通道 CH1   : 索引 {args.steering_ch} (固定 {args.pwm_center} µs 居中)")
    print(f"  * 油门通道 CH3   : 索引 {args.throttle_ch}")
    print(f"  * 功率计话题     : {args.battery_topic} (WeAct PowerMonitorMini)")
    print(f"  * 阶梯步长       : {args.step} µs")
    print(f"  * 单阶持续时长   : {args.duration} s")
    print(f"  * 正推区间       : {args.pwm_center} -> {args.pwm_max} µs (含 {len(list(range(args.pwm_center, args.pwm_max + 1, args.step)))} 阶)")
    print(f"  * 反推区间       : {args.pwm_center} -> {args.pwm_min} µs (含 {len(list(range(args.pwm_center, args.pwm_min - 1, -args.step)))} 阶)")
    print(f"  * 总测试阶梯数   : {total_steps} 个阶段")
    est_total_min = (total_steps * args.duration) / 60.0
    print(f"  * 预计总耗时     : 约 {est_total_min:.1f} 分钟")
    print("=" * 70)

    # 1. 冲突进程排查 (解决"声音一抖一抖"的最核心诱因)
    conflicting_pids = check_conflicting_processes()
    if conflicting_pids:
        print("\n\033[1;31m" + "!" * 70)
        print("【严重冲突警告】检测到后台正在运行 MPC 控制器进程！")
        print(f"  冲突进程 PID: {conflicting_pids}")
        print("  根因说明: 当船体解锁时，后台的 mpc_node 会以 5Hz 持续向 /mavros/rc/override")
        print("           发布 1500µs (停船中立指令)，与本标定脚本目标 PWM 剧烈冲突交替横跳，")
        print("           从而直接导致电机转速忽高忽低、发出『一抖一抖』的剧烈抽搐声！")
        print("  【必须执行解决步骤】:")
        print(f"    方案 1: 临时挂起 MPC:   kill -STOP {conflicting_pids[0]}")
        print("            (标定结束后恢复: kill -CONT %d)" % conflicting_pids[0])
        print("    方案 2: 停止系统服务:   sudo systemctl stop usv-system")
        print("!" * 70 + "\033[0m\n")
        confirm = input("若您尚未关闭冲突进程，请按 Ctrl+C 退出；若已停止/挂起，请输入 'yes' 继续: ")
        if confirm.strip().lower() != 'yes':
            print("用户取消执行，退出脚本。")
            return

    # 2. 传感器与状态检查 (等待 1.0 秒)
    time.sleep(1.0)
    print("\n【系统状态就绪检查】")
    if node.fcu_state:
        print(f"  * 飞控模式     : {node.fcu_state.mode} | 解锁状态: {'已解锁(ARMED)' if node.fcu_state.armed else '未解锁(DISARMED)'}")
        if node.fcu_state.mode != "MANUAL":
            print(f"    [警告] 当前飞控模式为 {node.fcu_state.mode}，方案 B RC Override 通常需要在 MANUAL 模式！")
        if not node.fcu_state.armed:
            print(f"    [警告] 飞控尚未解锁 (DISARMED)，下发 PWM 推进器可能不会旋转！")
    else:
        print("  * 飞控状态     : 暂未收到 /mavros/state，请确认 MAVROS 节点已正常启动。")

    if node.battery_msg_count > 0 and node.current_voltage is not None:
        curr_str = f"{node.current_current:+.2f}A" if node.current_current is not None else "N/A"
        pwr_str = f"{node.current_power:.1f}W" if node.current_power is not None else "N/A"
        print(f"  * WeAct 功率计 : [正常连接] 实时电压: {node.current_voltage:.2f}V, 电流: {curr_str}, 功率: {pwr_str}")
    else:
        print(f"  * WeAct 功率计 : [未收到数据] 话题 {args.battery_topic} 尚无消息！")
    print("=" * 70)

    print("\n【安全操作清单】")
    print("  1. 船体已通过系柱缆绳牢固系于码头/拉力计，拉力绳水平共线；")
    print("  2. 双舷螺旋桨已完全浸入水中且周围无人员、缆绳及漂浮物；")
    print("  3. 遥控器摇杆严格回中（防止遥控器物理打杆抢控）；")
    print("  4. 随时按 Ctrl+C 可立即急停并释放通道。\n")

    input(">> 确认所有准备就绪，按 [Enter] 键开始倒计时...")

    for i in range(5, 0, -1):
        print(f">> 距离标定开始还剩 {i} 秒... (按 Ctrl+C 随时取消)", end="\r")
        time.sleep(1.0)
    print("\n>> 标定正式开始！\n")

    log_records = []

    try:
        step_idx = 0
        for stage_name, target_pwm in stages:
            step_idx += 1
            is_cooldown = (stage_name == 'COOLDOWN')
            step_dur = args.cooldown if is_cooldown else args.duration

            node.voltage_samples.clear()
            node.current_samples.clear()
            node.power_samples.clear()

            node.set_target_pwm(target_pwm)
            step_start = time.time()

            stage_tag = "[正向推力]" if stage_name == 'FORWARD' else ("[中位过渡]" if is_cooldown else "[反向推力]")

            while time.time() - step_start < step_dur:
                elapsed = time.time() - step_start
                remain = max(0.0, step_dur - elapsed)

                volt_str = f"{node.current_voltage:.2f}V" if node.current_voltage is not None else "N/A"
                curr_str = f"{node.current_current:+.2f}A" if node.current_current is not None else "N/A"
                pwr_str = f"{node.current_power:4.1f}W" if node.current_power is not None else "N/A"

                progress_bar = "#" * int((elapsed / step_dur) * 16)
                progress_bar = progress_bar.ljust(16, '-')

                print(
                    f"\r{stage_tag} [{step_idx:02d}/{total_steps:02d}] "
                    f"PWM: {target_pwm:4d} µs | [{progress_bar}] {elapsed:4.1f}s/{step_dur:4.1f}s | "
                    f"功率计: {volt_str}, {curr_str}, {pwr_str} | (记录拉力)",
                    end="",
                    flush=True
                )
                time.sleep(0.2)

            step_end = time.time()
            avg_volt = sum(node.voltage_samples) / len(node.voltage_samples) if node.voltage_samples else None
            avg_curr = sum(node.current_samples) / len(node.current_samples) if node.current_samples else None
            avg_pwr = sum(node.power_samples) / len(node.power_samples) if node.power_samples else None

            print()

            if not is_cooldown:
                log_records.append({
                    'step': step_idx,
                    'stage': stage_name,
                    'target_pwm': target_pwm,
                    'duration_s': round(step_end - step_start, 2),
                    'avg_voltage_v': round(avg_volt, 3) if avg_volt is not None else "N/A",
                    'avg_current_a': round(avg_curr, 3) if avg_curr is not None else "N/A",
                    'avg_power_w': round(avg_pwr, 2) if avg_pwr is not None else "N/A",
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

        print("\n" + "=" * 70)
        print(">> 所有测试阶梯已执行完毕！正在平稳回中并释放通道...")
        node.set_target_pwm(args.pwm_center)
        time.sleep(2.0)
        node.release_channels()
        print(">> 通道已释放，标定程序顺利结束。")
        print("=" * 70)

    except KeyboardInterrupt:
        print("\n\n[!] 捕获到用户中断 (Ctrl+C)！")
        node.emergency_stop()
        print("[!] 已安全回中并释放 RC 通道。")

    finally:
        node.release_channels()
        node.running = False

    # 导出 CSV
    if log_records:
        csv_path = args.output_csv
        if not csv_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = f"thrust_calib_log_{ts}.csv"

        try:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                fieldnames = [
                    'step', 'stage', 'target_pwm', 'duration_s',
                    'avg_voltage_v', 'avg_current_a', 'avg_power_w',
                    'timestamp', 'measured_thrust_n'
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for r in log_records:
                    r['measured_thrust_n'] = ""
                    writer.writerow(r)
            print(f"\n[数据导出] 标定记录已保存至: {os.path.abspath(csv_path)}")
            print("  提示：请在 CSV 的 'measured_thrust_n' 列中填入实测拉力值(N)，用于拟合模型。")
        except Exception as e:
            print(f"[警告] CSV 文件写入失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="USV 实船推力标定脚本 (阶梯式 PWM 下发与 WeAct 功率计读数记录)")
    parser.add_argument('--step', type=int, default=20, help="PWM 阶梯步长 (µs, 默认: 20)")
    parser.add_argument('--duration', type=float, default=20.0, help="每阶梯保持时长 (秒, 默认: 20.0)")
    parser.add_argument('--cooldown', type=float, default=10.0, help="正反推之间的 1500µs 中位冷却时长 (秒, 默认: 10.0)")
    parser.add_argument('--pwm-center', type=int, default=1500, help="中位 PWM (µs, 默认: 1500)")
    parser.add_argument('--pwm-max', type=int, default=1900, help="正推最大 PWM (µs, 默认: 1900)")
    parser.add_argument('--pwm-min', type=int, default=1100, help="反推最小 PWM (µs, 默认: 1100)")
    parser.add_argument('--throttle-ch', type=int, default=2, help="油门 RC 通道索引 (默认: 2, 对应 CH3)")
    parser.add_argument('--steering-ch', type=int, default=0, help="转向 RC 通道索引 (默认: 0, 对应 CH1)")
    parser.add_argument('--battery-topic', type=str, default="/usv/battery", help="WeAct 功率计话题 (默认: /usv/battery)")
    parser.add_argument('--rate', type=float, default=20.0, help="RC Override 发送频率 (Hz, 默认: 20.0)")
    parser.add_argument('--skip-forward', action='store_true', help="跳过正推阶梯 (仅测反推)")
    parser.add_argument('--skip-reverse', action='store_true', help="跳过反推阶梯 (仅测正推)")
    parser.add_argument('--output-csv', type=str, default="", help="保存记录的 CSV 路径 (默认自动按时间戳命名)")

    args = parser.parse_args()

    if args.step <= 0:
        print("[错误] 步长 --step 必须大于 0！")
        sys.exit(1)
    if args.pwm_min >= args.pwm_center or args.pwm_center >= args.pwm_max:
        print("[错误] PWM 范围非法: 必须满足 pwm_min < pwm_center < pwm_max！")
        sys.exit(1)

    rclpy.init()
    node = ThrustCalibrator(args)

    spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin_thread.start()

    run_calibration(node, args)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
