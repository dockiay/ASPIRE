"""Pinned SO-101 description and Robosuite world composition.

This is a model import, shared by model checks and the SO-101 simulation adapter.
MuJoCo's spec attachment preserves upstream defaults, meshes and servo parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
import os
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING
import xml.etree.ElementTree as ET

if TYPE_CHECKING:
    import mujoco

SO101_PREFIX = "so101_"


@dataclass(frozen=True)
class SO101Description:
    """Identity of the unmodified manufacturer description."""

    model_path: Path
    commit: str
    arm_joints: tuple[str, ...]
    gripper_joint: str

    @property
    def scene_joint_names(self) -> tuple[str, ...]:
        return tuple(SO101_PREFIX + name for name in (*self.arm_joints, self.gripper_joint))


def load_so101_description(repo_root: Path | None = None) -> SO101Description:
    """Require the pinned, clean source checkout installed by bootstrap_so101.sh."""
    root = repo_root or Path(__file__).resolve().parents[3]
    config = json.loads(
        files("cap_harness").joinpath("configs/robots/so101.json").read_text(encoding="utf-8")
    )
    configured = os.environ.get("CAP_HARNESS_SO101_MODEL_ROOT")
    checkout = Path(configured).expanduser().resolve() if configured else root / config["checkout"]
    model_path = checkout / config["model"]
    if not model_path.is_file():
        raise FileNotFoundError("SO-101 description missing; run bash scripts/bootstrap_so101.sh")
    revision = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if revision != config["commit"]:
        raise ValueError(f"SO-101 revision mismatch: {revision} != {config['commit']}")
    changes = subprocess.run(
        ["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=no"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if changes:
        raise ValueError("SO-101 source has local changes; preserve the pinned description")
    return SO101Description(
        model_path=model_path,
        commit=revision,
        arm_joints=tuple(config["arm_joints"]),
        gripper_joint=config["gripper_joint"],
    )


def build_so101_scene(description: SO101Description) -> mujoco.MjSpec:
    """Attach the entire official model to a simple Robosuite world.

    Robosuite 1.4's XML loader cannot flatten the upstream nested default classes.
    Native spec attachment handles them without rewriting the manufacturer's files.
    The result supplies model checks and the SO-101 simulation profile.
    """
    import mujoco
    from robosuite.models import MujocoWorldBase

    world = MujocoWorldBase()
    world.root.set("model", "so101_import")
    visual = world.root.find("visual")
    if visual is None:
        visual = ET.SubElement(world.root, "visual")
    ET.SubElement(visual, "global", offwidth="640", offheight="640")
    ET.SubElement(
        world.worldbody, "geom", name="work_surface", type="plane",
        size="0.7 0.7 0.05", pos="0 0 -0.005", rgba="0.82 0.85 0.82 1",
    )
    ET.SubElement(
        world.worldbody, "light", name="scene_light", pos="0 0 2",
        dir="0 0 -1", diffuse="0.8 0.8 0.8",
    )
    scene = mujoco.MjSpec.from_string(world.get_xml())
    robot = mujoco.MjSpec.from_file(str(description.model_path))
    # Attachment resolves assets in memory, but an exported world uses its own
    # meshdir. Absolute source paths make that XML reopen from any output folder.
    mesh_directory = description.model_path.parent / robot.meshdir
    for mesh in robot.meshes:
        mesh.file = str((mesh_directory / mesh.file).resolve())
    mount = scene.worldbody.add_frame(name="so101_mount")
    scene.attach(robot, prefix=SO101_PREFIX, frame=mount)
    return scene
