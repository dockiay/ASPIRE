"""Integration checks that importing the description preserves robot physics."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cap_harness.robosuite.so101_model import (
    SO101_PREFIX,
    build_so101_scene,
    load_so101_description,
)


@pytest.fixture
def imported_robot():
    mujoco = pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    root = Path(__file__).resolve().parents[1]
    if not (root / "third_party/so_arm100/Simulation/SO101/so101_new_calib.xml").is_file():
        pytest.skip("Run bash scripts/bootstrap_so101.sh to install the pinned model")
    description = load_so101_description(root)
    original = mujoco.MjModel.from_xml_path(str(description.model_path))
    scene = build_so101_scene(description)
    return mujoco, original, scene


def test_import_preserves_joints_masses_and_servo_defaults(imported_robot):
    _, original, scene = imported_robot
    imported = scene.compile()
    assert imported.nq == original.nq == 6
    assert imported.nu == original.nu == 6
    assert imported.nmesh == original.nmesh
    for index in range(original.njnt):
        old = original.joint(index)
        new = imported.joint(SO101_PREFIX + old.name)
        np.testing.assert_allclose(new.range, old.range)
        np.testing.assert_allclose(new.pos, old.pos)
        np.testing.assert_allclose(new.axis, old.axis)
    for index in range(1, original.nbody):
        old = original.body(index)
        new = imported.body(SO101_PREFIX + old.name)
        np.testing.assert_allclose(new.mass, old.mass)
        np.testing.assert_allclose(new.inertia, old.inertia)
    for attribute in (
        "dof_damping", "dof_frictionloss", "dof_armature",
        "actuator_gainprm", "actuator_biasprm", "actuator_ctrlrange", "actuator_forcerange",
        "geom_contype", "geom_conaffinity", "geom_friction",
    ):
        expected = getattr(original, attribute)
        actual = getattr(imported, attribute)
        if attribute.startswith("geom_"):
            # The imported scene adds one work-surface geom before the robot geoms.
            actual = actual[1:]
        np.testing.assert_allclose(actual, expected, err_msg=attribute)


def test_exported_scene_reopens_with_its_meshes(imported_robot, tmp_path):
    mujoco, original, scene = imported_robot
    scene.compile()
    target = tmp_path / "scene.xml"
    target.write_text(scene.to_xml(), encoding="utf-8")
    imported = mujoco.MjModel.from_xml_path(str(target))
    assert imported.nmesh == original.nmesh
    assert imported.nq == original.nq
    assert imported.nu == original.nu
