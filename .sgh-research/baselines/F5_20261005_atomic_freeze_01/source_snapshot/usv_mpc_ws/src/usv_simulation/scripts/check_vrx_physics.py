#!/usr/bin/env python3
"""Headless DART regression: hydrostatics, effective mass, damping, yaw sign.

Use system gz.sim8 Python bindings with matching system libraries. Do not mix
them with ROS vendor libraries (see the guide). Tests a still-water world; forces
in these checks are applied to base_link, bypassing the command/bridge chain.
"""

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import gz.sim8 as sim
from gz.math7 import Vector3d
import numpy as np


def run_case(sdf_path, world_path, case, iterations):
    world_xml = ET.parse(world_path)
    world = world_xml.getroot().find("world")
    world.find("physics/real_time_factor").text = "0"
    model = ET.parse(sdf_path).getroot().find("model")
    if case in ("mass", "yaw_mass", "coupled"):
        world.find("gravity").text = "0 0 0"
        for item in list(model.findall("plugin")):
            if (item.attrib["name"] == "vrx::Surface" or
                    case != "coupled" and item.attrib["name"] == "gz::sim::systems::Hydrodynamics"):
                model.remove(item)
    world.append(model)
    test_world = Path(sdf_path).parent / f"check_{case}.sdf"
    world_xml.write(test_world, encoding="utf-8", xml_declaration=True)
    fixture = sim.TestFixture(str(test_world))
    state = {"link": None, "samples": []}

    def before(info, ecm):
        if state["link"] is None:
            w = sim.World(sim.world_entity(ecm))
            boat = sim.Model(w.model_by_name(ecm, "wamv"))
            state["link"] = sim.Link(boat.link_by_name(ecm, "wamv/base_link"))
            state["link"].enable_velocity_checks(ecm)
            if case == "coupled":
                # A one-step impulse initializes momentum without persistent
                # velocity-command components that would overwrite the dynamics.
                state["link"].add_world_wrench(
                    ecm, Vector3d(16.2*.6/.004, (22.2*.13+1.8857725*.2)/.004, 0),
                    Vector3d(0, 0, (1.8857725*.13+5.54*.2)/.004))
        link = state["link"]
        pose = link.world_pose(ecm)
        time = info.sim_time.total_seconds()
        force, torque = 0.0, 0.0
        if case == "mass":
            force = 1
        elif case == "yaw_mass":
            torque = 1
        elif case == "surge":
            force = 10 if time < 18 else 0
        elif case == "yaw":
            torque = 1 if time < 15 else 0
        elif case == "reverse":
            force = -10
        if force or torque:
            link.add_world_wrench(ecm, pose.rot()*Vector3d(force, 0, 0),
                                  pose.rot()*Vector3d(0, 0, torque))

    def after(info, ecm):
        link = state["link"]
        pose = link.world_pose(ecm)
        vel = link.world_linear_velocity(ecm)
        omega = link.world_angular_velocity(ecm)
        if vel is None or omega is None:
            return
        uvw = pose.rot().inverse()*vel
        pqr = pose.rot().inverse()*omega
        state["samples"].append([
            info.sim_time.total_seconds(), pose.pos().z(), pose.rot().roll(),
            pose.rot().pitch(), uvw.x(), uvw.y(), pqr.z()])

    fixture.on_pre_update(before)
    fixture.on_post_update(after)
    fixture.finalize()
    assert fixture.server().run(True, iterations, False)
    data = np.array(state["samples"])
    if not np.isfinite(data).all():
        raise AssertionError(f"{case}: non-finite state")
    np.savetxt(Path(sdf_path).parent / f"check_{case}.csv", data, delimiter=",",
               header="t,z,roll,pitch,u,v,r", comments="")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--world", required=True)
    parser.add_argument("--case", choices=["float", "mass", "yaw_mass", "surge", "yaw", "reverse", "coupled"],
                        required=True)
    args = parser.parse_args()
    iterations = {"float": 2500, "mass": 10, "yaw_mass": 10, "surge": 7500,
                  "yaw": 7500, "reverse": 5000, "coupled": 30}[args.case]
    data = run_case(args.model, args.world, args.case, iterations)
    result = {"case": args.case, "last": data[-1].tolist(),
              "max_abs_z_roll_pitch": np.max(np.abs(data[:, 1:4]), axis=0).tolist()}
    if args.case == "mass":
        result["measured_surge_mass"] = 1/np.polyfit(data[:, 0], data[:, 4], 1)[0]
        assert abs(result["measured_surge_mass"]-16.2) < .05, result
    if args.case == "yaw_mass":
        matrix = np.array([[22.2, 14.2*.12+.1817725],
                           [14.2*.12+.1817725, 5.54]])
        expected = np.linalg.solve(matrix, [0, 1])[1]
        result["measured_yaw_acceleration"] = np.polyfit(data[:, 0], data[:, 6], 1)[0]
        result["expected_yaw_acceleration"] = expected
        assert abs(result["measured_yaw_acceleration"] / expected - 1) < .01, result
    if args.case == "float":
        assert np.max(np.abs(data[-500:, 1:4])) < .01, result
    if args.case == "surge":
        expected = (-2.272063 + np.sqrt(2.272063**2+4*11.571784*10))/(2*11.571784)
        steady = data[(data[:, 0] > 16) & (data[:, 0] < 17.9), 4].mean()
        result["steady_u"] = float(steady)
        result["expected_steady_u"] = float(expected)
        assert abs(steady-expected) < .025, result
        assert abs(data[-1, 4]) < .05, result
    if args.case == "reverse":
        assert data[-1, 4] < -.7, result
    if args.case == "yaw":
        assert data[(data[:, 0] > 5) & (data[:, 0] < 10), 6].mean() > .05, result
        assert abs(data[-1, 6]) < .025, result
    if args.case == "coupled":
        assert data[2, 4] > .5 and data[2, 5] > .10 and data[2, 6] > .15
        mass = np.array([[16.2, 0, 0], [0, 22.2, 1.8857725], [0, 1.8857725, 5.54]])
        residuals = []
        for previous, following in zip(data[2:-1], data[3:]):
            u, v, r = previous[4:7]
            c13, c23 = -22.2*v-1.8857725*r, 16.2*u
            coriolis = np.array([[0, 0, c13], [0, 0, c23], [-c13, -c23, 0]])
            damping = np.diag([2.272063+11.571784*abs(u), 2.629019+.05*abs(v),
                               3.105+.71*abs(r)])
            expected = np.linalg.solve(mass, -(coriolis+damping) @ [u, v, r])
            measured = (following[4:7]-previous[4:7])/(following[0]-previous[0])
            residuals.append(measured-expected)
        result["max_ode_acceleration_error"] = np.max(np.abs(residuals), axis=0).tolist()
        assert np.max(np.abs(residuals)) < .005, result
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
