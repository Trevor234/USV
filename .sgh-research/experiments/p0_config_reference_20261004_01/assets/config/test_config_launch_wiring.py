"""Evaluate actual launch Python wiring using small local launch API doubles.

These checks do not replace the real sourced Ubuntu launch/ROS dump gate.
"""

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from apply_config_launch_patch import patched_bytes
import research_config_sources


HERE = Path(__file__).resolve().parent
# Point this at the immutable F3 source_snapshot/usv_mpc_ws/src on Ubuntu.
SOURCE_ROOT = Path(os.environ.get(
    "P0_TEST_SOURCE_ROOT",
    str(HERE.parents[1] / "p0_contract_impl_2026-10-03/source/usv_mpc_ws/src")))
MIRROR = SOURCE_ROOT / "usv_bringup/launch/vrx.launch.py"


class Item:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.__dict__.update(kwargs)


class Configuration:
    def __init__(self, name, default=None):
        self.name = name
        self.default = default

    def perform(self, context):
        if self.name in context:
            return str(context[self.name])
        if self.default is None:
            raise KeyError(self.name)
        return self.default.perform(context) if hasattr(self.default, "perform") else str(self.default)


class Value:
    def __init__(self, value, value_type):
        self.value = value
        self.value_type = value_type

    def evaluate(self, context):
        value = self.value.perform(context) if hasattr(self.value, "perform") else self.value
        return self.value_type(value)


class Description:
    def __init__(self, entities):
        self.entities = entities


def launch_modules():
    definitions = {
        "ament_index_python.packages": {"get_package_share_directory": lambda name: "/installed/" + name},
        "launch": {"LaunchDescription": Description},
        "launch.actions": {name: type(name, (Item,), {}) for name in (
            "DeclareLaunchArgument", "ExecuteProcess", "IncludeLaunchDescription", "OpaqueFunction", "TimerAction")},
        "launch.conditions": {"IfCondition": Item},
        "launch.substitutions": {"LaunchConfiguration": Configuration, "EnvironmentVariable": Item,
                                 "PathJoinSubstitution": Item, "PythonExpression": Item},
        "launch.launch_description_sources": {"PythonLaunchDescriptionSource": Item},
        "launch_ros.actions": {"Node": type("Node", (Item,), {})},
        "launch_ros.parameter_descriptions": {"ParameterValue": Value},
        "usv_simulation.vrx_spawn": {"launch_vrx": lambda context: []},
    }
    modules = {}
    for name, attributes in definitions.items():
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        modules[name] = module
        parts = name.split(".")
        for end in range(1, len(parts)):
            parent = ".".join(parts[:end])
            modules.setdefault(parent, types.ModuleType(parent))
    modules["usv_bringup"] = types.ModuleType("usv_bringup")
    modules["usv_bringup.research_config_sources"] = research_config_sources
    return modules


def load_launch(source, name):
    module = types.ModuleType(name)
    exec(compile(source, name, "exec"), module.__dict__)
    return module


def find_b_parameters(description):
    for entity in description.entities:
        for node in getattr(entity, "actions", []):
            if getattr(node, "package", None) == "usv_mpc_cpp":
                return node.parameters
    raise AssertionError("Dynamic B Node missing")


