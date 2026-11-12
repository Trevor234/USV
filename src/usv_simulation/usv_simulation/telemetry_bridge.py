"""USV 遥测桥接节点。

复用 usv_simulation.visualizer.USVVisualizer 的全部采集逻辑(订阅 11 类话题)，
按 5 Hz 打包成结构化 JSON，经裸 TCP 转发给地面站(usv_gcs)。

帧格式: [4 字节大端长度][UTF-8 JSON]，与地面站 TcpSource 的解析器完全对齐。
监听 127.0.0.1:8765，配合 frpc 的 tcp 代理(remotePort 7865)对外暴露。

帧类型(2026-09-04 新增):
    {"kind":"tm", ...}                 遥测快照，原有字段不变，只多一个 kind 标记
    {"kind":"log","lines":["..."]}     艇载 journalctl 日志行，与遥测复用同一条 TCP

地面站按 kind 分流；没有 kind 字段的旧帧一律按遥测处理，保证向后兼容。

艇载日志为什么改走遥测通道:
    原先日志经 8766 的 stcp 控制通道(usv_control.py 的 "L" 命令)推送。该通道连同
    A/B 方案遥控已于 2026-09-04 一并移除，日志改为搭遥测的顺风车，少一条穿透链路、
    少一个要维护的守护进程。

用法:
  ros2 run usv_simulation telemetry_bridge
  ros2 run usv_simulation telemetry_bridge --port 8765 --rate 5
  ros2 run usv_simulation telemetry_bridge --log-unit usv-system
  ros2 run usv_simulation telemetry_bridge --no-log        # 关闭日志跟随
  ros2 run usv_simulation telemetry_bridge --ros-args -p odom_topic:=/mavros/local_position/odom

设计要点:
  - 轨迹增量发送: 只发 history 中新增的点，不重发整段航迹。
  - 参考路径带 hash: 内容未变时只发 hash 不发 pts，省带宽。
  - RTCM 只发统计量(last_bytes/total/rate/age)，绝不转发原始差分字节。
  - 日志按客户端各自游标分发: 多地面站同时连也各拿全量，不互相抢。
"""

import argparse
import hashlib
import json
import socketserver
import struct
import subprocess
import threading
import time

import rclpy
from rclpy.executors import SingleThreadedExecutor

from usv_simulation.visualizer import USVVisualizer

LOG_BUFFER_MAX = 2000


class TelemetryHandler(socketserver.StreamRequestHandler):
    """每个地面站连接对应一个 handler，持续推送最新帧与日志行。"""

    def handle(self):
        self.server._add_client()
        self.server._log(f"地面站已连接 {self.client_address[0]}")
        last_ver = -1
        # 新客户端只收连接之后产生的日志(不看历史), 与旧版 stcp 日志流行为一致
        log_pos = self.server._log_next
        try:
            while not self.server._shutdown:
                lines, log_pos = self.server.logs_since(log_pos)
                if lines:
                    try:
                        self.wfile.write(_frame({"kind": "log", "lines": lines}))
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionError, OSError):
                        break

                pkt, ver = self.server._latest()
                if ver != last_ver:
                    try:
                        self.wfile.write(pkt)
                        self.wfile.flush()
                        last_ver = ver
                    except (BrokenPipeError, ConnectionError, OSError):
                        break
                time.sleep(0.02)
        finally:
            self.server._remove_client()
            self.server._log(f"地面站断开 {self.client_address[0]}")


class TelemetryServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, addr, logger=None):
        super().__init__(addr, TelemetryHandler)
        self._lock = threading.Lock()
        self._pkt = b""
        self._ver = 0
        self._shutdown = False
        self._clients = 0
        self._logger = logger
        # 日志环形缓冲: _logs[0] 对应全局序号 _log_base, 下一条序号为 _log_next
        self._logs = []
        self._log_base = 0
        self._log_next = 0

    def _latest(self):
        with self._lock:
            return self._pkt, self._ver

    def update(self, data: bytes):
        with self._lock:
            self._pkt = data
            self._ver += 1

    # ---- 日志缓冲 ----

    def push_logs(self, lines):
        with self._lock:
            for line in lines:
                self._logs.append(line)
                self._log_next += 1
            overflow = len(self._logs) - LOG_BUFFER_MAX
            if overflow > 0:
                del self._logs[:overflow]
                self._log_base += overflow

    def logs_since(self, pos):
        """返回 (自 pos 起的新日志行, 新的游标)。落后超出缓冲区时从缓冲区头开始。"""
        with self._lock:
            if pos < self._log_base:
                pos = self._log_base
            start = pos - self._log_base
            if start >= len(self._logs):
                return [], self._log_next
            return list(self._logs[start:]), self._log_next

    # ---- 连接管理 ----

    def _add_client(self):
        with self._lock:
            self._clients += 1

    def _remove_client(self):
        with self._lock:
            self._clients -= 1

    def client_count(self):
        with self._lock:
            return self._clients

    def shutdown(self):
        self._shutdown = True
        super().shutdown()

    def _log(self, msg: str):
        if self._logger is not None:
            self._logger.info(msg)


# 2026-11-11 P3: 本节点自身日志的识别关键字。
# 为什么要过滤: journalctl -u usv-system -f 会把 telemetry_bridge 自己写进该
# 单元的日志一并拉回来, 再推给地面站, 形成自激回声(每轮心跳都被自己的采集端
# 采到, 白白刷掉日志环形缓冲, 地面站看到大量重复 seq= 行)。此处直接丢弃。
_SELF_LOG_MARKERS = ("usv_telemetry_bridge", "telemetry_bridge-", "telemetry_bridge]")


