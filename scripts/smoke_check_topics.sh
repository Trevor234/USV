#!/usr/bin/env bash
# Smoke-check the USV MPC topic contract for a running profile.
# Source the relevant ROS workspaces before running this script.

set -u

PROFILE="${1:-}"
TIMEOUT_S="${SMOKE_TIMEOUT_S:-5}"

usage() {
  cat <<'EOF'
Usage:
  scripts/smoke_check_topics.sh real [A|B]

Profiles:
  real [A|B]  Real hardware / MAVROS stack launched by usv_bringup real.launch.py
              Scheme defaults to B (matching real.launch.py).

Environment:
  SMOKE_TIMEOUT_S  Timeout in seconds for --once topic echo checks (default: 5)

Examples:
  scripts/smoke_check_topics.sh real
  scripts/smoke_check_topics.sh real A
  SMOKE_TIMEOUT_S=10 scripts/smoke_check_topics.sh real B
EOF
}

if [[ -z "${PROFILE}" || "${PROFILE}" == "-h" || "${PROFILE}" == "--help" ]]; then
  usage
  exit 0
fi

if ! command -v ros2 >/dev/null 2>&1; then
  echo "ERROR: ros2 command not found. Source ROS 2 and the workspace first." >&2
  exit 2
fi

PASS=0
FAIL=0

pass() {
  echo "PASS: $*"
  PASS=$((PASS + 1))
}

fail() {
  echo "FAIL: $*" >&2
  FAIL=$((FAIL + 1))
}

check_topic_exists() {
  local topic="$1"
  if ros2 topic list | grep -Fxq "${topic}"; then
    pass "topic exists ${topic}"
  else
    fail "topic missing ${topic}"
  fi
}

check_echo_once() {
  local topic="$1"
  if timeout "${TIMEOUT_S}" ros2 topic echo "${topic}" --once >/dev/null 2>&1; then
    pass "received one message on ${topic}"
  else
    fail "no message on ${topic} within ${TIMEOUT_S}s"
  fi
}

check_info() {
  local topic="$1"
  if ros2 topic info "${topic}" >/dev/null 2>&1; then
    pass "topic info available ${topic}"
  else
    fail "topic info unavailable ${topic}"
  fi
}

check_common_mpc() {
  check_info "/path/reference"
  check_echo_once "/mpc/status"
  check_info "/mpc/predicted_trajectory"
}

SCHEME="${2:-B}"

case "${PROFILE}" in
  real)
    check_echo_once "/mavros/state"
    check_echo_once "/mavros/local_position/odom"
    check_echo_once "/mavros/imu/data"
    check_common_mpc
    case "${SCHEME}" in
      A|a)
        check_info "/mavros/setpoint_velocity/cmd_vel"
        ;;
      B|b)
        check_info "/mavros/rc/override"
        ;;
      *)
        echo "ERROR: unknown scheme '${SCHEME}' (expected A or B)" >&2
        usage >&2
        exit 2
        ;;
    esac
    ;;
  *)
    echo "ERROR: unknown profile '${PROFILE}'" >&2
    usage >&2
    exit 2
    ;;
esac

echo "---"
echo "Smoke check summary: ${PASS} passed, ${FAIL} failed"

if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
