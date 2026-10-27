"""Resolve the real launch parameter layers without executing any node action."""
import importlib.util
from pathlib import Path

import pytest
import yaml
from launch import LaunchContext
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.utilities import normalize_to_list_of_substitutions, perform_substitutions
from launch_ros.actions import Node
from launch_ros.utilities import evaluate_parameters

PACKAGE = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", ["mpc_params.yaml", "mpc_params_B.yaml"])
def test_dynamic_rc_yaml_uses_manual(name):
    params = yaml.safe_load((PACKAGE / "config" / name).read_text())["/**"]["ros__parameters"]
    assert params["output_mode"] == "rc_override"
    assert params["allowed_fcu_modes"] == ["MANUAL"]
    assert params["require_fcu_state"] is True


def nodes(entities):
    for entity in entities:
        if isinstance(entity, Node):
            yield entity
        elif isinstance(entity, TimerAction):
            yield from nodes(entity.actions)


@pytest.mark.parametrize("launch_name", ["real.launch.py", "sitl.launch.py"])
@pytest.mark.parametrize("scheme,target", [("A", "GUIDED"), ("B", "MANUAL")])
def test_effective_launch_mode_contract(launch_name, scheme, target, monkeypatch, tmp_path):
    monkeypatch.setenv("ROS_LOG_DIR", str(tmp_path / "ros_log"))
    spec = importlib.util.spec_from_file_location("mode_contract_launch", PACKAGE / "launch" / launch_name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    description = module.generate_launch_description()
    context = LaunchContext()
    context.launch_configurations["scheme"] = scheme
    for entity in description.entities:
        if isinstance(entity, DeclareLaunchArgument):
            entity.execute(context)
    selected = {}
    for node in nodes(description.entities):
        if node.condition is not None and not node.condition.evaluate(context):
            continue
        executable = perform_substitutions(context, normalize_to_list_of_substitutions(node.node_executable))
        if executable not in {"mpc_node", "mode_manager_node"}:
            continue
        # Normalized parameter storage is inspected; Node.execute is never called.
        effective = {}
        for item in evaluate_parameters(context, node._Node__parameters):
            if isinstance(item, dict):
                effective.update(item)
            else:
                effective.update(yaml.safe_load(Path(item).read_text())["/**"]["ros__parameters"])
        selected[executable] = effective
    modes = selected["mpc_node"]["allowed_fcu_modes"]
    assert isinstance(modes, (tuple, list))
    assert list(modes) == [target]
    assert selected["mode_manager_node"]["mpc_fcu_mode"] == target
    assert selected["mode_manager_node"]["auto_mode_switch"] is False
    if scheme == "B":
        assert selected["mpc_node"]["output_mode"] == "rc_override"
        assert selected["mpc_node"]["require_fcu_state"] is True
