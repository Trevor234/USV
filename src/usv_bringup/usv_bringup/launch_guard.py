"""防重复启动与硬件串口占用守护机制 (Launch Guard)。

设计目标:
1. 防后台服务冲突: 若 usv-system.service 已处于 active 状态, 阻止终端再次手动运行
   real.launch.py 或 mavros.launch.py, 避免双 MAVROS 实例抢占 /dev/ttyAMA10 造成 100% 丢帧;
2. 防并发实例冲突: 跨终端/多用户启动时, 基于 /tmp/usv_system.lock 的内核级排他文件锁 (flock)
   实现原子互斥 (进程退出内核自动释放锁, 绝无死锁);
3. 物理串口占用探查: 启动 MAVROS 前通过 /proc 文件系统精确探测 /dev/ttyAMA10 是否被其他残留
   或孤儿进程占用;
4. 调试逃生通道: 提供 force:=true 选项允许人工显式绕过保护 (带显眼黄色高危日志)。
"""

from datetime import datetime
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import List, Optional, Set

from launch.actions import LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration


class LaunchGuardError(RuntimeError):
    """防重复启动拦截异常, 包含可操作的处置指引。"""


# 全局引用以阻止 GC 垃圾回收导致文件描述符过早关闭与锁自动释放
_LOCK_FILE_OBJ = None


def is_systemd_managed() -> bool:
    """检查当前进程是否由 systemd 守护进程拉起 (天然携带 INVOCATION_ID)。"""
    return bool(os.environ.get("INVOCATION_ID"))


def is_service_active(service_name: str = "usv-system.service") -> bool:
    """检查指定的 systemd 服务是否处于运行或正在启动中。"""
    try:
        res = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return res.stdout.strip() in ("active", "activating", "reloading")
    except (OSError, subprocess.SubprocessError):
        return False


def acquire_launch_lock(
    lock_name: str = "usv_system",
    lock_dir: str = "/tmp",
) -> int:
    """获取非阻塞的全局排他文件锁 (flock)。

    返回锁定成功的文件描述符 (fileno)。若已被其他实例持有, 抛出 LaunchGuardError。
    注意: Linux 内核保证在持锁进程退出 (含 SIGTERM/SIGKILL 异常终止) 时自动解开文件锁。
    """
    global _LOCK_FILE_OBJ
    lock_path = Path(lock_dir) / f"{lock_name}.lock"
    try:
        # 使用 a+ 模式打开, 确保在未获得锁之前不截断原有内容
        fd = open(lock_path, "a+", encoding="utf-8")
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        # 成功获得锁后写入当前进程信息
        fd.seek(0)
        fd.truncate(0)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fd.write(f"pid={os.getpid()}\ntime={now_str}\ncmd={' '.join(sys.argv)}\n")
        fd.flush()

        _LOCK_FILE_OBJ = fd
        return fd.fileno()
    except (BlockingIOError, OSError) as exc:
        holder_info = "未知进程"
        try:
            with open(lock_path, "r", encoding="utf-8") as f:
                content = f.read().strip().replace("\n", " | ")
                if content:
                    holder_info = content
        except Exception:
            pass
        raise LaunchGuardError(
            f"[FATAL CONFLICT] 检测到系统启动锁已被占用: '{lock_path}'!\n"
            f"  持有者信息: {holder_info}\n"
            f"  系统禁止同时运行多个 USV 控制栈实例以防止串口冲突与抢控。\n"
            f"  若要终止已运行的实例, 请先关闭对应终端或使用 kill 命令。"
        ) from exc


def release_launch_lock() -> None:
    """显式释放当前进程持有的文件锁 (主要用于单元测试)。"""
    global _LOCK_FILE_OBJ
    if _LOCK_FILE_OBJ is not None:
        try:
            fcntl.flock(_LOCK_FILE_OBJ.fileno(), fcntl.LOCK_UN)
            _LOCK_FILE_OBJ.close()
        except Exception:
            pass
        _LOCK_FILE_OBJ = None


def parse_serial_device(fcu_url: str) -> Optional[str]:
    """从 MAVROS fcu_url (如 /dev/ttyAMA10:921600) 中提取物理串口路径。"""
    if not fcu_url:
        return None
    cleaned = fcu_url.strip()
    if cleaned.startswith(("udp:", "tcp:", "udpb:", "file:")):
        return None
    dev = cleaned.split(":")[0]
    return dev if dev.startswith("/dev/") else None


def get_process_name(pid: int) -> str:
    """读取指定 PID 的可执行程序名。"""
    try:
        return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
    except Exception:
        return "unknown"


