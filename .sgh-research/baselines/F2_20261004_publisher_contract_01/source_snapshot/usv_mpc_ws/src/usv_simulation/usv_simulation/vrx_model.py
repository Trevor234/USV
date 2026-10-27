"""Build a native SDF boat from identified parameters (SI, body FLU).

The source fit is never edited. Native DART added mass is symmetric; the
configured projection is also returned for the simulation controller.
"""

import argparse
import copy
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import yaml


HULL_STATIONS = [(-.5, .72, .75), (-.36, .94, .96), (-.16, 1, 1),
                 (.13, .98, 1), (.30, .79, .77), (.43, .40, .32),
                 (.5, .008, .025)]


def element(parent, tag, value=None, **attrs):
    child = ET.SubElement(parent, tag, attrs)
    if value is not None:
        child.text = str(value)
    return child


def numbers(values):
    return " ".join(f"{float(v):.12g}" for v in values)


def write_xml(root, path):
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def load_parameters(vehicle_file, simulation_file):
    with open(vehicle_file, encoding="utf-8") as stream:
        source = yaml.safe_load(stream)["/**"]["ros__parameters"]
    with open(simulation_file, encoding="utf-8") as stream:
        settings = yaml.safe_load(stream)
    params = copy.deepcopy(source)
    vehicle = params["vehicle"]
    warnings = []
    for block in (vehicle, params["thruster"]):
        for key, value in block.items():
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{key} must be a finite number")
    for key, value in settings.items():
        if key != "added_mass_cross_policy" and (
                not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise ValueError(f"{key} must be a finite number")
    for key in ("mass", "Iz", "length", "beam", "draft", "height", "d_thruster"):
        if vehicle[key] <= 0:
            raise ValueError(f"vehicle.{key} must be positive")
    for key in ("fluid_density", "roll_inertia", "pitch_inertia", "rotor_mass",
                "propeller_diameter", "thrust_coefficient", "buoyancy_radius",
                "buoyancy_half_length_fraction", "buoyancy_half_beam_fraction"):
        if settings[key] <= 0:
            raise ValueError(f"{key} must be positive")
    for key in ("T_max_forward", "T_max_reverse"):
        if params["thruster"][key] <= 0:
            raise ValueError(f"thruster.{key} must be positive")
    for key in ("Xu", "Yv", "Nr", "Xuu", "Yvv", "Nrr"):
        if vehicle[key] > 0:
            raise ValueError(f"vehicle.{key} must use the negative Fossen convention")
    policy = settings["added_mass_cross_policy"]
    if policy not in ("symmetric_mean", "strict"):
        raise ValueError("added_mass_cross_policy must be symmetric_mean or strict")
    if not math.isclose(vehicle["Yr_dot"], vehicle["Nv_dot"], abs_tol=1e-9):
        if policy == "strict":
            raise ValueError("Native added mass requires Yr_dot == Nv_dot")
        mean = (vehicle["Yr_dot"] + vehicle["Nv_dot"]) / 2
        warnings.append(
            f"Simulation projection: Yr_dot={vehicle['Yr_dot']}, "
            f"Nv_dot={vehicle['Nv_dot']} -> both {mean}; original fit unchanged.")
        vehicle["Yr_dot"] = vehicle["Nv_dot"] = mean
    added = np.array([[-vehicle["Xu_dot"], 0, 0],
                      [0, -vehicle["Yv_dot"], -vehicle["Yr_dot"]],
                      [0, -vehicle["Nv_dot"], -vehicle["Nr_dot"]]])
    if np.linalg.eigvalsh(added).min() < -1e-10:
        raise ValueError("Projected planar added mass must be positive semidefinite")
    if settings["buoyancy_radius"] < vehicle["draft"]:
        raise ValueError("Surface clamps depth to radius: radius must be >= draft")
    if any(value < 0 for key, value in settings.items() if "drag" in key):
        raise ValueError("Simulation-only drag magnitudes must be nonnegative")
    if (abs(vehicle["xg"]) + settings["buoyancy_half_length_fraction"] *
            vehicle["length"] >= vehicle["length"] / 2):
        raise ValueError("Buoyancy samples must lie within hull length")
    if settings["buoyancy_half_beam_fraction"] >= 0.5:
        raise ValueError("Buoyancy samples must lie within hull beam")
    return params, settings, warnings


def circle_segment(radius, depth):
    return (radius**2 * math.acos((radius-depth) / radius)
            - (radius-depth) * math.sqrt(2*radius*depth - depth**2))


def hull_mesh(vehicle, density):
    """Original hard-chine hull, closed triangles; submerged volume = m/rho.

    Station cross sections have a V bottom, a waterline chine and flared topsides.
    Width is solved using the volume of the triangulated underwater mesh.
    """
    def vertices(waterline_beam):
        result = []
        for x, width, depth in HULL_STATIONS:
            x *= vehicle["length"]
            wb = waterline_beam * width / 2
            db = vehicle["beam"] * width / 2
            result.extend([(x, 0, -vehicle["draft"] * depth),
                           (x, -wb, 0), (x, -db, vehicle["height"]),
                           (x, db, vehicle["height"]), (x, wb, 0)])
        return np.array(result)

    faces = []
    for station in range(len(HULL_STATIONS)-1):
        for j in range(5):
            a, b = station*5+j, station*5+(j+1) % 5
            faces.extend([(a, a+5, b), (b, a+5, b+5)])
    faces.extend([(0, j, j+1) for j in range(1, 4)])
    last = 5*(len(HULL_STATIONS)-1)
    faces.extend([(last, last+j+1, last+j) for j in range(1, 4)])
    faces = np.array(faces)

    def submerged_volume(verts):
        # Clip at z=0. Top cap contributes zero to signed tetrahedron volumes.
        triangles = verts[faces]
        underwater = triangles[np.max(triangles[:, :, 2], axis=1) <= 1e-12]
        # End caps include the full side profile; add only underwater triangles.
        caps = verts[[[0, 1, 4], [last, last+4, last+1]]]
        underwater = np.concatenate([underwater, caps])
        return abs(np.einsum("ij,ij->i", underwater[:, 0],
                            np.cross(underwater[:, 1], underwater[:, 2])).sum()/6)

    wl_beam = vehicle["mass"] / density / submerged_volume(vertices(1.0))
    if wl_beam >= vehicle["beam"]:
        raise ValueError("Displacement too large for this flared V-hull; change geometry")
    verts = vertices(wl_beam)
    signed = np.einsum("ij,ij->i", verts[faces[:, 0]],
                      np.cross(verts[faces[:, 1]], verts[faces[:, 2]])).sum()
    if signed < 0:
        faces = faces[:, ::-1]
    return verts, faces, wl_beam


def write_collada(vertices, faces, path):
    normals = np.zeros_like(vertices)
    for a, b, c in faces:
        normal = np.cross(vertices[b]-vertices[a], vertices[c]-vertices[a])
        normals[[a, b, c]] += normal
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    root = ET.Element("COLLADA", xmlns="http://www.collada.org/2005/11/COLLADASchema",
                      version="1.4.1")
    asset = element(root, "asset")
    element(asset, "created", "2026-09-14T00:00:00Z")
    element(asset, "modified", "2026-09-14T00:00:00Z")
    element(asset, "unit", name="meter", meter="1")
    element(asset, "up_axis", "Z_UP")
    geometries = element(root, "library_geometries")
    mesh = element(element(geometries, "geometry", id="hull", name="hull"), "mesh")
    for label, data in (("positions", vertices), ("normals", normals)):
        source = element(mesh, "source", id=label)
        element(source, "float_array", numbers(data.ravel()),
                id=f"{label}-array", count=str(data.size))
        accessor = element(element(source, "technique_common"), "accessor",
                           source=f"#{label}-array", count=str(len(data)), stride="3")
        for axis in "XYZ":
            element(accessor, "param", name=axis, type="float")
    element(element(mesh, "vertices", id="vertices"), "input",
            semantic="POSITION", source="#positions")
    tris = element(mesh, "triangles", count=str(len(faces)))
    element(tris, "input", semantic="VERTEX", source="#vertices", offset="0")
    element(tris, "input", semantic="NORMAL", source="#normals", offset="1")
    element(tris, "p", " ".join(str(int(i)) for i in np.repeat(faces.ravel(), 2)))
    scenes = element(root, "library_visual_scenes")
    node = element(element(scenes, "visual_scene", id="Scene"), "node", id="Hull")
    element(node, "instance_geometry", url="#hull")
    element(element(root, "scene"), "instance_visual_scene", url="#Scene")
    write_xml(root, path)


def visual(link, name, kind, dimensions, pose, color):
    vis = element(link, "visual", name=name)
    element(vis, "pose", numbers(pose))
    geometry = element(element(vis, "geometry"), kind)
    if kind == "box":
        element(geometry, "size", numbers(dimensions))
    elif kind == "cylinder":
        element(geometry, "radius", dimensions[0])
        element(geometry, "length", dimensions[1])
    else:
        element(geometry, "uri", dimensions)
    material = element(vis, "material")
    element(material, "ambient", color)
    element(material, "diffuse", color)
    element(material, "specular", "0.15 0.15 0.15 1")
    return vis


def box_collision(link, name, size, pose):
    """Add a DART-compatible primitive collision approximation."""
    collision = element(link, "collision", name=name)
    element(collision, "pose", numbers(pose))
    box = element(element(collision, "geometry"), "box")
    element(box, "size", numbers(size))
    return collision


def inertia(link, mass, com, tensor):
    eigenvalues = np.linalg.eigvalsh(tensor)
    if mass <= 0 or eigenvalues.min() <= 0 or 2*eigenvalues.max() > eigenvalues.sum():
        raise ValueError("Remaining hull inertia is not physically realizable")
    inertial = element(link, "inertial")
    element(inertial, "pose", numbers([*com, 0, 0, 0]))
    element(inertial, "mass", mass)
    matrix = element(inertial, "inertia")
    for key, i, j in (("ixx", 0, 0), ("iyy", 1, 1), ("izz", 2, 2),
                      ("ixy", 0, 1), ("ixz", 0, 2), ("iyz", 1, 2)):
        element(matrix, key, tensor[i, j])
    return inertial


def plugin(model, filename, name, values):
    result = element(model, "plugin", filename=filename, name=name)
    for tag, value in values.items():
        element(result, tag, value)
    return result


def build_model(vehicle_file, simulation_file, output_dir, name="wamv"):
    params, settings, warnings = load_parameters(vehicle_file, simulation_file)
    v, t, s = params["vehicle"], params["thruster"], settings
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    vertices, faces, wl_beam = hull_mesh(v, s["fluid_density"])
    mesh_path = output / "hull.dae"
    write_collada(vertices, faces, mesh_path)
    root = ET.Element("sdf", version="1.11")
    model = element(root, "model", name=name, canonical_link=f"{name}/base_link")
    element(model, "self_collide", "false")
    base = element(model, "link", name=f"{name}/base_link")
    L, B, H = v["length"], v["beam"], v["height"]
    mr, radius = s["rotor_mass"], s["propeller_diameter"]/2
    rotor_tensor = np.diag([mr*radius**2/2, mr*(3*radius**2+.012**2)/12,
                           mr*(3*radius**2+.012**2)/12])
    centers = [np.array([s["thruster_x_fraction"]*L, side*v["d_thruster"],
                         s["thruster_z"]]) for side in (1, -1)]
    cg = np.array([v["xg"], 0, 0])
    mb = v["mass"] - 2*mr
    if mb <= 0:
        raise ValueError("Total mass must include both rotor masses")
    cb = (v["mass"]*cg - mr*sum(centers))/mb
    tensor = np.diag([s["roll_inertia"], s["pitch_inertia"],
                      v["Iz"] - v["mass"]*v["xg"]**2])
    for mass, center in [(mb, cb), *[(mr, c) for c in centers]]:
        delta = center - cg
        tensor -= mass*(np.eye(3)*np.dot(delta, delta) - np.outer(delta, delta))
    tensor -= 2*rotor_tensor
    inertial = inertia(base, mb, cb, tensor)
    added = element(inertial, "fluid_added_mass")
    for key, value in {"xx": -v["Xu_dot"], "yy": -v["Yv_dot"],
                       "yr": -v["Yr_dot"], "rr": -v["Nr_dot"]}.items():
        element(added, key, value)
    visual(base, "hull_shell", "mesh", mesh_path.as_uri(), [0]*6, ".92 .32 .055 1")
    # DART in Gazebo Harmonic cannot construct an SDF triangle-mesh collision.
    # Use short boxes along the hull so contacts remain available in the VRX engine;
    # the closed mesh is still used for rendering and volume calibration.
    for index, (left, right) in enumerate(zip(HULL_STATIONS, HULL_STATIONS[1:])):
        x0, width0, _ = left
        x1, width1, _ = right
        box_collision(
            base, f"hull_collision_{index}",
            [(x1-x0)*L, max(width0, width1)*B, H+v["draft"]],
            [(x0+x1)*L/2, 0, (H-v["draft"])/2, 0, 0, 0])
    visual(base, "service_hatch", "box", [.47*L, .65*B, .018],
           [-.08*L, 0, H+.009, 0, 0, 0], ".06 .09 .12 1")
    visual(base, "electronics_cover", "box", [.25*L, .42*B, .07],
           [-.04*L, 0, H+.05, 0, 0, 0], ".88 .90 .88 1")
    visual(base, "instrument_mast", "cylinder", [.008, .20],
           [.02*L, 0, H+.17, 0, 0, 0], ".22 .25 .27 1")
    visual(base, "gnss_radome", "cylinder", [.034, .024],
           [.02*L, 0, H+.28, 0, 0, 0], ".94 .94 .91 1")
    for side, color in [(1, ".85 .025 .02 1"), (-1, ".015 .65 .10 1")]:
        visual(base, f"navigation_light_{side}", "box", [.04, .025, .018],
               [.15*L, side*.27*B, H+.023, 0, 0, 0], color)
        visual(base, f"deck_rail_{side}", "box", [.52*L, .018, .024],
               [-.12*L, side*.40*B, H+.012, 0, 0, 0], ".10 .12 .14 1")
    for label, center in zip(("left", "right"), centers):
        visual(base, f"{label}_pod", "cylinder", [radius*1.12, .13],
               [*(center + [.02, 0, 0]), 0, math.pi/2, 0], ".08 .11 .14 1")
        visual(base, f"{label}_bracket", "box", [.025, .024, H+.05-center[2]],
               [center[0]+.04, center[1], (H+center[2])*.5, 0, 0, 0], ".2 .23 .25 1")
        rotor = element(model, "link", name=f"{name}/{label}_propeller_link")
        element(rotor, "pose", numbers([*center, 0, 0, 0]))
        inertia(rotor, mr, [0, 0, 0], rotor_tensor)
        visual(rotor, "hub", "cylinder", [radius*.22, .025],
               [-.065, 0, 0, 0, math.pi/2, 0], ".55 .58 .61 1")
        for angle in (0, math.pi/2):
            visual(rotor, f"blade_{angle}", "box", [.008, radius*1.9, .014],
                   [-.07, 0, 0, angle, 0, 0], ".65 .69 .72 1")
        joint = element(model, "joint", name=f"{name}/{label}_engine_propeller_joint",
                        type="revolute")
        element(joint, "parent", f"{name}/base_link")
        element(joint, "child", f"{name}/{label}_propeller_link")
        element(element(joint, "axis"), "xyz", "1 0 0")
        plugin(model, "gz-sim-thruster-system", "gz::sim::systems::Thruster", {
            "joint_name": joint.attrib["name"], "namespace": name,
            "topic": f"thrusters/{label}/thrust", "name": label,
            "thrust_coefficient": s["thrust_coefficient"],
            "fluid_density": s["fluid_density"],
            "propeller_diameter": s["propeller_diameter"],
            "velocity_control": "true", "use_angvel_cmd": "false",
            "min_thrust_cmd": -t["T_max_reverse"], "max_thrust_cmd": t["T_max_forward"]})
    surface_length = v["mass"] / s["fluid_density"] / circle_segment(
        s["buoyancy_radius"], v["draft"])
    surface = plugin(model, "libSurface.so", "vrx::Surface", {
        "link_name": f"{name}/base_link", "hull_length": surface_length,
        "points_in_link_frame": "true",
        "hull_radius": s["buoyancy_radius"], "fluid_density": s["fluid_density"],
        "fluid_level": s["fluid_level"]})
    points = element(surface, "points")
    for longitudinal in (-1, 1):
        for lateral in (-1, 1):
            element(points, "point", numbers([
                v["xg"] + longitudinal*s["buoyancy_half_length_fraction"]*L,
                lateral*s["buoyancy_half_beam_fraction"]*B, -v["draft"]]))
    wavefield = element(surface, "wavefield")
    element(wavefield, "topic", "/vrx/wavefield/parameters")
    # VRX's default PMS gain is 1 even when amplitude is 0. Start calm;
    # a VRX world may subsequently publish its chosen sea state on the topic.
    wave = element(wavefield, "wave")
    element(wave, "gain", 0)
    element(wave, "amplitude", 0)
    drag = {"link_name": f"{name}/base_link", "disable_added_mass": "true",
            "disable_coriolis": "true", "default_current": "0 0 0"}
    for key, source in {"xU": "Xu", "xUabsU": "Xuu", "yV": "Yv", "yVabsV": "Yvv",
                        "yR": "Yr", "yRabsR": "Yrr", "nV": "Nv", "nVabsV": "Nvv",
                        "nR": "Nr", "nRabsR": "Nrr"}.items():
        drag[key] = v[source]
    for key, source in {"zW": "heave_linear_drag", "zWabsW": "heave_quadratic_drag",
                        "kP": "roll_linear_drag", "kPabsP": "roll_quadratic_drag",
                        "mQ": "pitch_linear_drag", "mQabsQ": "pitch_quadratic_drag"}.items():
        drag[key] = -s[source]
    plugin(model, "gz-sim-hydrodynamics-system", "gz::sim::systems::Hydrodynamics", drag)
    sensor = element(base, "sensor", name="imu_sensor", type="imu")
    element(sensor, "always_on", "true")
    element(sensor, "update_rate", 100)
    imu = element(sensor, "imu")
    for component, sigma in [("angular_velocity", s["imu_angular_stddev"]),
                             ("linear_acceleration", s["imu_acceleration_stddev"])]:
        axes = element(imu, component)
        for axis in "xyz":
            noise = element(element(axes, axis), "noise", type="gaussian")
            element(noise, "mean", 0)
            element(noise, "stddev", sigma)
    plugin(model, "gz-sim-odometry-publisher-system", "gz::sim::systems::OdometryPublisher", {
        "dimensions": 3, "odom_publish_frequency": 50, "odom_frame": "map",
        "robot_base_frame": f"{name}/base_link"})
    plugin(model, "gz-sim-joint-state-publisher-system", "gz::sim::systems::JointStatePublisher", {})
    write_xml(root, output / "model.sdf")
    # URDF is for robot_state_publisher / RViz only. Native fluid_added_mass
    # remains in model.sdf and is never round-tripped through URDF.
    robot = ET.Element("robot", name=name)
    for sdf_link in model.findall("link"):
        urdf_link = element(robot, "link", name=sdf_link.attrib["name"])
        for sdf_visual in sdf_link.findall("visual"):
            urdf_visual = element(urdf_link, "visual", name=sdf_visual.attrib["name"])
            pose = sdf_visual.findtext("pose").split()
            element(urdf_visual, "origin", xyz=" ".join(pose[:3]), rpy=" ".join(pose[3:]))
            shape = list(sdf_visual.find("geometry"))[0]
            attributes = {child.tag: child.text for child in shape}
            if shape.tag == "mesh":
                attributes = {"filename": attributes["uri"]}
            element(element(urdf_visual, "geometry"), shape.tag, **attributes)
            element(element(urdf_visual, "material", name=sdf_visual.attrib["name"]),
                    "color", rgba=sdf_visual.findtext("material/diffuse"))
    for label, center in zip(("left", "right"), centers):
        joint = element(robot, "joint", name=f"{name}/{label}_engine_propeller_joint", type="continuous")
        element(joint, "parent", link=f"{name}/base_link")
        element(joint, "child", link=f"{name}/{label}_propeller_link")
        element(joint, "origin", xyz=numbers(center), rpy="0 0 0")
        element(joint, "axis", xyz="1 0 0")
    write_xml(robot, output / "model.urdf")
    with (output / "effective_vehicle.yaml").open("w", encoding="utf-8") as stream:
        yaml.safe_dump({"/**": {"ros__parameters": params}}, stream, sort_keys=False)
    report = {"vehicle_source": str(Path(vehicle_file).resolve()),
              "simulation_source": str(Path(simulation_file).resolve()), "warnings": warnings,
              "mass_kg": v["mass"], "com_m": cg.tolist(), "yaw_inertia_at_origin": v["Iz"],
              "yaw_inertia_at_com": v["Iz"]-v["mass"]*v["xg"]**2,
              "waterline_beam_m": wl_beam, "displacement_m3": v["mass"]/s["fluid_density"],
              "surface_equivalent_length_m": surface_length, "effective_vehicle": v,
              "sdf": str(output / "model.sdf")}
    (output / "model_report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vehicle", required=True)
    parser.add_argument("--simulation", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(build_model(args.vehicle, args.simulation, args.output), indent=2))


if __name__ == "__main__":
    main()
