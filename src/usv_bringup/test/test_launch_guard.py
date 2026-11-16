"""launch_guard (防重复启动与串口冲突守护) 单元测试。"""

import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from usv_bringup.launch_guard import (  # noqa: E402
    LaunchGuardError,
    acquire_launch_lock,
    assert_safe_to_launch,
    find_device_holders,
    get_process_name,
    is_service_active,
    is_systemd_managed,
    parse_serial_device,
    release_launch_lock,
)


@pytest.fixture(autouse=True)
def clean_locks():
    """每次测试前后确保释放全局锁描述符。"""
    release_launch_lock()
    yield
    release_launch_lock()


# ── 1. 环境与串口解析基础测试 ────────────────────────────────────
def test_is_systemd_managed(monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    assert not is_systemd_managed()

    monkeypatch.setenv("INVOCATION_ID", "abc-123-xyz")
    assert is_systemd_managed()


@pytest.mark.parametrize(
    "fcu_url,expected",
    [
        ("/dev/ttyAMA10:921600", "/dev/ttyAMA10"),
        ("/dev/ttyUSB0", "/dev/ttyUSB0"),
        ("/dev/pts/3:115200", "/dev/pts/3"),
        ("udp://@192.168.0.1:14550", None),
        ("tcp://127.0.0.1:5760", None),
        ("file:///path/to/log", None),
        ("", None),
    ],
)
def test_parse_serial_device(fcu_url, expected):
    assert parse_serial_device(fcu_url) == expected


def test_get_process_name():
    # 当前测试进程应当能够读取到自身名字 (pytest 或 python)
    my_pid = os.getpid()
    comm = get_process_name(my_pid)
    assert comm in ("pytest", "python", "python3")
    # 不存在的 PID 应优雅返回 unknown
    assert get_process_name(99999999) == "unknown"


# ── 2. 排他文件锁互斥测试 ──────────────────────────────────────
def test_acquire_and_release_lock():
    with tempfile.TemporaryDirectory() as tmpdir:
        fd = acquire_launch_lock("test_single_instance", lock_dir=tmpdir)
        assert fd > 0

        # 重复获取同一锁必须抛出 LaunchGuardError
        with pytest.raises(LaunchGuardError, match="检测到系统启动锁已被占用"):
            acquire_launch_lock("test_single_instance", lock_dir=tmpdir)

        # 释放后可以再次获取
        release_launch_lock()
        fd2 = acquire_launch_lock("test_single_instance", lock_dir=tmpdir)
        assert fd2 > 0
        release_launch_lock()


# ── 3. systemd 服务状态探查 ────────────────────────────────────
def test_is_service_active_mocked():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="active\n")
        assert is_service_active("mock.service") is True

        mock_run.return_value = MagicMock(stdout="activating\n")
        assert is_service_active("mock.service") is True

        mock_run.return_value = MagicMock(stdout="inactive\n")
        assert is_service_active("mock.service") is False

        mock_run.return_value = MagicMock(stdout="failed\n")
        assert is_service_active("mock.service") is False

        # 异常情况容错返回 False
        mock_run.side_effect = OSError("command not found")
        assert is_service_active("mock.service") is False


# ── 4. 组合断言校验 (assert_safe_to_launch) ───────────────────
def test_assert_safe_to_launch_service_conflict():
    # 场景: 终端手动启动 (非 systemd), 且后台服务 active -> 必须拦截
    with patch("usv_bringup.launch_guard.is_service_active", return_value=True):
        with pytest.raises(LaunchGuardError, match="系统后台服务.*正在运行中"):
            assert_safe_to_launch(
                service_name="usv-system.service",
                is_systemd=False,
                check_lock=False,
                check_device=False,
            )


def test_assert_safe_to_launch_systemd_passthrough():
    # 场景: systemd 自身启动守护进程 (is_systemd=True), 即使服务 active 也必须放行
    with patch("usv_bringup.launch_guard.is_service_active", return_value=True):
        res = assert_safe_to_launch(
            service_name="usv-system.service",
            is_systemd=True,
            check_lock=False,
            check_device=False,
        )
        assert res is True


def test_assert_safe_to_launch_force_bypass():
    # 场景: 即便服务冲突、串口被占, 只要 force=True 必须放行
    with patch("usv_bringup.launch_guard.is_service_active", return_value=True):
        res = assert_safe_to_launch(
            service_name="usv-system.service",
            is_systemd=False,
            force=True,
        )
        assert res is True


def test_assert_safe_to_launch_device_held():
    # 场景: 物理串口已被外部 PID 占用 -> 必须拦截并打印冲突 PID
    with patch(
        "usv_bringup.launch_guard.find_device_holders",
        return_value=[88888],
    ):
        with patch(
            "usv_bringup.launch_guard.get_process_name",
            return_value="rogue_mavros",
        ):
            with pytest.raises(LaunchGuardError, match="PID 88888.*rogue_mavros"):
                assert_safe_to_launch(
                    fcu_url="/dev/ttyAMA10:921600",
                    check_service=False,
                    check_lock=False,
                    check_device=True,
                )