def find_device_holders(
    dev_path: str,
    exclude_pids: Optional[Set[int]] = None,
) -> List[int]:
    """通过 /proc/*/fd 快速检索当前正在打开指定字符设备文件的进程 PID (耗时约 10ms)。"""
    if not os.path.exists(dev_path):
        return []

    try:
        dev_stat = os.stat(dev_path)
        dev_rdev = dev_stat.st_rdev
    except OSError:
        return []

    excludes = set(exclude_pids or ())
    excludes.add(os.getpid())

    holders: List[int] = []
    for proc_entry in Path("/proc").iterdir():
        if not proc_entry.name.isdigit():
            continue
        try:
            pid = int(proc_entry.name)
        except ValueError:
            continue
        if pid in excludes:
            continue

        fd_dir = proc_entry / "fd"
        try:
            for fd_link in fd_dir.iterdir():
                try:
                    st = os.stat(fd_link)
                    if st.st_rdev == dev_rdev:
                        holders.append(pid)
                        break
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            continue

    return sorted(holders)


def assert_safe_to_launch(
    fcu_url: str = "/dev/ttyAMA10:921600",
    service_name: str = "usv-system.service",
    lock_name: str = "usv_system",
    force: bool = False,
    is_systemd: Optional[bool] = None,
    check_service: bool = True,
    check_lock: bool = True,
    check_device: bool = True,
) -> bool:
    """组合执行三层纵深防重复启动校验。

    若检测到冲突, 抛出带处置指引的 LaunchGuardError; 校验通过返回 True。
    """
    if force:
        print(
            "\n" + "=" * 70 + "\n"
            "[WARNING] 防重复启动检查已由 force:=true 强制绕过!\n"
            "  高危警告: 若后台有其他实例运行, 物理串口 (/dev/ttyAMA10) 将被双重读写,\n"
            "  造成 MAVLink 丢帧与控制抢占事故! 仅供离线排障测试使用!\n"
            + "=" * 70 + "\n",
            flush=True,
        )
        return True

    systemd_mode = is_systemd_managed() if is_systemd is None else is_systemd

    # ── Guard 1: systemd 运行感知 ────────────────────────────
    if check_service and not systemd_mode:
        if is_service_active(service_name):
            raise LaunchGuardError(
                f"\n{'=' * 72}\n"
                f"[FATAL CONFLICT] 系统后台服务 '{service_name}' 正在运行中!\n"
                f"  严禁在后台服务活跃期间手动执行 ros2 launch, 否则将产生双 MAVROS 实例\n"
                f"  争抢物理串口 (/dev/ttyAMA10), 导致 MAVLink 校验错误率达 100% 并引发抢控!\n\n"
                f"  若要手动调试, 请先停止后台服务:\n"
                f"      sudo systemctl stop {service_name.replace('.service', '')}\n"
                f"  若确实需要强制启动 (高风险排障), 请追加参数:\n"
                f"      force:=true\n"
                f"{'=' * 72}\n"
            )

    # ── Guard 2: 全局排他锁 (flock) ─────────────────────────
    if check_lock:
        acquire_launch_lock(lock_name=lock_name)

    # ── Guard 3: 硬件串口占用检查 ────────────────────────────
    if check_device:
        dev_path = parse_serial_device(fcu_url)
        if dev_path:
            holders = find_device_holders(dev_path)
            if holders:
                holder_descs = [f"PID {p} ({get_process_name(p)})" for p in holders]
                raise LaunchGuardError(
                    f"\n{'=' * 72}\n"
                    f"[FATAL CONFLICT] 物理串口 '{dev_path}' 正在被其他进程独占占用: {', '.join(holder_descs)}!\n"
                    f"  当前启动已被中止, 避免串口争抢导致 MAVLink 帧严重损坏。\n"
                    f"  请先终止上述冲突进程后重试。\n"
                    f"{'=' * 72}\n"
                )

    return True


def create_launch_guard_action(
    fcu_url_config_name: str = "fcu_url",
    force_config_name: str = "force",
    service_name: str = "usv-system.service",
    lock_name: str = "usv_system",
) -> OpaqueFunction:
    """生成 ROS 2 launch 执行期拦截 Action (OpaqueFunction)。

    在 Launch 图执行最早阶段触发校验; 失败立即抛出异常阻断全部子节点生成。
    """
    def _guard_fn(context):
        force_str = LaunchConfiguration(force_config_name).perform(context).strip().lower()
        force = force_str in ("true", "1", "yes", "on")
        fcu_url = LaunchConfiguration(fcu_url_config_name).perform(context).strip()

        assert_safe_to_launch(
            fcu_url=fcu_url,
            service_name=service_name,
            lock_name=lock_name,
            force=force,
        )
        return [LogInfo(msg="[launch_guard] 防重复启动与串口独占检查通过")]

    return OpaqueFunction(function=_guard_fn)
