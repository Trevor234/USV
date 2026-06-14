from usv_safety.safety_monitor import SafetyConfig, SafetyLevel, SafetyMonitor


def test_safety_domains_do_not_clear_each_other():
    monitor = SafetyMonitor(
        SafetyConfig(
            geofence_radius_m=10.0,
            max_path_timeout_s=1.0,
            max_solver_failures=2,
        )
    )

    monitor.update_odom(11.0, 0.0, 0.0, 0.0, 12.0, timestamp=100.0)
    monitor.update_solver(False, 10.0, timestamp=101.0)
    monitor.update_solver(False, 10.0, timestamp=102.0)
    monitor.update_path(True, timestamp=103.0)
    monitor.update_path(False, timestamp=105.0)

    flags = monitor.active_flags
    assert any(flag.startswith("GEOFENCE VIOLATION") for flag in flags)
    assert any(flag.startswith("Solver failed") for flag in flags)
    assert any(flag.startswith("No path update") for flag in flags)
    assert monitor.level == SafetyLevel.FAILSAFE

    monitor.update_odom(0.0, 0.0, 0.0, 0.0, 12.0, timestamp=106.0)
    flags = monitor.active_flags
    assert not any(flag.startswith("GEOFENCE VIOLATION") for flag in flags)
    assert any(flag.startswith("Solver failed") for flag in flags)
    assert any(flag.startswith("No path update") for flag in flags)


def test_state_returns_defensive_copy():
    monitor = SafetyMonitor(SafetyConfig(geofence_radius_m=10.0))
    monitor.update_odom(11.0, 0.0, 0.0, 0.0, 12.0, timestamp=100.0)

    state = monitor.state
    state.active_flags.clear()

    assert any(flag.startswith("GEOFENCE VIOLATION") for flag in monitor.active_flags)


def test_battery_severity_and_action():
    monitor = SafetyMonitor(SafetyConfig(low_battery_v=10.5, critical_battery_v=10.0))

    monitor.update_odom(0.0, 0.0, 0.0, 0.0, 10.2, timestamp=100.0)
    assert monitor.level == SafetyLevel.WARNING
    assert monitor.recommended_action == "REDUCE_SPEED"
    assert any(flag.startswith("Low battery") for flag in monitor.active_flags)

    monitor.update_odom(0.0, 0.0, 0.0, 0.0, 9.8, timestamp=101.0)
    assert monitor.level == SafetyLevel.FAILSAFE
    assert monitor.recommended_action == "RTL"
    assert any(flag.startswith("CRITICAL battery") for flag in monitor.active_flags)