def _is_self_log(line: str) -> bool:
    return any(m in line for m in _SELF_LOG_MARKERS)


def _journal_tailer(server: TelemetryServer, logger, unit: str, stop_event: threading.Event):
    """跟随 journalctl -u <unit> -f，把每行推进服务器日志缓冲。

    journalctl 退出(如服务重启导致 fd 失效)时自动重拉，保证长期在船不断流。
    本节点自身产生的日志行会被过滤, 避免自激回声(见 _SELF_LOG_MARKERS)。
    """
    cmd = ["journalctl", "-u", unit, "-f", "-n", "0", "--no-pager", "-o", "short"]
    while not stop_event.is_set():
        proc = None
        try:
            proc = subprocess.Popen(cmd,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL,
                                    text=True,
                                    errors="replace",
                                    bufsize=1)
            for line in proc.stdout:
                if stop_event.is_set():
                    break
                line = line.rstrip("\r\n")
                if line and not _is_self_log(line):
                    server.push_logs([line])
        except Exception as exc:  # noqa: BLE001 - 跟随线程不能因异常退出
            if logger is not None:
                logger.warning(f"日志跟随异常: {exc}")
        finally:
            if proc is not None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:  # noqa: BLE001
                    try:
                        proc.kill()
                    except Exception:  # noqa: BLE001
                        pass
        if not stop_event.is_set():
            time.sleep(2.0)


def _frame(obj: dict) -> bytes:
    data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    return struct.pack(">I", len(data)) + data


def _path_hash(pts) -> str:
    if not pts:
        return ""
    h = hashlib.md5()
    for p in pts[:512]:
        h.update(struct.pack("<dd", float(p[0]), float(p[1])))
    return h.hexdigest()[:8]


def main(args=None):
    parser = argparse.ArgumentParser(description="USV 遥测桥接节点")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址(默认 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="监听端口(默认 8765)")
    parser.add_argument("--rate", type=float, default=5.0, help="打包频率 Hz(默认 5)")
    parser.add_argument("--log-unit", default="usv-system",
                        help="跟随日志的 systemd 单元(默认 usv-system)")
    parser.add_argument("--no-log", action="store_true", help="关闭艇载日志跟随")
    cli, ros_argv = parser.parse_known_args()

    if cli.rate <= 0 or cli.rate > 50:
        raise SystemExit(f"非法速率 {cli.rate}，应在 (0, 50] Hz")

    rclpy.init(args=ros_argv)

    # 复用采集类: 它已订阅 odom/ref/mpc_traj/mission/mpc_status/cmd_vel/
    # thrust/rtcm/gps_fix/gps_raw 全部话题，并维护内部状态。
    collector = USVVisualizer()
    collector.get_logger().info(
        f"遥测桥接启动 | 监听 {cli.host}:{cli.port} | 速率 {cli.rate} Hz | "
        f"日志={'关' if cli.no_log else cli.log_unit}"
    )

    server = TelemetryServer((cli.host, cli.port), logger=collector.get_logger())
    srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
    srv_thread.start()

    stop_event = threading.Event()
    log_thread = None
    if not cli.no_log:
        log_thread = threading.Thread(
            target=_journal_tailer,
            args=(server, collector.get_logger(), cli.log_unit, stop_event),
            daemon=True,
        )
        log_thread.start()

    state = {"seq": 0, "last_track": 0, "last_ref_hash": ""}
    last_log = 0.0
    period = 1.0 / cli.rate

    def on_tick():
        nonlocal last_log
        try:
            snap = collector.snapshot(track_since=state["last_track"])
        except Exception as exc:
            collector.get_logger().error(f"快照失败: {exc}", throttle_duration_sec=5.0)
            return

        state["seq"] += 1
        snap["seq"] = state["seq"]
        snap["t"] = time.time()
        snap["kind"] = "tm"   # 帧类型标记, 与日志帧区分

        # 参考路径: 内容未变则只发 hash，不发 pts
        ref_obj = snap["paths"].get("ref", {})
        ref_pts = ref_obj.get("pts", [])
        h = _path_hash(ref_pts)
        if h and h == state["last_ref_hash"]:
            snap["paths"]["ref"] = {"h": h}
        else:
            ref_obj["h"] = h
            state["last_ref_hash"] = h

        # 轨迹增量: 更新已发送计数
        state["last_track"] += len(snap["track"].get("append", []))

        server.update(_frame(snap))

        now = time.monotonic()
        # 2026-11-11 P3: 5s -> 300s。原值每小时产出 720 行心跳日志, 全部进
        # journal 并被采集端反复搬运, 属于纯噪声。改成 5 分钟一次后仍有
        # 存活信号, 日志量降到原来的 1/60。
        if now - last_log > 300.0:
            last_log = now
            n = len(snap["track"].get("append", []))
            collector.get_logger().info(
                f"seq={state['seq']} 客户端={server.client_count()} "
                f"新增轨迹={n} 总轨迹={state['last_track']}"
            )

    collector.create_timer(period, on_tick)

    executor = SingleThreadedExecutor()
    executor.add_node(collector)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        server.shutdown()
        srv_thread.join(timeout=1.0)
        if log_thread is not None:
            log_thread.join(timeout=3.0)
        collector.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
