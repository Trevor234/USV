#!/usr/bin/env python3
"""只读 FCU 状态采样探针。

由维护 driver 以 trevor 身份、绑定后的生产 DDS 环境调用；只订阅
/mavros/state，不发任何服务请求、不发布话题、不写文件。

输出（stdout, 单行 JSON）:
  {"ok": bool, "samples": n, "connected": bool|null, "armed": bool|null,
   "mode": str|null, "modes": [...], "elapsed_ns": int}

`safe_hold` 只有在"采到样本 + 全程 connected + 全程未解锁 + 全程 HOLD"时才为 true。
"""

from __future__ import annotations

import argparse
import json
import sys
import time


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--topic", default="/mavros/state")
    args = parser.parse_args(argv)

    try:
        import rclpy
        from mavros_msgs.msg import State
        from rclpy.node import Node
    except Exception as error:  # noqa: BLE001 - 缺依赖必须显式失败
        print(json.dumps({"ok": False, "error": f"import:{error}"}))
        return 2

    rclpy.init(args=None)
    node = Node("p1_fcu_state_probe")
    facts = {"ok": True, "samples": 0, "connected": None, "armed": None,
             "mode": None, "modes": []}
    start = time.monotonic_ns()

    def on_state(message) -> None:
        facts["samples"] += 1
        facts["connected"] = bool(message.connected) if facts["connected"] is None \
            else (facts["connected"] and bool(message.connected))
        facts["armed"] = bool(message.armed) if facts["armed"] is None \
            else (facts["armed"] or bool(message.armed))
        facts["mode"] = message.mode
        if message.mode not in facts["modes"]:
            facts["modes"].append(message.mode)

    node.create_subscription(State, args.topic, on_state, 10)
    deadline = start + int(args.seconds * 1e9)
    while rclpy.ok() and time.monotonic_ns() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_node()
    rclpy.shutdown()

    facts["elapsed_ns"] = time.monotonic_ns() - start
    facts["safe_hold"] = bool(
        facts["samples"] > 0 and facts["connected"] is True and
        facts["armed"] is False and facts["modes"] == ["HOLD"])
    print(json.dumps(facts))
    return 0 if facts["samples"] > 0 else 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
