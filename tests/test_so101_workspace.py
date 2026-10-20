"""A model-derived depth crop must retain the whole robot's reachable geometry."""

import itertools
from types import SimpleNamespace

import numpy as np
import pytest

from cap_harness.api import CapApi
from cap_harness.so101.adapter import SO101Adapter


@pytest.fixture(scope="module")
def robot_workspace():
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    adapter = SO101Adapter()
    bounds = adapter.planning_workspace()
    return adapter, bounds, adapter._effector_geometry.robot


def test_workspace_contains_mesh_vertices_at_joint_and_jaw_extremes(robot_workspace):
    adapter, (lower, upper), robot = robot_workspace
    model = robot.model
    configurations = [
        np.where(bits, robot.high[:5], robot.low[:5])
        for bits in itertools.product([False, True], repeat=5)
    ]
    random = np.random.default_rng(318)
    configurations.extend(random.uniform(robot.low[:5], robot.high[:5], (16, 5)))
    # Whole meshes, including noncollision visuals and the moving jaw; this
    # verifies the frame and compiled geometry interpretation independently.
    for joints in configurations:
        for opening in (0.0, 0.5, 1.0):
            robot.forward(joints, opening)
            for geom in range(model.ngeom):
                if not model.body(int(model.geom_bodyid[geom])).name.startswith("so101_"):
                    continue
                mesh = int(model.geom_dataid[geom])
                if mesh < 0:
                    continue
                start = int(model.mesh_vertadr[mesh])
                count = int(model.mesh_vertnum[mesh])
                vertices = model.mesh_vert[start : start + count]
                points = (
                    vertices @ robot.data.geom_xmat[geom].reshape(3, 3).T
                    + robot.data.geom_xpos[geom]
                )
                assert np.all(points >= lower) and np.all(points <= upper)
    np.testing.assert_array_equal(adapter.planning_workspace(), (lower, upper))


def test_workspace_crop_retains_boundary_and_discards_only_distant_background(robot_workspace):
    adapter, (lower, upper), _robot = robot_workspace
    api = CapApi(adapter)
    boundary = np.array(list(itertools.product(*zip(lower, upper, strict=True))))
    points = np.vstack([boundary, np.zeros(3), upper * 2, lower * 2])
    cropped = api._crop_to_planning_workspace(points, "so101_base")
    np.testing.assert_array_equal(cropped, points[:-2])
    # Callers cannot shrink future crops by modifying returned arrays.
    returned_lower, returned_upper = adapter.planning_workspace()
    returned_lower[:] = 0
    returned_upper[:] = 0
    np.testing.assert_array_equal(adapter.planning_workspace(), (lower, upper))


def test_workspace_accounts_for_nonzero_joint_anchor_and_geom_extent():
    # Analytical counterexample to using body offsets alone: a rotating body's
    # origin may move by twice its off-origin joint-anchor distance.
    model = SimpleNamespace(
        nbody=3,
        ngeom=1,
        body=lambda name: SimpleNamespace(id=1),
        body_parentid=np.array([0, 0, 1]),
        body_pos=np.array([[0, 0, 0], [0, 0, 0], [0.2, 0, 0]]),
        body_jntadr=np.array([-1, -1, 0]),
        body_jntnum=np.array([0, 0, 1]),
        jnt_type=np.array([3]),
        jnt_pos=np.array([[0.1, 0, 0]]),
        geom_bodyid=np.array([2]),
        geom_type=np.array([7]),
        geom_pos=np.array([[0.05, 0, 0]]),
        geom_rbound=np.array([0.03]),
    )
    adapter = SO101Adapter()
    adapter._effector_geometry = SimpleNamespace(robot=SimpleNamespace(model=model))
    lower, upper = adapter.planning_workspace()
    np.testing.assert_allclose(upper, [0.48] * 3)
    np.testing.assert_allclose(lower, [-0.48] * 3)
