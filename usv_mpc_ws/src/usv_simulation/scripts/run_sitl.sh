#!/usr/bin/env bash
# Convenience wrapper around ArduPilot's sim_vehicle.py for the USV project.
#
# Brings up an ArduRover Boat-mode SITL instance configured to talk to the
# Gazebo Classic ardupilot_gazebo plugin via the binary FDM interface, and
# expose MAVLink TCP on :5760 for MAVROS to attach to.
#
# Prerequisites (one-time, see README.md):
#   - ArduPilot source tree built (/home/trevor/USV/ardupilot by default)
#   - khancyr/ardupilot_gazebo plugin installed for GAZEBO=1
#   - MAVROS connects to tcp://127.0.0.1:5760 when --no-mavproxy is used
#
# By default this script reuses an existing build/sitl/bin/ardurover binary and
# passes --no-rebuild to sim_vehicle.py. Set SITL_REBUILD=1 when you actually
# want sim_vehicle.py to reconfigure/rebuild ArduPilot.
#
# Usage:
#   ./run_sitl.sh                    # default: localhost
#   ./run_sitl.sh --custom-location 30.0,114.0,0,0
#   GAZEBO=0 ./run_sitl.sh           # skip JSON frame (no Gazebo)

set -euo pipefail

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARM_FILE="${THIS_DIR}/../config/ardupilot_boat.parm"
DEFAULT_ARDUPILOT_DIR="/home/trevor/USV/ardupilot"
ARDUPILOT_ROOT="${ARDUPILOT_DIR:-${DEFAULT_ARDUPILOT_DIR}}"
SIM_VEHICLE="${ARDUPILOT_ROOT}/Tools/autotest/sim_vehicle.py"
ARDUROVER_BIN="${ARDUPILOT_ROOT}/build/sitl/bin/ardurover"

if [[ ! -f "${PARM_FILE}" ]]; then
    echo "[run_sitl] ERROR: parameter file not found: ${PARM_FILE}" >&2
    exit 1
fi

if [[ ! -x "${SIM_VEHICLE}" ]]; then
    if command -v sim_vehicle.py >/dev/null 2>&1; then
        SIM_VEHICLE="$(command -v sim_vehicle.py)"
    else
        echo "[run_sitl] ERROR: sim_vehicle.py not found." >&2
        echo "  Expected: ${SIM_VEHICLE}" >&2
        echo "  Or set ARDUPILOT_DIR=/path/to/ardupilot, e.g.:" >&2
        echo "    export ARDUPILOT_DIR=/home/trevor/USV/ardupilot" >&2
        exit 2
    fi
fi

REBUILD_ARGS=()
if [[ "${SITL_REBUILD:-0}" != "1" ]]; then
    if [[ ! -x "${ARDUROVER_BIN}" ]]; then
        echo "[run_sitl] ERROR: ArduRover SITL binary not found: ${ARDUROVER_BIN}" >&2
        echo "  Build it once, then rerun this launch:" >&2
        echo "    cd ${ARDUPILOT_ROOT}" >&2
        echo "    ./waf configure --board sitl" >&2
        echo "    ./waf rover" >&2
        echo "  Or allow sim_vehicle.py to build on this run:" >&2
        echo "    SITL_REBUILD=1 ros2 launch usv_simulation ardupilot_sitl.launch.py use_gazebo:=false mavros:=true" >&2
        exit 3
    fi
    REBUILD_ARGS=(--no-rebuild)
fi

GAZEBO="${GAZEBO:-1}"
if [[ "${GAZEBO}" == "1" ]]; then
    # gazebo-rover frame selects SIM_Gazebo.cpp (binary fdm_packet/servo_packet
    # protocol) that matches libArduPilotPlugin.so. JSON FDM has no Gazebo
    # Classic 11 counterpart — only Gazebo Garden+ via ArduPilot/ardupilot_gazebo.
    FRAME_ARGS=(--frame=gazebo-rover)
else
    FRAME_ARGS=(--frame=rover-skid)   # internal physics fallback
fi

exec "${SIM_VEHICLE}" \
    --vehicle Rover \
    "${REBUILD_ARGS[@]}" \
    "${FRAME_ARGS[@]}" \
    --add-param-file="${PARM_FILE}" \
    --no-mavproxy \
    "$@"
