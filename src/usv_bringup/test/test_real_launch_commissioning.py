"""F5/F6 回归测试：usv_bringup 条件排除凭据与 real.launch.py 后端分支语义。

只验证外部效果（安装结果文件集合、launch 实体条件评估与解析后参数），
不读取源码字符串做文本匹配。
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchContext
from launch.actions import DeclareLaunchArgument
from launch.utilities import perform_substitutions
from launch_ros.actions import Node


PKG_ROOT = Path(__file__).resolve().parents[1]
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def _load_real_launch():
    path = PKG_ROOT / "launch" / "real.launch.py"
    spec = importlib.util.spec_from_file_location("usv_bringup_real_launch", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prepare_context(ld, overrides: dict[str, str]) -> LaunchContext:
    ctx = LaunchContext()
    for entity in ld.entities:
        if isinstance(entity, DeclareLaunchArgument):
            if entity.name in overrides:
                ctx.launch_configurations[entity.name] = overrides[entity.name]
            elif entity.default_value is not None:
                ctx.launch_configurations[entity.name] = perform_substitutions(
                    ctx, entity.default_value
                )
    return ctx


def _is_enabled(entity, ctx: LaunchContext) -> bool:
    if entity.condition is None:
        return True
    return bool(entity.condition.evaluate(ctx))


def test_setup_py_keeps_secrets_by_default_and_excludes_when_gated(tmp_path):
    # F5：默认安装保留 config/*.yaml（包括 ntrip_params.yaml）；仅在
    # USV_BRINGUP_EXCLUDE_SECRETS=1 时排除凭据，保护生产 usv-rtk 重建。
    src_pkg = tmp_path / "pkg"
    shutil.copytree(
        PKG_ROOT,
        src_pkg,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"),
    )
    ntrip_cfg = src_pkg / "config" / "ntrip_params.yaml"
    ntrip_cfg.write_text("ntrip_client:\n  ros__parameters:\n    username: test\n", encoding="utf-8")

    default_install = tmp_path / "install_default"
    env_default = {k: v for k, v in os.environ.items() if k != "USV_BRINGUP_EXCLUDE_SECRETS"}
    res_def = subprocess.run(
        [sys.executable, "setup.py", "install_data", "--install-dir", str(default_install)],
        cwd=str(src_pkg),
        env=env_default,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert res_def.returncode == 0, res_def.stdout + res_def.stderr
    assert (default_install / "share" / "usv_bringup" / "config" / "ntrip_params.yaml").is_file()
    assert (default_install / "share" / "usv_bringup" / "config" / "safety_params.yaml").is_file()

    excluded_install = tmp_path / "install_excluded"
    env_excl = dict(env_default)
    env_excl["USV_BRINGUP_EXCLUDE_SECRETS"] = "1"
    res_excl = subprocess.run(
        [sys.executable, "setup.py", "install_data", "--install-dir", str(excluded_install)],
        cwd=str(src_pkg),
        env=env_excl,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert res_excl.returncode == 0, res_excl.stdout + res_excl.stderr
    assert not (excluded_install / "share" / "usv_bringup" / "config" / "ntrip_params.yaml").exists()
    assert (excluded_install / "share" / "usv_bringup" / "config" / "safety_params.yaml").is_file()


def _extract_mode_manager_params(node: Node, ctx: LaunchContext) -> tuple[str, dict]:
    node._perform_substitutions(ctx)
    param_args = node._Node__expanded_parameter_arguments
    yaml_path = param_args[0][0]
    inline_path, is_temp = param_args[1]
    try:
        with open(inline_path, "r", encoding="utf-8") as handle:
            inline_params = yaml.safe_load(handle)["/**"]["ros__parameters"]
    finally:
        if is_temp and os.path.basename(inline_path).startswith("launch_params_") and os.path.isfile(inline_path):
            os.unlink(inline_path)
    return yaml_path, inline_params


def test_real_launch_legacy_preserves_mode_manager_params_and_mpc(monkeypatch):
    # F6：controller_backend 默认 legacy；legacy 分支的 mode_manager_node
    # 参数集合与 HEAD 完全一致（不额外注入 failsafe_mode），且拉起 mpc_node。
    mod = _load_real_launch()
    monkeypatch.setattr(mod, "_ntrip_daemon_state", lambda service="usv-rtk.service": "active")
    monkeypatch.setattr(
        mod, "get_package_share_directory", lambda pkg: str(PKG_ROOT) if pkg == "usv_bringup" else get_package_share_directory(pkg)
    )
    ld = mod.generate_launch_description()
    ctx = _prepare_context(ld, {})
    assert ctx.launch_configurations["controller_backend"] == "legacy"

    enabled_nodes = [
        e for e in ld.entities if isinstance(e, Node) and _is_enabled(e, ctx)
    ]
    mode_managers = [n for n in enabled_nodes if n.node_executable == "mode_manager_node"]
    assert len(mode_managers) == 1
    yaml_path, inline_dict = _extract_mode_manager_params(mode_managers[0], ctx)
    assert os.path.samefile(yaml_path, str(PKG_ROOT / "config" / "safety_params.yaml"))
    expected_head_inline = {
        "auto_arm": False,
        "auto_mode_switch": False,
        "state_topic": "/mavros/state",
        "odom_topic": "/mavros/local_position/odom",
        "battery_topic": "/usv/battery",
        "path_topic": "/path/reference",
        "set_mode_service": "/mavros/set_mode",
        "arming_service": "/mavros/cmd/arming",
    }
    assert inline_dict == expected_head_inline
    assert "failsafe_mode" not in inline_dict

    enabled_timers = [
        e for e in ld.entities if type(e).__name__ == "TimerAction" and _is_enabled(e, ctx)
    ]
    assert len(enabled_timers) == 1  # legacy delayed_mpc
    timer_nodes = [a for a in enabled_timers[0].actions if isinstance(a, Node)]
    assert len(timer_nodes) == 1 and timer_nodes[0].node_executable == "mpc_node"
    enabled_execs = [
        e for e in ld.entities if type(e).__name__ == "ExecuteProcess" and _is_enabled(e, ctx)
    ]
    # 只有 log_msg，没有 commissioning_launch
    assert len(enabled_execs) == 1


def test_real_launch_commissioning_sets_report_failsafe_and_skips_mpc(monkeypatch):
    mod = _load_real_launch()
    monkeypatch.setattr(mod, "_ntrip_daemon_state", lambda service="usv-rtk.service": "active")
    monkeypatch.setattr(
        mod, "get_package_share_directory", lambda pkg: str(PKG_ROOT) if pkg == "usv_bringup" else get_package_share_directory(pkg)
    )
    ld = mod.generate_launch_description()
    ctx = _prepare_context(
        ld,
        {
            "controller_backend": "research_commissioning",
            "commissioning_release_root": "/tmp/fake-R",
            "commissioning_underlay": "/tmp/fake-U",
        },
    )

    enabled_nodes = [
        e for e in ld.entities if isinstance(e, Node) and _is_enabled(e, ctx)
    ]
    mode_managers = [n for n in enabled_nodes if n.node_executable == "mode_manager_node"]
    assert len(mode_managers) == 1
    _yaml_path, inline_dict = _extract_mode_manager_params(mode_managers[0], ctx)
    assert inline_dict["failsafe_mode"] == "report"
    assert inline_dict["auto_arm"] is False
    assert inline_dict["auto_mode_switch"] is False
    assert not any(n.node_executable == "mpc_node" for n in enabled_nodes)

    # 无任何 mpc TimerAction 生效
    enabled_timers = [
        e for e in ld.entities if type(e).__name__ == "TimerAction" and _is_enabled(e, ctx)
    ]
    assert len(enabled_timers) == 0

    enabled_execs = [
        e for e in ld.entities if type(e).__name__ == "ExecuteProcess" and _is_enabled(e, ctx)
    ]
    assert len(enabled_execs) == 2
    commissioning_cmd = [perform_substitutions(ctx, part) for part in enabled_execs[1].cmd]
    assert commissioning_cmd[0].endswith("run_shipboard_commissioning.py")
    assert "/tmp/fake-R" in commissioning_cmd
    assert "/tmp/fake-U" in commissioning_cmd
    assert any(p.endswith("contract_shipboard_commissioning.json") for p in commissioning_cmd)
    assert "commissioning" in commissioning_cmd


def test_real_launch_dry_run_selects_dry_run_contract_and_skips_mpc(monkeypatch):
    mod = _load_real_launch()
    monkeypatch.setattr(mod, "_ntrip_daemon_state", lambda service="usv-rtk.service": "active")
    monkeypatch.setattr(
        mod, "get_package_share_directory", lambda pkg: str(PKG_ROOT) if pkg == "usv_bringup" else get_package_share_directory(pkg)
    )
    ld = mod.generate_launch_description()
    ctx = _prepare_context(
        ld,
        {
            "controller_backend": "research_dry_run",
            "commissioning_release_root": "/tmp/fake-R",
            "commissioning_underlay": "/tmp/fake-U",
        },
    )

    enabled_nodes = [
        e for e in ld.entities if isinstance(e, Node) and _is_enabled(e, ctx)
    ]
    mode_managers = [n for n in enabled_nodes if n.node_executable == "mode_manager_node"]
    assert len(mode_managers) == 1
    _yaml_path, inline_dict = _extract_mode_manager_params(mode_managers[0], ctx)
    assert inline_dict["failsafe_mode"] == "report"
    assert not any(n.node_executable == "mpc_node" for n in enabled_nodes)
    enabled_timers = [
        e for e in ld.entities if type(e).__name__ == "TimerAction" and _is_enabled(e, ctx)
    ]
    assert len(enabled_timers) == 0

    enabled_execs = [
        e for e in ld.entities if type(e).__name__ == "ExecuteProcess" and _is_enabled(e, ctx)
    ]
    assert len(enabled_execs) == 2
    dry_run_cmd = [perform_substitutions(ctx, part) for part in enabled_execs[1].cmd]
    assert dry_run_cmd[0].endswith("run_shipboard_commissioning.py")
    assert any(p.endswith("contract_shipboard_dry_run.json") for p in dry_run_cmd)
    assert "shipboard_dry_run" in dry_run_cmd
