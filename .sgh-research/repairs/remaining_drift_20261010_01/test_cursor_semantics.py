"""Offline semantic regression of the actual snapshot and timer callback bodies.

No ROS module is imported, no node/socket/process is started. Expected point
sequences are explicit acceptance criteria, rather than the cursor algorithm.
The audited source strings are compiled after extracting just the pure callbacks.
"""

import ast
from collections import deque
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict


BASE = Path(__file__).resolve().parents[1]
AUDIT = BASE / "drift_impact_audit_20261010_01/remote_readonly_investigation.json"
BRIDGE = BASE.parent / "a_feasibility_2026-10-03/remote_snapshot/usv_mpc_ws/src/usv_simulation/usv_simulation/telemetry_bridge.py"


def propose(visualizer, bridge):
    old_return = '"track": {"append": track_append},'
    new_return = '"track": {"append": track_append, "next": history_total},'
    assert visualizer.count(old_return) == 1
    visualizer = visualizer.replace(old_return, new_return)
    old_capture = '        hist = list(self._history)'
    assert visualizer.count(old_capture) == 1
    visualizer = visualizer.replace(old_capture, old_capture + '\n        history_total = self._history_total')
    old_base = 'evicted = max(0, self._history_total - len(hist))'
    assert visualizer.count(old_base) == 1
    visualizer = visualizer.replace(old_base, 'evicted = max(0, history_total - len(hist))')
    old_doc = '''        track_since 用于增量轨迹：只返回 history 中该索引之后的新增点，
        避免每帧重发整段航迹。返回字典与地面站 usv_gcs 的数据契约对齐。'''
    new_doc = '''        track_since 是绝对累计样本游标，返回仍保留的新增点；track.next
        是本次快照的下一绝对游标。消费者成功提交帧后应采用 next，不能
        用 append 长度推进游标，因为有界 history 可能已经逐出旧点。
        返回字典与地面站 usv_gcs 的数据契约对齐。'''
    assert visualizer.count(old_doc) == 1
    visualizer = visualizer.replace(old_doc, new_doc)
    old_advance = '''        # 轨迹增量: 更新已发送计数
        state["last_track"] += len(snap["track"].get("append", []))

        server.update(_frame(snap))'''
    new_advance = '''        # 先序列化并提交帧，再使用本次快照的绝对游标。
        # deque 逐出旧点后 append 长度不等于累计新增数。
        server.update(_frame(snap))
        state["last_track"] = snap["track"]["next"]'''
    assert bridge.count(old_advance) == 1
    return visualizer, bridge.replace(old_advance, new_advance)


def extract_function(source, names):
    tree = ast.parse(source)
    result = {}
    for item in ast.walk(tree):
        if isinstance(item, ast.FunctionDef) and item.name in names:
            # The timer's nonlocal declaration refers to main(); make its test
            # binding global while leaving all operational statements intact.
            item.body = [
                ast.Global(names=x.names) if isinstance(x, ast.Nonlocal) else x
                for x in item.body
            ]
            result[item.name] = item
    assert set(result) == set(names)
    module = ast.Module(body=list(result.values()), type_ignores=[])
    ast.fix_missing_locations(module)
    return compile(module, "<audited callback bodies>", "exec")


class Logger:
    def info(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class Server:
    def __init__(self):
        self.frames = []

    def update(self, frame):
        self.frames.append(frame)

    def client_count(self):
        return 1


def fixture(visualizer, bridge, capacity):
    ns = {
        "Any": Any, "Dict": Dict, "Odometry": object,
        "math": __import__("math"), "time": SimpleNamespace(monotonic=lambda: 0.0, time=lambda: 0.0),
    }
    exec(extract_function(visualizer, {"_odom_callback", "snapshot"}), ns)
    node = SimpleNamespace(
        _history=deque(maxlen=capacity), _history_total=0,
        _x=0.0, _y=0.0, _psi=0.0, _u=0.0, _v=0.0, _r=0.0,
        _mpc_status={}, _gps_raw=None, _gps_fix_status=None,
        _gps_fix_llh=None, _rtcm_last_size=0, _rtcm_total_bytes=0,
        _topic_stats={}, _ref_path=[], _mpc_traj=[], _mission_waypoints=[],
        _cmd_vel=None, _rtcm_rate_bps=lambda now: 0.0,
        _mark_topic=lambda name: None, get_logger=lambda: Logger(),
    )
    node.snapshot = lambda track_since: ns["snapshot"](node, track_since)
    ns.update(collector=node, server=Server(), state={"seq": 0, "last_track": 0, "last_ref_hash": ""},
              last_log=0.0, _path_hash=lambda pts: "", _frame=lambda snap: snap)
    exec(extract_function(bridge, {"on_tick"}), ns)

    def point(seq):
        p = SimpleNamespace(x=float(seq), y=float(seq * 10))
        q = SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0)
        vel = SimpleNamespace(linear=SimpleNamespace(x=0.0, y=0.0), angular=SimpleNamespace(z=0.0))
        msg = SimpleNamespace(pose=SimpleNamespace(pose=SimpleNamespace(position=p, orientation=q)),
                              twist=SimpleNamespace(twist=vel))
        ns["_odom_callback"](node, msg)

    def tick():
        ns["on_tick"]()
        return [p[0] for p in ns["server"].frames[-1]["track"]["append"]]

    return node, ns, point, tick


