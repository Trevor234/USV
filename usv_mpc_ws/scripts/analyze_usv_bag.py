#!/usr/bin/env python3
"""USV rosbag 分析: 跟踪误差/速度/推力/任务摘要 → PNG + 文本报告。

用法:
  python3 analyze_usv_bag.py <bag目录> [-o 输出目录]

自动识别仿真/实机话题:
  odom: /wamv/sensors/position/ground_truth_odometry 或 /mavros/local_position/odom
  推力: /wamv/thrusters/{left,right}/thrust 或 /mavros/rc/override(仅状态)
  参考: /path/reference + /path/reference_profile
  状态: /mpc/status (JSON)
需在 source 过 ROS 2 的环境中运行 (依赖 rosbag2_py 与消息类型)。
"""
import argparse
import json
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def nearest_point_distance(px, py, path_pts):
    """点到折线最近距离 (path_pts: [(x, y), ...])。"""
    best = float("inf")
    n = len(path_pts)
    for i in range(n - 1):
        x1, y1 = path_pts[i]
        x2, y2 = path_pts[i + 1]
        dx, dy = x2 - x1, y2 - y1
        seg2 = dx * dx + dy * dy
        t = 0.0
        if seg2 > 1e-12:
            t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg2))
        cx, cy = x1 + t * dx, y1 + t * dy
        d = math.hypot(px - cx, py - cy)
        if d < best:
            best = d
    if best == float("inf") and n == 1:
        best = math.hypot(px - path_pts[0][0], py - path_pts[0][1])
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bag")
    ap.add_argument("-o", "--outdir", default=None)
    args = ap.parse_args()
    bag = args.bag.rstrip("/")
    outdir = args.outdir or bag
    os.makedirs(outdir, exist_ok=True)

    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=bag, storage_id="mcap"),
        rosbag2_py.ConverterOptions("", ""),
    )
    topic_types = {t.name: t.type for t in reader.get_all_topics_and_types()}

    ODOM_CANDIDATES = [
        "/wamv/sensors/position/ground_truth_odometry",
        "/mavros/local_position/odom",
    ]
    THRUST = ["/wamv/thrusters/left/thrust", "/wamv/thrusters/right/thrust"]

    odom_t, odom_xy, odom_speed = [], [], []
    path_t, path_pts = [], []          # 最近一次参考路径 (时间戳, 点列)
    ref_t, ref_v = [], []              # 参考速度剖面采样 (t, v)
    tl_t, tl_v, tr_t, tr_v = [], [], [], []
    status_t, status = [], []
    type_map = {}

    while reader.has_next():
        topic, data, t = reader.read_next()
        tt = topic_types.get(topic)
        if tt is None:
            continue
        if topic in ODOM_CANDIDATES and tt.endswith("Odometry"):
            m = deserialize_message(data, get_message(tt))
            ts = t * 1e-9  # 录包墙钟 (header.stamp 是 gz 仿真时, 与其他话题不同基准)
            x = m.pose.pose.position.x
            y = m.pose.pose.position.y
            vx = m.twist.twist.linear.x
            vy = m.twist.twist.linear.y
            odom_t.append(ts)
            odom_xy.append((x, y))
            odom_speed.append(math.hypot(vx, vy))
        elif topic == "/path/reference" and tt.endswith("Path"):
            m = deserialize_message(data, get_message(tt))
            pts = [(p.pose.position.x, p.pose.position.y) for p in m.poses]
            if len(pts) >= 2:
                path_t.append(t * 1e-9)
                path_pts.append(pts)
        elif topic == "/path/reference_profile" and tt.endswith("Float64MultiArray"):
            m = deserialize_message(data, get_message(tt))
            data4 = m.data
            if len(data4) >= 4 and len(data4) % 4 == 0:
                n = len(data4) // 4
                t0_p = t * 1e-9
                ref_t = [t0_p + data4[4 * i + 3] for i in range(n)]
                ref_v = [data4[4 * i] for i in range(n)]
        elif topic in THRUST and tt.endswith("Float64"):
            m = deserialize_message(data, get_message(tt))
            ts = t * 1e-9
            if topic == THRUST[0]:
                tl_t.append(ts); tl_v.append(m.data)
            else:
                tr_t.append(ts); tr_v.append(m.data)
        elif topic == "/mpc/status" and tt.endswith("String"):
            m = deserialize_message(data, get_message(tt))
            try:
                status_t.append(t * 1e-9)
                status.append(json.loads(m.data))
            except Exception:
                pass

    if not odom_t:
        print("bag 中没有里程计数据 (odom 话题缺失或为空)")
        return 1

    # 参考路径: 取"最后一条非空路径"作为任务参考 (与 MPC 跟踪对象一致)
    ref = path_pts[-1] if path_pts else []

    # 逐 odom 采样计算横距误差 (只对存在参考路径时段计算)
    cte_t, cte = [], []
    path_intervals = list(zip(path_t[:-1], path_t[1:])) + (
        [(path_t[-1], float("inf"))] if path_t else [])
    for (ts, (x, y)) in zip(odom_t, odom_xy):
        for a, b in path_intervals:
            if a <= ts < b:
                if path_pts and b != float("inf"):
                    idx = min(len(path_intervals) - 1,
                              [i for i, (pa, pb) in enumerate(path_intervals)
                               if pa <= ts < pb][0])
                    if idx < len(path_pts) and path_pts[idx]:
                        cte_t.append(ts)
                        cte.append(nearest_point_distance(x, y, path_pts[idx]))
                break

    t0 = odom_t[0]
    rel = [t - t0 for t in odom_t]
    cte_rel = [t - t0 for t in cte_t]

    # ---- 统计 ----
    lines = [f"bag: {bag}", f"时长: {odom_t[-1]-t0:.1f} s, odom 采样 {len(odom_t)}"]
    if status:
        active = [s for s in status if s.get("state") == "ACTIVE"]
        lines.append(f"MPC 状态: ACTIVE {len(active)} 帧 / 共 {len(status)} 帧")
        fails = [s.get("fail_count", 0) for s in active] or [0]
        sol = [s.get("solve_time_ms", 0) for s in active] or [0]
        lines.append(f"求解: 最大 fail_count={max(fails)}, "
                     f"solve_time 均值 {sum(sol)/len(sol):.1f} ms")
    if cte:
        lines.append(f"横距误差 CTE: 均值 {sum(cte)/len(cte):.3f} m, "
                     f"最大 {max(cte):.3f} m (n={len(cte)})")
    if odom_speed:
        cruise = [v for v in odom_speed if v > 0.1]
        if cruise:
            lines.append(f"航速: 峰值 {max(odom_speed):.2f} m/s, "
                         f"巡航段均值 {sum(cruise)/len(cruise):.2f} m/s")
    if tl_v and tr_v:
        ts_ = [abs(v) for v in tl_v] + [abs(v) for v in tr_v]
        sat = sum(1 for v in ts_ if v >= 24.5) / len(ts_)
        lines.append(f"推力: |T| 均值 {sum(ts_)/len(ts_):.1f} N, 峰值 {max(ts_):.1f} N, "
                     f"饱和占比 {sat*100:.1f}% (≥24.5N)")
    report = "\n".join(lines)
    print(report)
    with open(os.path.join(outdir, "analysis_report.txt"), "w") as f:
        f.write(report + "\n")

    # ---- 图 ----
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    ax = axes[0][0]
    if ref:
        rx = [p[0] for p in ref]; ry = [p[1] for p in ref]
        ax.plot(rx, ry, "g-", lw=1, label="reference")
    ax.plot([p[0] for p in odom_xy], [p[1] for p in odom_xy], "r-", lw=1.2,
            label="actual")
    ax.plot(odom_xy[0][0], odom_xy[0][1], "k^", ms=8, label="start")
    ax.set_title("USV Trajectory"); ax.set_xlabel("East x (m)")
    ax.set_ylabel("North y (m)"); ax.axis("equal"); ax.legend(); ax.grid(True)

    ax = axes[0][1]
    if cte:
        ax.plot(cte_rel, cte, "b-", lw=1)
        ax.set_title("Cross-Track Error"); ax.set_xlabel("t (s)")
        ax.set_ylabel("CTE (m)"); ax.grid(True)

    ax = axes[1][0]
    ax.plot(rel, odom_speed, "b-", lw=1, label="speed")
    if ref_v:
        rv0 = ref_t[0]
        ax.plot([t - rv0 for t in ref_t], ref_v, "g--", lw=1, label="ref speed")
    ax.set_title("Speed"); ax.set_xlabel("t (s)"); ax.set_ylabel("m/s")
    ax.legend(); ax.grid(True)

    ax = axes[1][1]
    if tl_t:
        ax.plot([t - t0 for t in tl_t], tl_v, "r-", lw=1, label="T left")
        ax.plot([t - t0 for t in tr_t], tr_v, "b-", lw=1, label="T right")
        ax.set_title("Thrust"); ax.set_xlabel("t (s)"); ax.set_ylabel("N")
        ax.legend(); ax.grid(True)

    out_png = os.path.join(outdir, "analysis.png")
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    print(f"图: {out_png}\n报告: {os.path.join(outdir, 'analysis_report.txt')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
