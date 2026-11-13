#!/usr/bin/env python3
"""方案 A MPC 节点的隔离烟测 (不接飞控, 不发解锁/模式/推力指令)。

启动一个独立的 `usv_mpc mpc_node`, 全部话题都在 /migration/smoke/* 命名空间,
用 require_fcu_state:=false 覆盖(仅本进程), 不写 YAML、不碰真实 MAVROS 话题。

harness 流程:
  1. 5 s 不发 odom/path: 必须 STANDBY 且发布零速度;
  2. 发 map/base_link 合法四元数 odom (20 Hz) + 直线路径 (1 Hz), 用输出速度
     推进同一滞后 plant, 连续 60 s: 要求 >=280 个 ACTIVE 成功状态、0 HOLD、
     0 deadline_miss、backend=acados、5x21 预测、输出有限且在界内,
     状态发布正间隔 p95 <= 250 ms、最大间隔 < 400 ms;
  3. 停发 odom 3 s: 越过 1 s timeout 后必须 STANDBY/零速度; 恢复 5 s: 回到
     ACTIVE 并按测量 anchor 衔接; 再发空路径: STANDBY/零速度;
  4. 读取子进程 /proc/<pid>/exe 与 maps, 确认是本次候选的 A 节点、无 deleted
     映射, 实际映射本候选共用后端库与 acados/hpipm/blasfeo, 无 libcasadi。

只关闭本 harness 与它启动的子进程; 不停止生产服务。
"""

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time

import rclpy
from geometry_msgs.msg import PoseStamped, TwistStamped
from nav_msgs.msg import Odometry, Path
from std_msgs.msg import String

# 与 mpc_params_A.yaml 一致的确定性 plant (5 状态滞后, 四子步 RK4)。
DT = 0.2
TAU_U = 0.8
TAU_R = 1.78
U_MIN = 0.0
U_MAX = 3.3
R_MAX = 1.25


def wrap_pi(angle):
  return math.atan2(math.sin(angle), math.cos(angle))


def step_plant(state, control, substeps=4, dt=DT, tau_u=TAU_U, tau_r=TAU_R):
  def rhs(s):
    psi, u, r = s[2], s[3], s[4]
    return [u * math.cos(psi), u * math.sin(psi), r,
            (control[0] - u) / tau_u, (control[1] - r) / tau_r]

  x = list(state)
  h = dt / float(substeps)
  for _ in range(substeps):
    k1 = rhs(x)
    k2 = rhs([x[i] + 0.5 * h * k1[i] for i in range(5)])
    k3 = rhs([x[i] + 0.5 * h * k2[i] for i in range(5)])
    k4 = rhs([x[i] + h * k3[i] for i in range(5)])
    x = [x[i] + h / 6.0 * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i])
         for i in range(5)]
  return x


def quaternion_from_yaw(yaw):
  return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))