class LaunchWiring(unittest.TestCase):
    def setUp(self):
        self.modules = patch.dict(sys.modules, launch_modules())
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.vrx = load_launch(patched_bytes(MIRROR.read_bytes()), "patched_vrx_launch")
        self.parameters = find_b_parameters(self.vrx.generate_launch_description())

    def test_old_entry_resolves_vehicle_and_solver_limits_from_original_plant(self):
        context = {"effective_vehicle": "/legacy/effective_vehicle.yaml", "plant_tmax": 25, "plant_tmin": -25}
        self.assertEqual(self.parameters[1].perform(context), context["effective_vehicle"])
        self.assertEqual(self.parameters[-1]["dynamic.T_max"].evaluate(context), 25.0)
        self.assertEqual(self.parameters[-1]["dynamic.T_min"].evaluate(context), -25.0)

    def test_plant_limit_change_cannot_change_independent_b_solver_limits(self):
        context = {"effective_vehicle": "/plant/effective_vehicle.yaml", "plant_tmax": 20,
                   "plant_tmin": -25, "controller_vehicle": "/nominal/nominal_effective.yaml",
                   "controller_tmax": 25, "controller_tmin": -25}
        self.assertEqual(self.parameters[1].perform(context), context["controller_vehicle"])
        self.assertEqual(self.parameters[-1]["dynamic.T_max"].evaluate(context), 25.0)
        context["plant_tmax"] = 18
        self.assertEqual(self.parameters[-1]["dynamic.T_max"].evaluate(context), 25.0)
        context["controller_tmax"] = 20
        self.assertEqual(self.parameters[-1]["dynamic.T_max"].evaluate(context), 20.0)
        self.assertEqual(context["plant_tmax"], 18)

    def wrapper_context(self, root):
        nominal = json.loads((HERE / "p0_nominal_f3.yaml").read_text(encoding="utf-8"))
        plant = copy.deepcopy(nominal)
        plant["/**"]["ros__parameters"]["vehicle"].update({"Yr_dot": 0.0, "Nv_dot": -0.363545})
        for name, document in (("nominal", nominal), ("plant", plant),
                               ("simulation", {"added_mass_cross_policy": "symmetric_mean"})):
            (root / (name + ".yaml")).write_text(json.dumps(document), encoding="utf-8")
        (root / "reference.yaml").write_text("{}", encoding="utf-8")
        return {
            "research_run_id": "wiring_run", "research_baseline_id": "F4_wiring",
            "research_config_hash": "1" * 64, "research_nominal_config_hash": "",
            "nominal_vehicle_config": str(root / "nominal.yaml"),
            "plant_vehicle_config": str(root / "plant.yaml"),
            "simulation_config": str(root / "simulation.yaml"),
            "waypoints_file": str(root / "reference.yaml"),
            "bag_path": str(root / "bag"), "research_output_dir": str(root / "source"),
            "model_output_dir": str(root / "model"), "config_output_dir": str(root / "config"),
            "enable_reference_prediction_logging": "true", "world": "test_world",
            "headless": "true", "paused": "false", "path_frame": "map",
            "research_expected_pose_frame": "map", "research_expected_child_frame": "wamv/base_link",
            "research_frame_contract_verified": "true",
            **{name: "/" + name for name in (
                "odom_topic", "imu_topic", "left_thrust_topic", "right_thrust_topic",
                "path_topic", "profile_topic", "mpc_status_topic", "predicted_trajectory_topic")},
        }

    def test_new_wrapper_uses_two_separate_snapshots_and_binds_actual_nominal_hash(self):
        wrapper = load_launch((HERE / "p0_config_reference_recording.launch.py").read_bytes(), "new_wrapper")
        with tempfile.TemporaryDirectory() as folder:
            context = self.wrapper_context(Path(folder))
            recorder, include = wrapper._setup(context)
            forwarded = dict(include.launch_arguments)
            report = json.loads((Path(folder) / "config/config_sources.json").read_text())
            self.assertEqual(forwarded["vehicle_config"], report["snapshot_paths"]["plant_input"])
            self.assertEqual(forwarded["controller_vehicle"], report["snapshot_paths"]["nominal_effective"])
            self.assertNotEqual(forwarded["vehicle_config"], forwarded["controller_vehicle"])
            self.assertEqual(forwarded["research_nominal_config_hash"], report["nominal_effective_sha256"])
            self.assertEqual(forwarded["controller_tmax"], "25.0")
            self.assertEqual(forwarded["controller_tmin"], "-25.0")
            self.assertEqual(forwarded["enable_reference_prediction_logging"], "true")
            self.assertIn("/research/reference_prediction", recorder.cmd)
            self.assertEqual(len(recorder.cmd[recorder.cmd.index(context["bag_path"]) + 1:]), 13)

    def test_new_wrapper_rejects_wrong_nominal_hash_and_existing_directory(self):
        wrapper = load_launch((HERE / "p0_config_reference_recording.launch.py").read_bytes(), "new_wrapper")
        with tempfile.TemporaryDirectory() as folder:
            context = self.wrapper_context(Path(folder))
            context["research_nominal_config_hash"] = "f" * 64
            with self.assertRaisesRegex(RuntimeError, "nominal_config_hash"):
                wrapper._setup(context)
            with self.assertRaisesRegex(RuntimeError, "existing config_output_dir"):
                wrapper._setup(context)


if __name__ == "__main__":
    unittest.main()
