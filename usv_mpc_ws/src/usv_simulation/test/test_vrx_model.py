"""Physical consistency checks against the generated Gazebo artifact."""

from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pytest
import yaml

from usv_simulation.vrx_model import build_model, circle_segment, hull_mesh, load_parameters

PACKAGE = Path(__file__).resolve().parents[1]
VEHICLE = PACKAGE.parent / "usv_bringup/config/usv_params_sim.yaml"
SETTINGS = PACKAGE / "config/vrx_model.yaml"


@pytest.fixture
def boat(tmp_path):
    report = build_model(VEHICLE, SETTINGS, tmp_path)
    return ET.parse(tmp_path / "model.sdf").getroot().find("model"), report


def test_assembled_mass_cg_and_inertia_include_rotors(boat):
    model, report = boat
    mass, first_moment, yaw_origin = 0, np.zeros(3), 0
    for link in model.findall("link"):
        origin = np.fromstring(link.findtext("pose", "0 0 0 0 0 0"), sep=" ")[:3]
        inertia = link.find("inertial")
        center = origin + np.fromstring(inertia.findtext("pose"), sep=" ")[:3]
        m = float(inertia.findtext("mass"))
        mass += m
        first_moment += m * center
        yaw_origin += float(inertia.findtext("inertia/izz")) + m*np.dot(center[:2], center[:2])
    assert mass == pytest.approx(14.2)
    assert first_moment / mass == pytest.approx([.12, 0, 0], abs=1e-12)
    assert yaw_origin == pytest.approx(2.13)
    assert report["yaw_inertia_at_com"] == pytest.approx(1.92552)


def test_displacement_and_roll_pitch_restoring_samples(boat):
    model, report = boat
    surface = model.find("plugin[@name='vrx::Surface']")
    assert surface.findtext("points_in_link_frame") == "true"
    assert surface.findtext("wavefield/wave/gain") == "0"
    length = float(surface.findtext("hull_length"))
    radius = float(surface.findtext("hull_radius"))
    rho = float(surface.findtext("fluid_density"))
    points = np.array([np.fromstring(p.text, sep=" ") for p in surface.findall("points/point")])
    assert rho*length*circle_segment(radius, .1) == pytest.approx(14.2)
    assert points.mean(axis=0) == pytest.approx([.12, 0, -.1])
    assert np.ptp(points[:, 0]) > 0
    assert np.ptp(points[:, 1]) > 0


def test_native_added_mass_and_damping_have_no_double_count(boat):
    model, report = boat
    added = model.find("link/inertial/fluid_added_mass")
    assert float(added.findtext("xx")) == 2
    assert float(added.findtext("yy")) == 8
    assert float(added.findtext("rr")) == 3.41
    assert float(added.findtext("yr")) == pytest.approx(.1817725)
    hydro = model.find("plugin[@name='gz::sim::systems::Hydrodynamics']")
    assert hydro.findtext("disable_added_mass") == "true"
    assert hydro.findtext("disable_coriolis") == "true"
    assert not hydro.findall("xDotU")
    assert model.find("plugin[@name='vrx::SimpleHydrodynamics']") is None
    assert float(hydro.findtext("xU")) == -2.272063
    assert float(hydro.findtext("xUabsU")) == -11.571784
    assert float(hydro.findtext("nRabsR")) == -.71
    assert report["effective_vehicle"]["Yr_dot"] == report["effective_vehicle"]["Nv_dot"]
    assert report["warnings"]


def test_raw_fit_is_unchanged_and_strict_policy_rejects_asymmetry(tmp_path):
    before = VEHICLE.read_bytes()
    build_model(VEHICLE, SETTINGS, tmp_path / "model")
    assert VEHICLE.read_bytes() == before
    settings = yaml.safe_load(SETTINGS.read_text())
    settings["added_mass_cross_policy"] = "strict"
    config = tmp_path / "strict.yaml"
    config.write_text(yaml.safe_dump(settings))
    with pytest.raises(ValueError, match="Yr_dot == Nv_dot"):
        load_parameters(VEHICLE, config)


def test_thruster_lever_and_limits_are_identified(boat):
    model, _ = boat
    for label, y in (("left", .25), ("right", -.25)):
        rotor = model.find(f"link[@name='wamv/{label}_propeller_link']")
        assert float(rotor.findtext("pose").split()[1]) == y
    for thruster in model.findall("plugin[@name='gz::sim::systems::Thruster']"):
        assert float(thruster.findtext("max_thrust_cmd")) == 25
        assert float(thruster.findtext("min_thrust_cmd")) == -25
        assert thruster.findtext("use_angvel_cmd") == "false"


def test_generated_hull_is_closed_outward_and_has_requested_envelope():
    params, settings, _ = load_parameters(VEHICLE, SETTINGS)
    vertices, faces, _ = hull_mesh(params["vehicle"], settings["fluid_density"])
    edges = {}
    for tri in faces:
        for a, b in zip(tri, np.roll(tri, -1)):
            key = tuple(sorted([a, b]))
            edges.setdefault(key, []).append((a, b))
    assert all(len(pair) == 2 and pair[0] == pair[1][::-1] for pair in edges.values())
    assert np.ptp(vertices[:, 0]) == pytest.approx(1.2)
    assert np.ptp(vertices[:, 1]) == pytest.approx(.6)
    assert np.min(vertices[:, 2]) == -.1
    assert np.max(vertices[:, 2]) == .3
    tris = vertices[faces]
    volume = np.einsum("ij,ij->i", tris[:, 0], np.cross(tris[:, 1], tris[:, 2])).sum()/6
    assert volume > .0142


def test_collision_uses_dart_supported_primitives(boat):
    model, _ = boat
    collisions = model.findall("link[@name='wamv/base_link']/collision")
    assert len(collisions) == 6
    assert not model.findall(".//collision/geometry/mesh")
    assert all(c.find("geometry/box/size") is not None for c in collisions)
