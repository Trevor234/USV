# USV MPC Topic and Frame Contract

This document is the authoritative interface map for the USV MPC stack. Keep
launch files, YAML parameters, and node defaults aligned with this contract.

## Common interfaces

| Interface | Default topic/frame | Message / meaning |
| --- | --- | --- |
| Reference path | `/path/reference` | `nav_msgs/msg/Path`, path frame is `map` |
| Dynamic waypoints | `/usv/mission/waypoints_local` | `nav_msgs/msg/Path`, local mission waypoints |
| MPC status | `/mpc/status` | `std_msgs/msg/String`, JSON diagnostics |
| MPC predicted trajectory | `/mpc/predicted_trajectory` | `nav_msgs/msg/Path` |
| Map frame | `map` | Global/world path and odometry frame |
| Body frame | `base_link` | USV body frame for commands/diagnostics |

Scheme A publishes candidate-solution feasibility diagnostics in `/mpc/status`:
`initial_state_residual`, `max_dynamics_residual`,
`max_control_bound_violation`, and `max_control_rate_violation`. A recovered
IPOPT iterate is successful only when all four values are within
`kinematic.solution_constraint_tol`.

Scheme B publishes the solver's planned first thrust as `tl_cmd_n`/`tr_cmd_n` and
the execution-layer equivalent input used for the next rate anchor as
`tl_n`/`tr_n`. `actuation_anchor_source` is `rc_linearized` for RC override and
`vrx_published` for direct VRX thrust. `actuation_mapping_error_n` is the
largest absolute difference between the planned and anchored values.

## Runtime profiles

### `vrx` — real VRX Gazebo Sim / WAM-V

| Interface | Topic |
| --- | --- |
| Odometry | `/wamv/sensors/position/ground_truth_odometry` |
| IMU | `/wamv/sensors/imu/imu/data` |
| Left thrust command | `/wamv/thrusters/left/thrust` |
| Right thrust command | `/wamv/thrusters/right/thrust` |

Notes:

- VRX waypoints must use the same world/map coordinates as the WAM-V odometry.
  They are **not** local to the boat spawn point.
- VRX odometry follows the `nav_msgs/msg/Odometry` frame contract: pose is in
  `header.frame_id` (`map`) and twist is in `child_frame_id`
  (`wamv/base_link`). Scheme A's `cmdvel_to_thrust` consumes
  `twist.linear.x` directly as body-frame surge speed and must not rotate it by
  the pose yaw again.
- The default WAM-V spawn in `sydney_regatta` is around `(-532, 162)`, so a
  YAML route around `(0, 0)` is hundreds of meters away.
- VRX thrust topics use the WAM-V thruster command scale; `mpc_node` maps its
  internal left/right thrust values through `vrx_thrust_scale`, clamps them to
  the configured dynamic thrust bounds, and writes the final published values
  back as the next `delta_T` anchor.

### `sitl_mavros` — ArduPilot SITL + MAVROS

| Interface | Topic |
| --- | --- |
| Odometry | `/mavros/local_position/odom` |
| IMU | `/mavros/imu/data` |
| FCU state | `/mavros/state` |
| Scheme A velocity command | `/mavros/setpoint_velocity/cmd_vel` |
| Scheme B RC override | `/mavros/rc/override` |
| RC output | `/mavros/rc/out` |

Scheme B's RC path uses the configured PWM gains and signs to produce the
override. After integer PWM quantization, the node reports a linearized
equivalent thrust in `tl_n`/`tr_n`; this is a command-side estimate until PWM,
dead zone, propulsion and battery-voltage calibration data are available.

### `real_mavros` — real boat + MAVROS

Use the same MAVROS topic contract as `sitl_mavros` unless the hardware launch
explicitly remaps topics. Any deviation should be documented in the launch file
and reflected in this document.

### `fallback_gz` — project Gazebo Sim fallback

| Interface | Topic |
| --- | --- |
| Gazebo model odometry | `/model/usv_2m/odometry` |
| Wrench command | `/world/lake_gz/wrench` |
| Force command bridge input | `/usv/cmd_force` |

### `classic_gazebo` — Gazebo Classic legacy/fallback

Gazebo Classic launch files use `GAZEBO_*` environment variables and may depend
on `gazebo_ros`. They are not the preferred VRX validation path on ROS 2 Jazzy.

## Debug checklist

```bash
ros2 topic list | grep -E 'mpc|path|wamv|mavros|usv'
ros2 topic echo /mpc/status --once
ros2 topic info /path/reference
ros2 param dump /mpc_controller_node
```

For VRX, also check:

```bash
ros2 topic echo /wamv/sensors/position/ground_truth_odometry --once
ros2 topic echo /wamv/thrusters/left/thrust --once
ros2 topic echo /wamv/thrusters/right/thrust --once
```
