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
| Battery state | `/usv/battery` | `sensor_msgs/msg/BatteryState`, WeAct 功率计实测电压/电流(放电为负)/SOC |

Scheme A publishes candidate-solution feasibility diagnostics in `/mpc/status`:
`initial_state_residual`, `max_dynamics_residual`,
`max_control_bound_violation`, and `max_control_rate_violation`. A recovered
IPOPT iterate is successful only when all four values are within
`kinematic.solution_constraint_tol`.

Scheme B publishes the solver's planned first thrust as `tl_cmd_n`/`tr_cmd_n` and
the execution-layer equivalent input used for the next rate anchor as
`tl_n`/`tr_n`. `actuation_anchor_source` is `rc_linearized` for RC override.
`actuation_mapping_error_n` is the largest absolute difference between the planned
and anchored values.

## Runtime profile

### `real_mavros` — real boat + MAVROS

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
Any deviation from these defaults should be documented in `real.launch.py` and
reflected in this document and `src/usv_bringup/config/topic_contract.yaml`.

## Power monitor (`/usv/battery`)

WeAct PowerMonitorMini V1, wired to Pi 5 GPIO UART (not the FCU link):
`dtoverlay=uart4-pi5` in `/boot/firmware/config.txt` enables GPIO12/13 as
`/dev/ttyAMA4`; cross-wire Pi TXD→device RX, Pi RXD→device TX, common GND.
GPIO14/15 (`/dev/ttyAMA10`) stays reserved for MAVROS. Protocol v1.3 with
CRC8-0x31 frame terminator; details in `usv_bringup/power_monitor_node.py`.

`power_monitor_node` publishes `sensor_msgs/BatteryState` (sensor-data QoS):
voltage/current measured inline on the battery (current negative on
discharge), `percentage` interpolated from a 3S LiPo per-cell SOC table
(sag-biased under load — low-battery failsafe still uses absolute voltage
thresholds); power is derivable as voltage×current. The driver polls only
the 0x82 realtime command (mAh/mWh counters are available via the vendor GUI
over USB, which can run concurrently with the UART link). With
`use_power_monitor:=true` (default), `real.launch.py` points the mode
manager's `battery_topic` at `/usv/battery`; `false` falls back to
`/mavros/battery`.

## Debug checklist

```bash
ros2 topic list | grep -E 'mpc|path|mavros|usv'
ros2 topic echo /mpc/status --once
ros2 topic info /path/reference
ros2 param dump /mpc_controller_node
```