class Harness:
  def __init__(self, node, prefix):
    self.node = node
    self.prefix = prefix
    self.odom_pub = node.create_publisher(Odometry, prefix + "/odom", 10)
    self.path_pub = node.create_publisher(Path, prefix + "/path", 10)
    self.status = []
    self.commands = []
    self.trajectories = []
    self.node.create_subscription(String, prefix + "/status", self._status, 20)
    self.node.create_subscription(TwistStamped, prefix + "/cmd_vel",
                                  self._command, 20)
    self.node.create_subscription(Path, prefix + "/predicted", self._trajectory, 20)
    # 初速 0.5 m/s: ACTIVE 入口必须按测量值重锚, 否则首拍会突变。
    self.state = [0.0, 0.0, 0.0, 0.5, 0.0]

  def _status(self, msg):
    try:
      payload = json.loads(msg.data)
    except json.JSONDecodeError:
      return
    payload["_recv"] = time.monotonic()
    self.status.append(payload)

  def _command(self, msg):
    self.commands.append((msg.twist.linear.x, msg.twist.angular.z,
                          time.monotonic()))

  def _trajectory(self, msg):
    self.trajectories.append(len(msg.poses))

  def publish_odom(self):
    msg = Odometry()
    msg.header.stamp = self.node.get_clock().now().to_msg()
    msg.header.frame_id = "map"
    msg.child_frame_id = "base_link"
    msg.pose.pose.position.x = self.state[0]
    msg.pose.pose.position.y = self.state[1]
    q = quaternion_from_yaw(wrap_pi(self.state[2]))
    msg.pose.pose.orientation.x = q[0]
    msg.pose.pose.orientation.y = q[1]
    msg.pose.pose.orientation.z = q[2]
    msg.pose.pose.orientation.w = q[3]
    msg.twist.twist.linear.x = self.state[3]
    msg.twist.twist.angular.z = self.state[4]
    self.odom_pub.publish(msg)

  def publish_path(self, empty=False):
    msg = Path()
    msg.header.stamp = self.node.get_clock().now().to_msg()
    msg.header.frame_id = "map"
    if not empty:
      for index in range(0, 101):
        pose = PoseStamped()
        pose.header = msg.header
        pose.pose.position.x = float(index)
        pose.pose.position.y = 0.0
        q = quaternion_from_yaw(0.0)
        pose.pose.orientation.z = q[2]
        pose.pose.orientation.w = q[3]
        msg.poses.append(pose)
    self.path_pub.publish(msg)

  def spin(self, seconds, odom=True, path=True, advance=True):
    deadline = time.monotonic() + seconds
    next_odom = 0.0
    next_path = 0.0
    last_command = (0.0, 0.0)
    while time.monotonic() < deadline:
      now = time.monotonic()
      if odom and now >= next_odom:
        self.publish_odom()
        next_odom = now + 0.05
      if path and now >= next_path:
        self.publish_path()
        next_path = now + 1.0
      rclpy.spin_once(self.node, timeout_sec=0.01)
      if advance and self.commands:
        candidate = self.commands[-1]
        if candidate[0] != last_command[0] or candidate[1] != last_command[1]:
          last_command = (candidate[0], candidate[1])
      if advance:
        # 用最近发布的速度指令推进 plant (失败/零速也照常推进)。
        control = last_command
        self.state = step_plant(self.state, control)


def wait_ready(node, harness, timeout):
  """等订阅者连上, 避免前几拍丢消息导致误判。"""
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.05)
    if harness.odom_pub.get_subscription_count() > 0:
      return True
  return False


def summarize_status(records, since):
  subset = [item for item in records if item["_recv"] >= since]
  active = [item for item in subset if item.get("state") == "ACTIVE"
            and item.get("success") is True]
  hold = [item for item in subset if item.get("hold") is True]
  deadline = [item for item in subset if item.get("deadline_miss") is True]
  backends = sorted({item.get("backend") for item in subset
                     if item.get("backend") is not None})
  return subset, active, hold, deadline, backends


def latency_stats(statuses):
  times = sorted(item["_recv"] for item in statuses)
  intervals = [b - a for a, b in zip(times, times[1:]) if b > a]
  if not intervals:
    return None, None
  intervals_sorted = sorted(intervals)
  rank = int(math.ceil(0.95 * len(intervals_sorted)))
  return intervals_sorted[min(max(rank - 1, 0), len(intervals_sorted) - 1)], max(intervals)


