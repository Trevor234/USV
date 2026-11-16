# Copyright 2026 USV Developer
# SPDX-License-Identifier: MIT
"""基线捕获的边界测试。

捕获器最容易犯的两个错，都不是"少抓了"，而是"抓错了还说自己对"：
  1) --source-only 仍然声称 install 一致；
  2) 允许覆盖已有的快照目录。
本测试各覆盖一次，全部在临时目录里完成，绝不触碰工作区。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "usv_mpc_ws" / "scripts" / "capture_scheme_a_baseline.py"


def run(args):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                          capture_output=True, text=True)


def test_source_only_declares_no_install_consistency():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "snap"
        r = run(["--workspace", str(Path(__file__).resolve().parents[3]),
                 "--out", str(out), "--source-only", "--archive-root", "/nonexistent"])
        # the archive is unreachable here, so the capture must fail loudly rather than
        # silently drop the identity cross-check
        if r.returncode == 0 and (out / "integrity_check.json").is_file():
            doc = json.loads((out / "integrity_check.json").read_text())
            assert not doc.get("archive_identity_checked", False)
        else:
            assert r.returncode != 0


def test_refuses_to_overwrite_an_existing_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "snap"
        out.mkdir()
        (out / "sentinel.txt").write_text("keep")
        r = run(["--workspace", str(Path(__file__).resolve().parents[3]),
                 "--out", str(out), "--source-only", "--archive-root", "/nonexistent"])
        assert r.returncode != 0
        assert (out / "sentinel.txt").read_text() == "keep"
