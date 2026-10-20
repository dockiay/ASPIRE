"""FruitGym meshes/textures in a fixed SO-101 scene; ASPIRE owns the free fruit."""

import hashlib
import json
import math
import xml.etree.ElementTree as ET

import numpy as np

from cap_harness.so101.paths import workspace_root
from cap_harness.so101.strawberry import FRUIT_POSITION

ROOT = workspace_root()
CONFIG = ROOT / "configs/so101/fruitgym-assets-v1.json"


def resources():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    root = ROOT / config["checkout"]
    for name, digest in config["files"].items():
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(
                f"FruitGym resource missing/modified: {name}. Run python scripts/prepare_fruitgym_assets.py"
            )
    return root / "fruit_gym/envs/xmls", config


def obj_vertices(path):
    return np.array(
        [
            list(map(float, row.split()[1:4]))
            for row in path.read_text(encoding="utf-8").splitlines()
            if row.startswith("v ")
        ]
    )


def add_fruitgym_plant(scene):
    """Import actual upstream assets, fitted to a 36 x 34 x 48 mm target fruit.

    The collision is MuJoCo's convex hull of the fruit mesh; calyx is visual.
    Stems and leaf hubs are rigid in this first integration, not FruitGym springs.
    """
    import mujoco

    root, config = resources()
    for name, relative in {
        "red": "textures_small/r1.png",
        "green": "textures_small/g1.png",
        "calyx": "textures_small/strawberry_leaves.png",
        "leaf": "textures/leaf_g1.png",
    }.items():
        texture = "fg_" + name
        scene.add_texture(
            name=texture, type=mujoco.mjtTexture.mjTEXTURE_2D, file=str(root / relative)
        )
        material = scene.add_material(name=texture, specular=0.1, shininess=0.15)
        material.textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] = texture
    vertices = obj_vertices(root / "assets/sb1.obj")
    # Upstream fruit axis is +Y; rotate to +Z and fit declared lesson dimensions.
    scale = np.array([0.036, 0.048, 0.034]) / np.ptp(vertices, axis=0)
    rotation = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])
    offset = -rotation @ ((vertices.max(0) + vertices.min(0)) / 2 * scale)
    quat = [math.sqrt(0.5), math.sqrt(0.5), 0, 0]
    for name, filename, mesh_scale in [
        ("fruit", "sb1.obj", scale),
        ("calyx", "calyx1.obj", scale),
        ("leaf", "leaf_1.obj", [0.55, 0.55, 0.55]),
    ]:
        scene.add_mesh(name="fg_" + name, file=str(root / "assets" / filename), scale=mesh_scale)
    plant = scene.worldbody.add_body(name="lesson_plant")

    def capsule(name, start, end, radius=0.002):
        plant.add_geom(
            name="plant_" + name,
            type=mujoco.mjtGeom.mjGEOM_CAPSULE,
            size=[radius, 0, 0],
            fromto=[*start, *end],
            rgba=[0.18, 0.3, 0.12, 1],
        )

    plant.add_geom(
        name="plant_pot",
        type=mujoco.mjtGeom.mjGEOM_CYLINDER,
        pos=[0.47, 0.06, 0.035],
        size=[0.052, 0.035, 0],
        rgba=[0.5, 0.25, 0.13, 1],
    )
    plant.add_geom(
        name="plant_soil",
        type=mujoco.mjtGeom.mjGEOM_CYLINDER,
        pos=[0.47, 0.06, 0.073],
        size=[0.048, 0.004, 0],
        rgba=[0.16, 0.09, 0.035, 1],
    )
    crown = [0.47, 0.06, 0.19]
    capsule("crown_stem", [0.47, 0.06, 0.077], crown, 0.003)
    stalk = [0.40, 0.01, 0.32]
    capsule("flower_stalk", crown, stalk, 0.002)
    capsule("target_branch", stalk, [0.365, 0, 0.29], 0.0015)
    # Calyx reaches above the collision hull; keep a physical gap to the fruit.
    capsule("peduncle", [0.365, 0, 0.29], [0.365, 0, 0.268], 0.001)

    def fruit_geoms(owner, prefix, ripe=False, dynamic=False):
        body = owner if dynamic else owner.add_body(name=prefix)
        body.add_geom(
            name="plant_fruit" if dynamic else prefix + "_fruit",
            type=mujoco.mjtGeom.mjGEOM_MESH,
            meshname="fg_fruit",
            pos=offset,
            quat=quat,
            material="fg_red" if ripe else "fg_green",
            mass=0.020,
            condim=4,
            priority=1,
            solref=[0.004, 1],
            friction=[1, 0.005, 0.0001],
        )
        body.add_geom(
            name="plant_fruit_tip" if dynamic else prefix + "_calyx",
            type=mujoco.mjtGeom.mjGEOM_MESH,
            meshname="fg_calyx",
            pos=offset,
            quat=quat,
            material="fg_calyx",
            mass=0,
            contype=0,
            conaffinity=0,
        )
        return body

    fruit = scene.worldbody.add_body(name="lesson_fruit", pos=FRUIT_POSITION)
    fruit.add_freejoint(name="fruit_free")
    fruit_geoms(fruit, "target", ripe=True, dynamic=True)
    scene.add_equality(
        name="fruit_fixture",
        type=mujoco.mjtEq.mjEQ_CONNECT,
        objtype=mujoco.mjtObj.mjOBJ_BODY,
        name1="lesson_fruit",
        name2="lesson_plant",
        data=[0, 0, 0.024, 0, 0, 0, 0, 0, 0, 0, 1],
        solref=[0.01, 1],
        solimp=[0.9, 0.9, 0.001, 0.5, 2],
    )
    for index, position in enumerate(([0.44, 0.095, 0.245], [0.50, 0.015, 0.21])):
        capsule(f"green_stalk_{index}", crown, np.asarray(position) + [0, 0, 0.026], 0.001)
        body = fruit_geoms(plant, f"plant_fg_green_{index}")
        body.pos = position

    # Preserve the three-leaf hub orientations from FruitGym's leaves.xml.
    hub = ET.parse(root / "leaves.xml").find(".//body[@name='hub']")
    for index, (position, yaw) in enumerate(
        (([0.47, 0.13, 0.27], 0.0), ([0.52, 0.03, 0.31], 0.7), ([0.49, -0.025, 0.16], -0.8))
    ):
        capsule(f"petiole_{index}", crown, position, 0.0012)
        leaf_hub = plant.add_body(
            name=f"fg_leaf_hub_{index}",
            pos=position,
            quat=[math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)],
        )
        for leaf_index, node in enumerate(hub.findall("body")):
            angles = np.fromstring(node.get("euler", "0 0 0"), sep=" ")
            # MJCF default is intrinsic xyz Euler, in radians for this template.
            from scipy.spatial.transform import Rotation

            xyzw = Rotation.from_euler("XYZ", angles).as_quat()
            leaf_hub.add_geom(
                name=f"plant_fg_leaf_{index}_{leaf_index}",
                type=mujoco.mjtGeom.mjGEOM_MESH,
                meshname="fg_leaf",
                quat=[xyzw[3], *xyzw[:3]],
                material="fg_leaf",
                mass=0.002,
            )
    return {
        "repository": config["repository"],
        "commit": config["commit"],
        "asset_manifest_sha256": hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        "files": config["files"],
        "layout": "fixed SO-101 layout; FruitGym leaf hub orientations",
        "fruit_size_m": [0.036, 0.034, 0.048],
        "fruit_mesh_scale": scale.tolist(),
        "plant_dynamics": "rigid stems and leaves; uncalibrated load release on target only",
        "fruit_disappears_on_grasp": False,
    }