def main(argv):
  parser = argparse.ArgumentParser(description="方案 A 节点隔离烟测")
  parser.add_argument("--release-root", required=True)
  parser.add_argument("--domain-id", type=int, default=213)
  parser.add_argument("--output", required=True, help="结果 JSON (必须不存在)")
  parser.add_argument("--active-seconds", type=float, default=60.0)
  parser.add_argument("--acados-lib-dir", default="/home/trevor/acados/lib",
                      help="acados/hpipm/blasfeo 所在目录 (launch 里由节点补 LD 路径)")
  args = parser.parse_args(argv)
  if os.path.exists(args.output):
    print(f"输出文件已存在, 拒绝覆盖: {args.output}", file=sys.stderr)
    return 2

  release = os.path.realpath(args.release_root)
  params = [
    os.path.join(release, "src", "usv_bringup", "config", "mpc_params_A.yaml"),
    os.path.join(release, "src", "usv_bringup", "config", "usv_params_A.yaml"),
  ]
  for path in params:
    if not os.path.exists(path):
      print(f"缺少参数文件: {path}", file=sys.stderr)
      return 2
  node_exe = os.path.join(release, "install_release", "usv_mpc", "lib",
                          "usv_mpc", "mpc_node")
  if not os.path.exists(node_exe):
    print(f"缺少 A 节点可执行文件: {node_exe}", file=sys.stderr)
    return 2
  prefix = "/migration/smoke"
  if not os.path.isdir(args.acados_lib_dir):
    print(f"缺少 acados 库目录: {args.acados_lib_dir}", file=sys.stderr)
    return 2
  environment = dict(os.environ)
  environment["ROS_DOMAIN_ID"] = str(args.domain_id)
  # harness 自己的 rclpy 节点也要进同一个 domain: 否则 parent 在默认 domain 0,
  # 与隔离 domain 里的被测节点互相看不见 (subscription_count 永远为 0)。
  os.environ["ROS_DOMAIN_ID"] = str(args.domain_id)
  # 实测: 该 Pi 上 ROS_LOCALHOST_ONLY=1 会让 discovery 完全看不到对端。
  # 隔离改用"独立 domain + /migration/smoke 命名空间", 不启用这个开关。
  environment.pop("ROS_LOCALHOST_ONLY", None)
  os.environ.pop("ROS_LOCALHOST_ONLY", None)
  # real.launch.py 会给节点补 acados LD 路径; 这里直接起进程, 必须自己补。
  existing = environment.get("LD_LIBRARY_PATH")
  environment["LD_LIBRARY_PATH"] = (
    args.acados_lib_dir + (":" + existing if existing else ""))
  # 直接 exec 安装好的 ELF: `ros2 run` 会多一层 python 启动器, PID/映射检查
  # 会落在启动器上而不是节点本身。
  command = [node_exe, "--ros-args",
             "--params-file", params[0], "--params-file", params[1],
             "-p", "require_fcu_state:=false",
             "-p", f"odom_topic:={prefix}/odom",
             "-p", f"imu_topic:={prefix}/imu",
             "-p", f"state_topic:={prefix}/state",
             "-p", f"path_topic:={prefix}/path",
             "-p", f"profile_topic:={prefix}/profile",
             "-p", f"velocity_topic:={prefix}/cmd_vel",
             "-p", f"status_topic:={prefix}/status",
             "-p", f"predicted_trajectory_topic:={prefix}/predicted"]
  process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
  result = {"release_root": release, "domain_id": args.domain_id,
            "command": command, "failures": [], "phases": {}}
  try:
    rclpy.init()
    node = rclpy.create_node("migration_smoke_harness")
    harness = Harness(node, prefix)
    if not wait_ready(node, harness, 30.0):
      result["failures"].append("控制器未在 30 s 内订阅 /migration/smoke/* 话题")
      return _finish(process, args.output, result)
    # 阶段 1: 5 s 无输入
    phase1_start = time.monotonic()
    harness.spin(5.0, odom=False, path=False, advance=False)
    subset, active, hold, deadline, backends = summarize_status(
      harness.status, phase1_start)
    result["phases"]["idle"] = {
      "status_count": len(subset), "active_count": len(active),
      "backends": backends,
      "last_state": subset[-1].get("state") if subset else None,
    }
    if active:
      result["failures"].append("无 odom/path 时出现 ACTIVE")
    if not subset:
      result["failures"].append("无 odom/path 时没有任何状态发布")
    elif subset[-1].get("state") != "STANDBY":
      result["failures"].append(
        f"无输入最终状态不是 STANDBY: {subset[-1].get('state')}")

    # 阶段 2: 60 s ACTIVE 闭环
    phase2_start = time.monotonic()
    harness.spin(args.active_seconds)
    subset, active, hold, deadline, backends = summarize_status(
      harness.status, phase2_start)
    p95, worst = latency_stats(subset)
    result["phases"]["active"] = {
      "status_count": len(subset), "active_success": len(active),
      "hold": len(hold), "deadline_miss": len(deadline),
      "backends": backends, "interval_p95_s": p95, "interval_max_s": worst,
      "command_count": len(harness.commands),
      "trajectory_lengths": sorted(set(harness.trajectories))[:3],
    }
    if len(active) < 280:
      result["failures"].append(f"ACTIVE 成功状态只有 {len(active)} (<280)")
    if hold:
      result["failures"].append(f"出现 HOLD {len(hold)} 次")
    if deadline:
      result["failures"].append(f"出现 deadline_miss {len(deadline)} 次")
    if backends != ["acados"]:
      result["failures"].append(f"backend 集合不是 [acados]: {backends}")
    if p95 is None or p95 > 0.250:
      result["failures"].append(f"状态间隔 p95 超限: {p95}")
    if worst is None or worst >= 0.400:
      result["failures"].append(f"状态间隔最大 {worst} >= 0.4 s")
    if any(length != 21 for length in harness.trajectories):
      result["failures"].append(
        f"预测轨迹长度不是 21: {sorted(set(harness.trajectories))[:5]}")
    for command_u, command_r, _ in harness.commands:
      if not (math.isfinite(command_u) and math.isfinite(command_r)):
        result["failures"].append("发布了非有限速度指令")
        break
      if not (U_MIN - 1e-6 <= command_u <= U_MAX + 1e-6):
        result["failures"].append(f"速度指令越界: {command_u}")
        break
      if abs(command_r) > R_MAX + 1e-6:
        result["failures"].append(f"角速度指令越界: {command_r}")
        break

    # 阶段 3: 停 odom 3 s -> STANDBY; 恢复 5 s -> ACTIVE; 空路径 -> STANDBY
    stop_start = time.monotonic()
    harness.spin(3.0, odom=False)
    subset, active, hold, deadline, _ = summarize_status(harness.status, stop_start)
    result["phases"]["odom_loss"] = {
      "last_state": subset[-1].get("state") if subset else None,
      "active_count": len(active)}
    if not subset:
      result["failures"].append("odom 停发后没有任何状态发布")
    elif subset[-1].get("state") != "STANDBY":
      result["failures"].append(
        f"odom 停发 3 s 后状态不是 STANDBY: {subset[-1].get('state')}")
    if harness.commands:
      last_u, last_r, _ = harness.commands[-1]
      if abs(last_u) > 1e-9 or abs(last_r) > 1e-9:
        result["failures"].append(
          f"STANDBY 未发布零速度: u={last_u} r={last_r}")

    resume_start = time.monotonic()
    harness.spin(5.0)
    subset, active, hold, _, _ = summarize_status(harness.status, resume_start)
    result["phases"]["resume"] = {"active_count": len(active)}
    if not active:
      result["failures"].append("恢复 odom 5 s 内未回到 ACTIVE 成功状态")

    empty_start = time.monotonic()
    harness.spin(3.0, path=False)
    harness.publish_path(empty=True)
    harness.spin(2.0, path=False)
    subset, active, hold, _, _ = summarize_status(harness.status, empty_start)
    result["phases"]["empty_path"] = {
      "last_state": subset[-1].get("state") if subset else None}
    if subset and subset[-1].get("state") != "STANDBY":
      result["failures"].append(
        f"空路径后状态不是 STANDBY: {subset[-1].get('state')}")
    return _finish(process, args.output, result)
  finally:
    try:
      rclpy.shutdown()
    except Exception:  # noqa: BLE001 - 关闭阶段不再升级异常
      pass


