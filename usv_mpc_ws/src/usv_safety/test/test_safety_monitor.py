from usv_safety.safety_monitor import SafetyConfig, SafetyLevel, SafetyMonitor


def test_safety_domains_do_not_clear_each_other():
    monitor = SafetyMonitor(
        SafetyConfig(
            geofence_radius_m=10.0,
            max_path_timeout_s=1.0,
            max_solver_failures=2,
        )
    )

    monitor.update_odom(11.0, 0.0, 0.0, 0.0, timestamp=100.0)
    monitor.update_battery(12.0, timestamp=100.0)
    monitor.update_solver(False, 10.0, timestamp=101.0)
    monitor.update_solver(False, 10.0, timestamp=102.0)
    monitor.update_path(True, timestamp=103.0)
    monitor.update_path(False, timestamp=105.0)

    flags = monitor.active_flags
    assert any(flag.startswith("GEOFENCE VIOLATION") for flag in flags)
    assert any(flag.startswith("Solver failed") for flag in flags)
    assert any(flag.startswith("No path update") for flag in flags)
    assert monitor.level == SafetyLevel.FAILSAFE

    monitor.update_odom(0.0, 0.0, 0.0, 0.0, timestamp=106.0)
    flags = monitor.active_flags
    assert not any(flag.startswith("GEOFENCE VIOLATION") for flag in flags)
    assert any(flag.startswith("Solver failed") for flag in flags)
    assert any(flag.startswith("No path update") for flag in flags)


def test_state_returns_defensive_copy():
    monitor = SafetyMonitor(SafetyConfig(geofence_radius_m=10.0))
    monitor.update_odom(11.0, 0.0, 0.0, 0.0, timestamp=100.0)

    state = monitor.state
    state.active_flags.clear()

    assert any(flag.startswith("GEOFENCE VIOLATION") for flag in monitor.active_flags)


def test_battery_severity_and_action():
    monitor = SafetyMonitor(SafetyConfig(low_battery_v=10.5, critical_battery_v=10.0))

    monitor.update_battery(10.2, timestamp=100.0)
    assert monitor.level == SafetyLevel.WARNING
    assert monitor.recommended_action == "REDUCE_SPEED"
    assert any(flag.startswith("Low battery") for flag in monitor.active_flags)

    monitor.update_battery(9.8, timestamp=101.0)
    assert monitor.level == SafetyLevel.FAILSAFE
    assert monitor.recommended_action == "RTL"
    assert any(flag.startswith("CRITICAL battery") for flag in monitor.active_flags)


def test_battery_update_does_not_refresh_odom_watchdog():
    """Battery telemetry must not keep the odom failsafe alive (P0-1)."""
    monitor = SafetyMonitor(
        SafetyConfig(max_odom_timeout_s=1.0, low_battery_v=10.5)
    )

    monitor.update_odom(0.0, 0.0, 0.0, 0.0, timestamp=100.0)
    # Battery keeps arriving long after odom died.
    for t in (101.0, 102.0, 103.0):
        monitor.update_battery(12.0, timestamp=t)

    assert monitor.check_odom_timeout(timestamp=103.0)
    monitor.set_odom_watchdog("Odometry timeout: 3.0s", timestamp=103.0)
    assert monitor.level == SafetyLevel.FAILSAFE


def test_mpc_status_timeout_triggers_failsafe():
    """Stale /mpc/status in ACTIVE/HOLD must failsafe (P0-2)."""
    monitor = SafetyMonitor(SafetyConfig(mpc_status_timeout_s=1.0))

    monitor.mark_mpc_status(timestamp=100.0)
    assert not monitor.check_mpc_status_timeout(timestamp=100.5)
    monitor.set_mpc_status_watchdog(None, timestamp=100.5)
    assert monitor.level == SafetyLevel.NOMINAL

    # MPC died: no more status. Beyond the timeout the watchdog flags FAILSAFE.
    assert monitor.check_mpc_status_timeout(timestamp=101.5)
    monitor.set_mpc_status_watchdog("MPC status timeout: 1.5s", timestamp=101.5)
    assert monitor.level == SafetyLevel.FAILSAFE
    assert monitor.recommended_action == "RTL"
    assert any(f.startswith("MPC status timeout") for f in monitor.active_flags)

    # A fresh status clears the watchdog flag again.
    monitor.mark_mpc_status(timestamp=102.0)
    monitor.set_mpc_status_watchdog(None, timestamp=102.0)
    assert monitor.level == SafetyLevel.NOMINAL
