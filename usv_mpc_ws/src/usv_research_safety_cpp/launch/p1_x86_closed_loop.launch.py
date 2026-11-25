# Copyright 2026 USV Developer
# SPDX-License-Identifier: MIT
"""受控仿真闭环的 launch。三个节点 + 计划身份，全部显式传入，无隐式默认。"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    args = [
        DeclareLaunchArgument("run_id"),
        DeclareLaunchArgument("contract_file"),
        DeclareLaunchArgument("contract_hash"),
        DeclareLaunchArgument("model_plan_file"),
        DeclareLaunchArgument("model_plan_sha256"),
        DeclareLaunchArgument("out_dir"),
        # plant 必须拿到场景路径文件；regulator 必须拿到真实 worker pid
        # （它用 pidfd 监视该进程，不猜、不轮询进程名）。
        DeclareLaunchArgument("scenario_path_file"),
        DeclareLaunchArgument("worker_pid"),
    ]

    common = {
        "run_id": LaunchConfiguration("run_id"),
        "contract_file": LaunchConfiguration("contract_file"),
        "contract_hash": LaunchConfiguration("contract_hash"),
        "model_plan_file": LaunchConfiguration("model_plan_file"),
        "model_plan_sha256": LaunchConfiguration("model_plan_sha256"),
    }

    return LaunchDescription(args + [
        Node(package="usv_research_safety_cpp", executable="p1_x86_plant",
             name="p1_x86_plant", output="screen",
             parameters=[common, {
                 "source_file": [LaunchConfiguration("out_dir"), "/plant.source.jsonl"],
                 "scenario_path_file": LaunchConfiguration("scenario_path_file")}]),
        Node(package="usv_research_safety_cpp", executable="p1_solver_worker",
             name="p1_solver_worker", output="screen",
             parameters=[common, {"mode": "controlled_sim",
                                  "source_file": [LaunchConfiguration("out_dir"), "/worker.source.jsonl"]}]),
        Node(package="usv_research_safety_cpp", executable="p1_regulator",
             name="p1_regulator", output="screen",
             parameters=[common, {"mode": "controlled_sim",
                                  "worker_pid": LaunchConfiguration("worker_pid"),
                                  "recording_observer_node": "p1_x86_plant",
                                  "source_file": [LaunchConfiguration("out_dir"), "/regulator.source.jsonl"]}]),
    ])
