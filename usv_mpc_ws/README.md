# USV MPC Control System

ROS 2 Humble workspace for autonomous 2-meter dual-thruster USV using Model Predictive Control (MPC).

## Architecture

```
usv_mpc_ws/
├── src/
│   ├── usv_bringup/       # Launch files and configuration
│   ├── usv_mpc/            # MPC controller (core)
│   ├── usv_planning/      # Path planning and waypoints
│   ├── usv_safety/        # Mode management and safety monitoring
│   └── usv_simulation/    # Simulator (no hardware needed)
├── install/
├── build/
└── log/
```

## Packages

| Package | Description | Key Files |
|:---|:---|:---|
| `usv_mpc` | MPC solvers (kinematic + dynamic), ROS 2 node | `mpc_node.py`, `mpc_kinematic.py`, `mpc_dynamic.py` |
| `usv_planning` | Waypoint management, Dubins paths, path smoothing | `path_planner_node.py`, `dubins_path.py` |
| `usv_safety` | Mode switching, geofence, failsafe monitoring | `mode_manager_node.py`, `safety_monitor.py` |
| `usv_simulation` | 6-DOF dynamics simulator, matplotlib visualizer | `sim_node.py`, `visualizer.py` |
| `usv_bringup` | Launch files (sim/SITL/real), YAML configs | `launch/*.py`, `config/*.yaml` |

## Two Control Schemes

| | Scheme A (Kinematic) | Scheme B (Dynamic) |
|:---|:---|:---|
| MPC state | [x, y, psi] | [x, y, psi, u, v, r] |
| MPC control | [u_surge, r_yaw] | [T_L, T_R] |
| MAVLink cmd | `SET_POSITION_TARGET_LOCAL_NED` | `RC_CHANNELS_OVERRIDE` |
| Complexity | Low | High |
| Status | Ready | Experimental |

## Prerequisites

- Ubuntu 24.04 + ROS 2 Humble
- CasADi (`pip install casadi`)
- NumPy, matplotlib, pyyaml
- MAVROS (`sudo apt install ros-humble-mavros ros-humble-mavros-extras`)
- acados (optional, for embedded performance)

## Quick Start

### 1. Build the workspace

```bash
cd ros/usv_mpc_ws
colcon build --symlink-install
source install/setup.bash
```

### 2. Simulation test (no hardware)

```bash
ros2 launch usv_bringup sim.launch.py
```

This starts the dynamics simulator, MPC controller, path planner, and visualizer.

### 3. Run MPC test scripts (no ROS)

```bash
cd src/usv_mpc/test
python test_mpc_straight.py   # Straight line tracking
python test_mpc_circle.py     # Circular path tracking
python test_mpc_benchmark.py  # Solver performance benchmarks
```

### 4. SITL (with ArduRover simulator)

Terminal 1:
```bash
sim_vehicle.py -v Rover --map --console --out=tcpin:0.0.0.0:5760
```

Terminal 2:
```bash
ros2 launch usv_bringup sitl.launch.py
```

### 5. Real hardware

```bash
ros2 launch usv_bringup real.launch.py
```

Verify communication:
```bash
ros2 topic echo /mavros/state
ros2 topic echo /mavros/mavros/odom
```

### 6. Ground station via Raspberry Pi network

For a single Mission Planner instance on the same LAN as the Raspberry Pi,
launch MAVROS with a GCS forwarding endpoint:

```bash
ros2 launch usv_bringup mavros.launch.py gcs_url:=udp://@<gcs-ip>:14550
```

Or forward telemetry while running the full real-hardware stack:

```bash
ros2 launch usv_bringup real.launch.py gcs_url:=udp://@<gcs-ip>:14550
```

This keeps MAVROS as the only serial client to the flight controller and
forwards MAVLink to one ground-station endpoint. For future 5G / internet,
multi-GCS, or multi-consumer routing, prefer a dedicated routing layer such as
`mavlink-router` plus stable addressing or VPN.

## Configuration

All tunable parameters are in `src/usv_bringup/config/`:

- `mpc_params.yaml` — MPC weights, horizon, constraints
- `usv_params.yaml` — Hull mass, damping, thruster properties
- `path_config.yaml` — Waypoints, path generation settings
- `mavros_config.yaml` — MAVROS FCU and optional GCS forwarding config

## Topics

| Topic | Type | Direction | Rate |
|:---|:---|:---|:---|
| `/mavros/mavros/odom` | `Odometry` | FCU → RPi | 10-50 Hz |
| `/mavros/mavros/data` | `Imu` | FCU → RPi | 50 Hz |
| `/mavros/mavros/cmd_vel` | `TwistStamped` | RPi → FCU | 5 Hz |
| `/mavros/mavros/override` | `OverrideRCIn` | RPi → FCU | 10 Hz |
| `/path/reference` | `Path` | Internal | 1 Hz |
| `/mpc/predicted_trajectory` | `Path` | Internal | 5 Hz |

## Safety

The `usv_safety` package provides:
- Geofence boundary enforcement → RTL on violation
- Solver failure detection → fallback to HOLD/RTL
- Communication timeout monitoring
- Battery voltage monitoring

## Related Documents

- [Implementation Plan](../implementation_plan.md)
- [Parameter Identification Plan](../usv_parameter_identification_plan.md)
