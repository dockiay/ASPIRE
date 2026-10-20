"""Cross-embodiment API defaults and SO-101 provider selection regressions."""

from types import SimpleNamespace

import numpy as np
import pytest

from cap_harness.api import CapApi
from cap_harness.contracts import (
    CameraObservation,
    GraspCandidate,
    GraspSet,
    MotionStrategy,
    Observation,
    PlanningScene,
    PointCloud,
    Pose,
    RobotState,
)
from cap_harness.geometry import matrix_to_pose


def api_fixture(embodiment="so101", frame="so101_base", **kwargs):
    pose = Pose([0, 0, 0], [1, 0, 0, 0], frame)
    state = RobotState(
        joint_positions=np.zeros(5 if embodiment == "so101" else 7),
        joint_velocities=np.zeros(5 if embodiment == "so101" else 7),
        end_effector_poses=pose,
        gripper_positions=1.0,
        base_frame=frame,
        embodiment=embodiment,
    )
    camera = CameraObservation(
        rgb=np.zeros((2, 2, 3), dtype=np.uint8),
        depth_m=np.ones((2, 2)),
        intrinsics=np.eye(3),
        frame="agentview",
        camera_pose=pose,
    )
    observation = Observation(cameras={"agentview": camera}, robot_state=state)
    adapter = SimpleNamespace(
        embodiment=embodiment,
        get_robot_state=lambda: state,
        get_observation=lambda: observation,
    )
    return CapApi(adapter, **kwargs)


@pytest.mark.parametrize(
    ("embodiment", "frame"),
    [("so101", "so101_base"), ("robosuite", "robot_base"), ("libero", "panda_base")],
)
def test_mask_projection_omitted_frame_uses_observation_base(embodiment, frame):
    api = api_fixture(embodiment, frame)
    cloud = api.mask_to_point_cloud(np.ones((2, 2), dtype=bool), "agentview")
    assert cloud.frame == frame and len(cloud.points) == 4
    with pytest.raises(ValueError, match="camera pose"):
        api.mask_to_point_cloud(np.ones((2, 2), dtype=bool), "agentview", "unrelated_base")


def test_default_grasp_provider_is_configured_not_silently_substituted():
    calls = []
    candidate = GraspCandidate(Pose([0, 0, 0], [1, 0, 0, 0], "so101_base"), 0.5, 0.02)

    def generate(cloud, **kwargs):
        calls.append((cloud, kwargs))
        return GraspSet(ok=True, grasps=[candidate])

    api = api_fixture(
        grasp_providers={"so101-geometric": SimpleNamespace(generate_grasps=generate)},
        default_grasp_backend="so101-geometric",
    )
    result = api.generate_grasps("agentview", np.ones((2, 2), dtype=bool), max_candidates=2)
    assert result.ok and len(calls) == 1
    assert calls[0][0].frame == "so101_base"
    assert calls[0][1]["max_candidates"] == 2
    assert calls[0][1]["scene_point_cloud"].frame == "so101_base"
    assert not api.generate_grasps(
        "agentview", np.ones((2, 2), dtype=bool), backend="contact-graspnet"
    ).ok
    assert len(calls) == 1


def test_so101_top_down_selection_uses_physical_tcp_x_axis():
    api = api_fixture()
    down_x = np.eye(4)
    down_x[:3, :3] = [[0, 0, 1], [0, 1, 0], [-1, 0, 0]]
    down_z = np.diag([1, -1, -1, 1])
    top = GraspCandidate(matrix_to_pose(down_x, frame="so101_base"), 0.3, 0.02)
    side = GraspCandidate(matrix_to_pose(down_z, frame="so101_base"), 0.9, 0.02)
    grasps = GraspSet(ok=True, grasps=[side, top])
    assert api.select_grasp(grasps) is top
    assert api.select_grasp(grasps, "highest_score") is side


def test_so101_contact_target_preserves_fruit_and_surrounding_obstacles(monkeypatch):
    api = api_fixture()
    target = PointCloud([[0, 0, 1], [0.02, 0.02, 1.02]], "so101_base")
    obstacle = [0.01, 0.01, 1.01]
    scene = PointCloud([*target.points, obstacle, [0.2, 0.2, 1]], "so101_base")
    monkeypatch.setattr(api, "_project_mask", lambda *args, **kwargs: scene)
    result = api._planning_scene(target_point_cloud=target, voxel_size_m=0.001)
    assert any(np.allclose(point, obstacle) for point in result.point_cloud.points)
    assert len(result.point_cloud.points) == 4
    assert result.contact_target is target


def test_contact_target_must_share_the_planning_frame():
    scene = PointCloud([[0, 0, 1]], "base")
    with pytest.raises(ValueError, match="contact_target"):
        PlanningScene(scene, contact_target=PointCloud([[0, 0, 1]], "other"))
    with pytest.raises(ValueError, match="contact_target"):
        PlanningScene(scene, contact_target=True)


@pytest.mark.parametrize("backend", [None, "", " ", 1])
def test_empty_default_grasp_provider_is_rejected(backend):
    with pytest.raises(ValueError, match="default_grasp_backend"):
        api_fixture(default_grasp_backend=backend)


def test_so101_planner_is_a_valid_explicit_motion_strategy():
    strategy = MotionStrategy(ik_solver="so101", trajectory_planner="so101")
    assert strategy.trajectory_planner == "so101"
