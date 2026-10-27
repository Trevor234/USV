#!/usr/bin/env python3
"""Render the actual SDF geometry as a static engineering preview (no Gazebo GUI)."""

import argparse
import itertools
from pathlib import Path
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def transform(vertices, pose):
    x, y, z, r, p, yaw = pose
    cx, cy, cz = np.cos([r, p, yaw])
    sx, sy, sz = np.sin([r, p, yaw])
    rotation = np.array([[cz*cy, cz*sy*sx-sz*cx, cz*sy*cx+sz*sx],
                         [sz*cy, sz*sy*sx+cz*cx, sz*sy*cx-cz*sx],
                         [-sy, cy*sx, cy*cx]])
    return np.asarray(vertices) @ rotation.T + [x, y, z]


def geometry(geom):
    if geom.find("mesh") is not None:
        path = unquote(urlparse(geom.findtext("mesh/uri")).path)
        dae = ET.parse(path)
        ns = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
        values = dae.find(".//c:source[@id='positions']/c:float_array", ns).text
        vertices = np.fromstring(values, sep=" ").reshape(-1, 3)
        triangles = dae.find(".//c:triangles", ns)
        stride = max(int(i.attrib["offset"]) for i in triangles.findall("c:input", ns))+1
        faces = np.fromstring(triangles.find("c:p", ns).text, sep=" ", dtype=int)
        return vertices, faces.reshape(-1, stride)[:, 0].reshape(-1, 3)
    if geom.find("box") is not None:
        size = np.fromstring(geom.findtext("box/size"), sep=" ")
        vertices = np.array(list(itertools.product([-1, 1], repeat=3))) * size / 2
        faces = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1],
                 [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
        return vertices, faces
    radius = float(geom.findtext("cylinder/radius"))
    length = float(geom.findtext("cylinder/length"))
    n = 24
    vertices = np.array([(radius*np.cos(a), radius*np.sin(a), z)
                         for z in (-length/2, length/2)
                         for a in np.linspace(0, 2*np.pi, n, endpoint=False)])
    faces = [[j, (j+1) % n, (j+1) % n+n, j+n] for j in range(n)]
    faces.extend([list(range(n-1, -1, -1)), list(range(n, 2*n))])
    return vertices, faces


def rasterize(shapes, elevation, azimuth, width=1100, height=800):
    """Orthographic triangle z-buffer; keeps deck/hull occlusion correct."""
    el, az = np.deg2rad([elevation, azimuth])
    depth_axis = np.array([np.cos(el)*np.cos(az), np.cos(el)*np.sin(az), np.sin(el)])
    right = np.array([-np.sin(az), np.cos(az), 0])
    up = np.cross(depth_axis, right)
    camera = np.stack([right, up, depth_axis], axis=1)
    all_points = np.concatenate([np.concatenate(faces) for faces, _ in shapes]) @ camera
    low, high = all_points[:, :2].min(axis=0), all_points[:, :2].max(axis=0)
    scale = min(width/(high-low)[0], height/(high-low)[1])*.84
    center = (high+low)/2
    pixels = np.empty((height, width, 3))
    pixels[:] = np.array([238, 243, 245])/255
    depth = np.full((height, width), -np.inf)
    light = np.array([.35, -.45, .82])
    for faces, color in shapes:
        for face in faces:
            for j in range(1, len(face)-1):
                tri = face[[0, j, j+1]]
                normal = np.cross(tri[1]-tri[0], tri[2]-tri[0])
                normal /= max(np.linalg.norm(normal), 1e-12)
                rgb = color[:3]*(.60+.40*abs(normal @ light))
                projected = tri @ camera
                xy = (projected[:, :2]-center)*[scale, -scale]+[width/2, height/2]
                x0, y0 = np.maximum(np.floor(xy.min(axis=0)).astype(int), [0, 0])
                x1, y1 = np.minimum(np.ceil(xy.max(axis=0)).astype(int), [width-1, height-1])
                if x1 < x0 or y1 < y0:
                    continue
                xx, yy = np.meshgrid(np.arange(x0, x1+1)+.5, np.arange(y0, y1+1)+.5)
                a, b, c = xy
                denominator = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                if abs(denominator) < 1e-10:
                    continue
                wa = ((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/denominator
                wb = ((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/denominator
                wc = 1-wa-wb
                z = wa*projected[0, 2]+wb*projected[1, 2]+wc*projected[2, 2]
                target = depth[y0:y1+1, x0:x1+1]
                mask = (wa >= 0) & (wb >= 0) & (wc >= 0) & (z > target)
                target[mask] = z[mask]
                pixels[y0:y1+1, x0:x1+1][mask] = rgb
    return pixels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model")
    parser.add_argument("output")
    args = parser.parse_args()
    model = ET.parse(args.model).getroot().find("model")
    shapes = []
    for link in model.findall("link"):
        link_pose = np.fromstring(link.findtext("pose", "0 0 0 0 0 0"), sep=" ")
        for vis in link.findall("visual"):
            vertices, faces = geometry(vis.find("geometry"))
            pose = np.fromstring(vis.findtext("pose", "0 0 0 0 0 0"), sep=" ")
            vertices = transform(transform(vertices, pose), link_pose)
            rgba = np.fromstring(vis.findtext("material/diffuse"), sep=" ")
            shapes.append(([vertices[f] for f in faces], rgba))
    fig = plt.figure(figsize=(13, 7.5), facecolor="#eef3f5")
    views = [(24, -47, "PERSPECTIVE"), (90, -90, "PLAN"), (0, -90, "PROFILE")]
    for index, (elevation, azimuth, label) in enumerate(views):
        bounds = [.015, .11, .65, .73] if index == 0 else [.70, .55 if index == 1 else .12, .28, .32]
        ax = fig.add_axes(bounds, facecolor="#eef3f5")
        ax.imshow(rasterize(shapes, elevation, azimuth))
        ax.set_axis_off()
        ax.text(.04, .98, label, transform=ax.transAxes, fontsize=9, color="#45616e")
    fig.text(.045, .92, "USV  /  PARAMETRIC VRX MODEL", size=22, weight="bold", color="#15313e")
    fig.text(.047, .875, "Original hull mesh + compact twin thrusters + instrument deck", size=11, color="#4b6571")
    fig.text(.047, .105, "1.20 m LENGTH     0.60 m BEAM     0.10 m DRAFT     14.2 kg TOTAL", size=12,
             color="#15313e", weight="bold")
    fig.text(.047, .065, "Geometry preview from generated SDF. Deck details are conceptual; hydrodynamics use the identification YAML.",
             size=9, color="#516975")
    output = Path(args.output)
    fig.savefig(output, dpi=170, facecolor=fig.get_facecolor())
    print(output.resolve())


if __name__ == "__main__":
    main()