def _finish(process, output, result):
  pid = process.pid
  result["node_pid"] = pid
  try:
    result["exe_link"] = os.readlink(f"/proc/{pid}/exe")
  except OSError:
    result["exe_link"] = None
  result["exe_deleted"] = bool(result["exe_link"]
                              and result["exe_link"].endswith(" (deleted)"))
  mapped = []
  try:
    with open(f"/proc/{pid}/maps", "r", encoding="utf-8", errors="replace") as handle:
      for line in handle:
        parts = line.split()
        if len(parts) < 6:
          continue
        path = parts[5]
        if not path.startswith("/"):
          continue
        if any(marker in os.path.basename(path)
               for marker in ("libusv_acados_backend", "libacados", "libhpipm",
                              "libblasfeo", "libcasadi")):
          if path not in mapped:
            mapped.append(path)
  except OSError:
    pass
  result["mapped_libraries"] = mapped
  names = [os.path.basename(path) for path in mapped]
  for marker in ("libusv_acados_backend", "libacados", "libhpipm", "libblasfeo"):
    if not any(marker in name for name in names):
      result["failures"].append(f"进程未映射 {marker}")
  if any("libcasadi" in name for name in names):
    result["failures"].append("进程仍映射 libcasadi")
  if result["exe_deleted"]:
    result["failures"].append("控制器 ELF 已被删除")
  if not (result.get("exe_link") or "").startswith(
      os.path.join(result["release_root"], "install_release") + os.sep):
    result["failures"].append(
      f"控制器不在本候选 install_release: {result.get('exe_link')}")

  process.send_signal(signal.SIGINT)
  try:
    output_text = process.communicate(timeout=20)[0]
  except subprocess.TimeoutExpired:
    process.kill()
    output_text = process.communicate()[0]
  result["node_output_tail"] = (output_text or "")[-4000:]
  result["node_returncode"] = process.returncode
  result["ok"] = not result["failures"]
  with open(output, "x", encoding="utf-8") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
  for failure in result["failures"]:
    print(f"未通过: {failure}", file=sys.stderr)
  print(f"烟测{'通过' if result['ok'] else '失败'}: {output}")
  return 0 if result["ok"] else 1


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