def run_sequences(visualizer, bridge):
    cases = []

    def evaluate(name, capacity, steps):
        node, ns, point, tick = fixture(visualizer, bridge, capacity)
        checks = []
        for insert, expected, expected_cursor in steps:
            for seq in insert:
                point(seq)
            actual = tick()
            checks.append({"expected": expected, "actual": actual,
                           "expected_cursor": expected_cursor,
                           "actual_cursor": ns["state"]["last_track"],
                           "passed": actual == expected and ns["state"]["last_track"] == expected_cursor})
        cases.append({"name": name, "passed": all(x["passed"] for x in checks), "checks": checks})

    evaluate("normal delta at and across wrap", 3, [
        ([1, 2], [1.0, 2.0], 2), ([], [], 2), ([3, 4], [3.0, 4.0], 4),
        ([5], [5.0], 5), ([], [], 5),
    ])
    evaluate("startup backlog already exceeds retention", 3, [
        ([1, 2, 3, 4, 5, 6], [4.0, 5.0, 6.0], 6), ([], [], 6),
        ([7], [7.0], 7), ([], [], 7),
    ])
    evaluate("gap after one published snapshot exceeds retention", 3, [
        ([1, 2], [1.0, 2.0], 2), ([3, 4, 5, 6, 7, 8], [6.0, 7.0, 8.0], 8),
        ([], [], 8), ([9], [9.0], 9),
    ])
    evaluate("minimum capacity survives repeated overwrites", 1, [
        ([1, 2, 3], [3.0], 3), ([], [], 3), ([4, 5], [5.0], 5),
        ([], [], 5), ([6], [6.0], 6),
    ])
    evaluate("fresh collector resets both sides together", 3, [
        ([], [], 0), ([1], [1.0], 1), ([], [], 1),
    ])
    for failure_kind in ("snapshot", "serialization", "server.update"):
        node, ns, point, tick = fixture(visualizer, bridge, 3)
        for seq in (1, 2):
            point(seq)
        assert tick() == [1.0, 2.0]
        for seq in (3, 4, 5, 6, 7, 8):
            point(seq)
        frames_before = len(ns["server"].frames)

        def fail(*args, **kwargs):
            raise RuntimeError("injected " + failure_kind + " failure")

        if failure_kind == "snapshot":
            original = node.snapshot
            node.snapshot = fail
        elif failure_kind == "serialization":
            original = ns["_frame"]
            ns["_frame"] = fail
        else:
            original = ns["server"].update
            ns["server"].update = fail
        try:
            ns["on_tick"]()
        except RuntimeError:
            pass
        failure_cursor = ns["state"]["last_track"]
        frames_after = len(ns["server"].frames)
        if failure_kind == "snapshot":
            node.snapshot = original
        elif failure_kind == "serialization":
            ns["_frame"] = original
        else:
            ns["server"].update = original
        recovery = tick()
        recovery_cursor = ns["state"]["last_track"]
        no_new_points = tick()
        passed = failure_cursor == 2 and frames_after == frames_before and recovery == [6.0, 7.0, 8.0] and recovery_cursor == 8 and no_new_points == []
        cases.append({"name": failure_kind + " failure does not consume retained points",
                      "passed": passed, "failure_cursor_expected": 2, "failure_cursor_actual": failure_cursor,
                      "frames_before": frames_before, "frames_after": frames_after,
                      "recovery_expected": [6.0, 7.0, 8.0], "recovery_actual": recovery,
                      "recovery_cursor_expected": 8, "recovery_cursor_actual": recovery_cursor,
                      "next_without_new_points_expected": [], "next_without_new_points_actual": no_new_points})
    return cases


def main():
    data = json.loads(AUDIT.read_text(encoding="utf-8"))
    # Collector's splitlines/join representation drops the final newline.
    visualizer = data["old_25"][24]["current_content"]["text"] + "\n"
    bridge_bytes = BRIDGE.read_bytes()
    bridge_sha = hashlib.sha256(bridge_bytes).hexdigest()
    assert bridge_sha == "28aecff3f465f6c807a13dbf76dba3a47c3fdc2044fcf79d814d640869b74306"
    bridge = bridge_bytes.decode("utf-8")
    assert hashlib.sha256(visualizer.encode()).hexdigest() == data["old_25"][24]["current_content"]["sha256"]
    proposed_visualizer, proposed_bridge = propose(visualizer, bridge)
    existing = run_sequences(visualizer, bridge)
    proposed = run_sequences(proposed_visualizer, proposed_bridge)
    assert any(not x["passed"] for x in existing)
    assert all(x["passed"] for x in proposed)
    result = {
        "schema": "visualizer-absolute-cursor-offline-semantic-regression-v1",
        "source_visualizer_sha256": hashlib.sha256(visualizer.encode()).hexdigest(),
        "source_bridge_sha256": bridge_sha, "remote_access": False,
        "ros_imported": False, "node_or_socket_started": False,
        "method": "compile actual _odom_callback, snapshot and on_tick AST bodies with inert collaborators",
        "existing": existing, "proposed": proposed,
        "scope": "point retention and bridge cursor accounting; excludes GUI rendering, DDS, socket delivery and multithreaded ROS execution",
    }
    out = Path(__file__).with_name("semantic_regression_result_v2.json")
    with out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"existing_passed": sum(x["passed"] for x in existing),
                      "proposed_passed": sum(x["passed"] for x in proposed),
                      "cases": len(proposed), "result": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
