#!/usr/bin/env bash
set -u

# Jetson Orin migration G0 inventory. Read-only; output contains no secrets by design.
printf 'timestamp=%s\n' "$(date --iso-8601=seconds)"
printf 'hostname=%s\n' "$(hostname)"
printf 'arch='; uname -m
printf 'kernel='; uname -r

if [ -r /etc/os-release ]; then
  . /etc/os-release
  printf 'os=%s %s\n' "${PRETTY_NAME:-unknown}" "${VERSION_ID:-unknown}"
fi

if [ -r /etc/nv_tegra_release ]; then
  printf '%s\n' '--- /etc/nv_tegra_release ---'
  sed -n '1p' /etc/nv_tegra_release
else
  printf '%s\n' 'jetson_release_file=missing'
fi

printf '%s\n' '--- ROS ---'
printf 'ROS_DISTRO=%s\n' "${ROS_DISTRO:-unset}"
printf 'RMW_IMPLEMENTATION=%s\n' "${RMW_IMPLEMENTATION:-unset}"
if command -v ros2 >/dev/null 2>&1; then
  printf 'ros2='; command -v ros2
  ros2 doctor --report 2>&1 | sed -n '1,80p'
else
  printf '%s\n' 'ros2=missing'
fi

printf '%s\n' '--- toolchain ---'
printf 'python='; python3 --version 2>&1 || true
printf 'gcc='; gcc --version 2>/dev/null | sed -n '1p' || true
printf 'cmake='; cmake --version 2>/dev/null | sed -n '1p' || true
printf 'colcon='; command -v colcon 2>/dev/null || true

printf '%s\n' '--- serial devices ---'
ls -l /dev/serial/by-id /dev/ttyTHS* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || true

printf '%s\n' '--- storage and memory ---'
df -h / /home /mnt 2>/dev/null || df -h /
free -h

printf '%s\n' '--- network ---'
ip -br address 2>/dev/null || true

printf '%s\n' '--- relevant services and permissions ---'
id
systemctl is-active usv-system.service 2>/dev/null || true
systemctl cat usv-system.service 2>/dev/null | sed -E 's/(password|passwd|token|secret|api[_-]?key)=.*/\1=<redacted>/I' || true
