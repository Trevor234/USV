# Copyright 2026 USV Developer
# SPDX-License-Identifier: MIT
"""Unit tests for Scheme-A GP+PPO research baseline capture."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("capture_research_baseline.py")
WORKTREE = Path(__file__).resolve().parents[3]


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], capture_output=True, text=True)


def test_refuses_to_overwrite_existing_out_dir():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "existing"
        out.mkdir()
        (out / "keep.txt").write_text("do_not_touch", encoding="utf-8")
        res = _run(["--workspace", str(WORKTREE), "--out", str(out), "--source-only"])
        assert res.returncode == 2
        assert (out / "keep.txt").read_text(encoding="utf-8") == "do_not_touch"


def test_source_only_mode_declares_no_install_consistency():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "baseline_src"
        res = _run([
            "--workspace", str(WORKTREE),
            "--out", str(out),
            "--source-only",
            "--skip-parent-evidence",
        ])
        assert res.returncode == 0, res.stdout + res.stderr
        baseline = json.loads((out / "baseline.json").read_text(encoding="utf-8"))
        hashes = json.loads((out / "source_hashes.json").read_text(encoding="utf-8"))
        assets = json.loads((out / "asset_manifest.json").read_text(encoding="utf-8"))
        assert hashes["schema"] == "scheme-a-execution-closure-baseline-v1"
        assert len(hashes["records"]) > 0
        assert baseline["build"]["mode"] == "source-only"
        assert baseline["build"]["claims_install_consistency"] is False
        assert baseline["integrity"]["verified"] is True
        assert assets["rl_assets"]["frozen_files"]["policy_physical_n.onnx"]["sha256"].startswith("ff60e0f7")


def test_built_mode_binds_real_build_and_install():
    build_base = WORKTREE / "build" / "scheme_a"
    install_base = WORKTREE / "install" / "scheme_a"
    if not build_base.is_dir() or not install_base.is_dir():
        return
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "baseline_built"
        res = _run([
            "--workspace", str(WORKTREE),
            "--out", str(out),
            "--build-base", str(build_base),
            "--install-base", str(install_base),
        ])
        assert res.returncode == 0, res.stdout + res.stderr
        baseline = json.loads((out / "baseline.json").read_text(encoding="utf-8"))
        assert baseline["build"]["mode"] == "built"
        assert baseline["build"]["claims_install_consistency"] is True
        assert baseline["integrity"]["verified"] is True
        safety_cache = baseline["build"]["packages"]["usv_research_safety_cpp"]["cmake_cache"]
        assert safety_cache["USV_RESEARCH_TEST_SEAMS"] == "OFF"
