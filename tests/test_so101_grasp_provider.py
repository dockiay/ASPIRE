"""Robot-only grasp proposals; fixtures never claim a successful physical grasp."""

from dataclasses import replace
from itertools import product

import numpy as np
import pytest

from cap_harness.contracts import PointCloud, RobotState
from cap_harness.errors import ErrorCode
from cap_harness.so101.grasp_provider import SO101GraspProvider
from cap_harness.so101.planning import filter_observed_robot_points


@pytest.fixture(scope="module")
def fixture():
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    state = None
    provider = SO101GraspProvider(lambda: state)
    joints = (provider.ik.robot.low[:5] + provider.ik.robot.high[:5]) / 2
    position, axes = provider.ik.robot.forward(joints, 0.3)
    state = RobotState(
        joint_positions=joints,
        joint_velocities=np.zeros(5),
        end_effector_poses=provider._pose(position, axes, "so101_base"),
        gripper_positions=0.3,
        joint_names=tuple(
            provider.ik.robot.model.joint(int(index)).name for index in provider.ik.robot.joints[:5]
        ),
        base_frame="so101_base",
        embodiment="so101",
    )
    shape = provider.effector.describe(joints, 0.3)
    center = position + axes @ np.asarray(shape["grasp_center_in_tcp_m"])
    offsets = np.array(list(product([-0.003, 0.003], [-0.003, 0.003], [-0.01, 0.01])))
    cloud = PointCloud(center + offsets @ axes.T, "so101_base")
    return provider, state, cloud


def test_reachable_tcp_uses_angular_jaw_offset_and_public_state_is_unchanged(fixture):
    provider, state, cloud = fixture
    initial_joints = state.joint_positions["primary"].copy()
    result = provider.generate_grasps(cloud, scene_point_cloud=cloud, max_candidates=1)
    assert result.ok, result
    candidate = result.grasps[0]
    metadata = candidate.metadata
    assert candidate.frame == "so101_base"
    assert not metadata["grasp_verified"]
    assert metadata["approach_axis"] == 0
    assert metadata["approach_check"]["path_clear"]
    assert result.diagnostics["ik_calls"] <= provider.max_ik_calls
    assert result.diagnostics["checked_obstacle_points"] == 0
    assert 0 <= metadata["gripper_position"] <= 1
    assert candidate.width_m >= metadata["observed_object_width_m"] + 0.002
    assert metadata["point_error_m"] < 0.0005
    position, axes = provider.ik.robot.forward(
        metadata["joint_target"], metadata["gripper_position"]
    )
    np.testing.assert_allclose(candidate.pose.position, position, atol=1e-9)
    np.testing.assert_allclose(candidate.pose.as_matrix()[:3, :3], axes, atol=1e-9)
    center = position + axes @ np.asarray(metadata["grasp_center_in_tcp_m"])
    np.testing.assert_allclose(center, metadata["observed_center_m"], atol=0.0005)
    assert np.linalg.norm(candidate.pose.position - center) > 0.005
    # Independent full-pose IK verifies that a returned grasp does not hide an
    # orientation the five-axis robot cannot actually achieve.
    opening_state = replace(state, gripper_positions={"primary": metadata["gripper_position"]})
    solved = provider.ik.solve_ik(candidate.pose, opening_state)
    assert solved.ok, solved
    np.testing.assert_array_equal(initial_joints, state.joint_positions["primary"])


def test_deterministic_bounded_proposals(fixture):
    provider, _, cloud = fixture
    first = provider.generate_grasps(cloud, max_candidates=1)
    second = provider.generate_grasps(cloud, max_candidates=1)
    assert first.ok and second.ok
    np.testing.assert_array_equal(first.grasps[0].transform, second.grasps[0].transform)
    assert first.diagnostics == second.diagnostics
    assert len(first.grasps) == 1


@pytest.mark.parametrize("full_scene", [False, True])
def test_mask_background_outliers_do_not_move_target_and_remain_obstacles(
    fixture, monkeypatch, full_scene
):
    provider, _, cloud = fixture
    far_point = np.array([10.0, -30.0, -12.0])
    contaminated = PointCloud(np.vstack([cloud.points, far_point]), cloud.frame)
    seen = []
    original = provider.effector.check_path

    def check(waypoints, points, **kwargs):
        background = np.flatnonzero(np.linalg.norm(points - far_point, axis=1) < 1e-9)
        assert len(background) == 1
        assert not kwargs["finger_contact_mask"][background[0]]
        seen.append(True)
        return original(waypoints, points, **kwargs)

    monkeypatch.setattr(provider.effector, "check_path", check)
    scene = None
    if full_scene:
        other = np.column_stack([np.linspace(4, 5, 5000), np.full((5000, 2), 5.0)])
        scene = PointCloud(np.vstack([contaminated.points, other]), cloud.frame)
    result = provider.generate_grasps(contaminated, scene_point_cloud=scene, max_candidates=1)
    assert result.ok and seen, result
    component = result.diagnostics["target_component"]
    assert component["unambiguous"]
    assert component["selected_points"] == len(cloud.points)
    assert component["excluded_points"] == 1
    np.testing.assert_allclose(
        result.grasps[0].metadata["observed_center_m"], cloud.points.mean(0), atol=0.001
    )
    assert result.diagnostics["checked_obstacle_points"] == (4096 if full_scene else 1)
    assert result.diagnostics["excluded_mask_points_preserved_as_obstacles"] == 1


def test_excluded_mask_sample_still_blocks_a_grasp_when_scene_exceeds_sampling_budget(fixture):
    provider, state, cloud = fixture
    robot = provider.effector.robot
    robot.forward(state.joint_positions["primary"], state.gripper_positions["primary"])
    for geom in range(robot.model.ngeom):
        mesh = int(robot.model.geom_dataid[geom])
        if (
            robot.model.body(int(robot.model.geom_bodyid[geom])).name == "so101_shoulder"
            and mesh >= 0
            and robot.model.geom_contype[geom]
        ):
            start, count = int(robot.model.mesh_vertadr[mesh]), int(robot.model.mesh_vertnum[mesh])
            local = robot.model.mesh_vert[start : start + count].mean(0)
            obstacle = (
                local @ robot.data.geom_xmat[geom].reshape(3, 3).T + robot.data.geom_xpos[geom]
            )
            break
    else:
        pytest.fail("Expected a collision mesh on the shoulder")
    contaminated = PointCloud(np.vstack([cloud.points, obstacle]), cloud.frame)
    other = np.column_stack([np.linspace(4, 5, 5000), np.full((5000, 2), 5.0)])
    scene = PointCloud(np.vstack([contaminated.points, other]), cloud.frame)
    result = provider.generate_grasps(contaminated, scene_point_cloud=scene)
    assert not result.ok and result.error.code == ErrorCode.NO_GRASP
    assert result.diagnostics["target_component"]["excluded_points"] == 1
    assert result.diagnostics["excluded_mask_points_preserved_as_obstacles"] == 1
    assert result.diagnostics["rejections"]["observed_approach_collision"] > 0


def test_ambiguous_disconnected_objects_are_not_silently_selected(fixture):
    provider, _, cloud = fixture
    ambiguous = PointCloud(np.vstack([cloud.points, cloud.points + [0, 0.2, 0]]), cloud.frame)
    result = provider.generate_grasps(ambiguous)
    assert not result.ok and result.error.code == ErrorCode.NO_GRASP
    assert not result.diagnostics["target_component"]["unambiguous"]
    assert result.diagnostics["ik_calls"] == 0


def test_target_cloud_budget_rejects_before_graph_or_svd(fixture, monkeypatch):
    provider, _, _ = fixture
    cloud = PointCloud(np.zeros((provider.max_target_points + 1, 3)), "so101_base")

    def forbidden(*args, **kwargs):
        pytest.fail("Oversized input reached expensive decomposition")

    monkeypatch.setattr(provider, "_target_component", forbidden)
    monkeypatch.setattr(np.linalg, "matrix_rank", forbidden)
    result = provider.generate_grasps(cloud)
    assert not result.ok and result.error.code == ErrorCode.INVALID_REQUEST
    assert result.diagnostics["ik_calls"] == 0


@pytest.mark.parametrize("count", [0, -1, True, 1.5, 33])
def test_invalid_candidate_budget_is_a_typed_failure(fixture, count):
    provider, _, cloud = fixture
    result = provider.generate_grasps(cloud, max_candidates=count)
    assert not result.ok and result.error.code == ErrorCode.INVALID_REQUEST
    assert result.diagnostics["ik_calls"] == 0


def test_invalid_frames_and_insufficient_clouds_never_run_ik(fixture):
    provider, _, cloud = fixture
    for result in (
        provider.generate_grasps(np.empty((0, 3))),
        provider.generate_grasps(replace(cloud, frame="world")),
        provider.generate_grasps(cloud, scene_point_cloud=replace(cloud, frame="camera")),
        provider.generate_grasps(PointCloud([[0, 0, 0]], "so101_base")),
        provider.generate_grasps(
            PointCloud(np.column_stack([np.arange(8), np.zeros((8, 2))]), "so101_base")
        ),
    ):
        assert not result.ok
        assert result.diagnostics["ik_calls"] == 0


def test_unreachable_cloud_and_unfittable_object_return_no_grasp(fixture):
    provider, _, cloud = fixture
    for points in (
        cloud.points + [2, 0, 0],
        cloud.points.mean(0) + np.array(list(product([-0.15, 0.15], repeat=3))),
    ):
        result = provider.generate_grasps(PointCloud(points, "so101_base"))
        assert not result.ok and result.error.code == ErrorCode.NO_GRASP
        assert not result.grasps
        assert result.diagnostics["ik_calls"] <= provider.max_ik_calls


def test_public_scene_obstacle_rejects_approaches(fixture, monkeypatch):
    provider, state, cloud = fixture
    candidate = provider.generate_grasps(cloud, max_candidates=1).grasps[0]
    # Isolate one feasible proposal so a different approach cannot avoid the
    # obstacle intentionally placed in this approach's future collision mesh.
    axes = state.end_effector_poses["primary"].as_matrix()[:3, :3]
    monkeypatch.setattr(provider, "_directions", lambda center, rotation: [axes[:, 0]])
    robot = provider.effector.robot
    robot.forward(candidate.metadata["joint_target"], candidate.metadata["gripper_position"])
    possible = []
    # Future mesh interiors are occupied by this proposal, not necessarily by
    # the currently observed robot. The fixture supplies one as an obstacle.
    for geom in range(robot.model.ngeom):
        body = robot.model.body(int(robot.model.geom_bodyid[geom]))
        mesh = int(robot.model.geom_dataid[geom])
        if (
            body.name.startswith("so101_")
            and mesh >= 0
            and (robot.model.geom_contype[geom] or robot.model.geom_conaffinity[geom])
        ):
            start = int(robot.model.mesh_vertadr[mesh])
            count = int(robot.model.mesh_vertnum[mesh])
            vertices = robot.model.mesh_vert[start : start + count]
            # Points just inside several future hull surfaces, rather than
            # centers which remain inside both old and new overlapping meshes.
            local = vertices[np.linspace(0, count - 1, min(16, count), dtype=int)]
            local = 0.9 * local + 0.1 * vertices.mean(0)
            obstacles = (
                local @ robot.data.geom_xmat[geom].reshape(3, 3).T + robot.data.geom_xpos[geom]
            )
            possible.extend(obstacles)
    obstacles, _ = filter_observed_robot_points(provider.effector, state, np.asarray(possible))
    assert len(obstacles), "Fixture must include future geometry outside the current robot"
    scene = PointCloud(np.vstack([cloud.points, obstacles]), cloud.frame)
    result = provider.generate_grasps(cloud, scene_point_cloud=scene)
    assert not result.ok and result.error.code == ErrorCode.NO_GRASP
    assert result.diagnostics["checked_obstacle_points"] == len(obstacles)
    assert result.diagnostics["rejections"]["observed_approach_collision"] > 0
    attempt = result.diagnostics["attempts"][0]
    assert attempt["status"] == "observed_approach_collision"
    assert attempt["blocking_sample_kind"] == "scene"
    assert attempt["approach_check"]["reason"] in ("observed_obstacle", "observed_clearance")


def test_public_robot_surface_returns_are_filtered_without_removing_target(fixture):
    provider, state, cloud = fixture
    robot = provider.effector.robot
    robot.forward(state.joint_positions["primary"], state.gripper_positions["primary"])
    returned = []
    for geom in range(robot.model.ngeom):
        mesh = int(robot.model.geom_dataid[geom])
        if mesh < 0 or not (robot.model.geom_contype[geom] or robot.model.geom_conaffinity[geom]):
            continue
        start = int(robot.model.mesh_vertadr[mesh])
        local = robot.model.mesh_vert[start]
        returned.append(
            local @ robot.data.geom_xmat[geom].reshape(3, 3).T + robot.data.geom_xpos[geom]
        )
    result = provider.generate_grasps(
        cloud,
        scene_point_cloud=PointCloud(np.vstack([cloud.points, returned]), cloud.frame),
        max_candidates=1,
    )
    assert result.ok, result
    assert result.diagnostics["checked_target_points"] == len(cloud.points)
    assert result.diagnostics["removed_robot_points"] == len(returned)
    assert result.diagnostics["checked_obstacle_points"] == 0


def test_model_state_disagreement_is_rejected_before_search(fixture):
    provider, state, cloud = fixture
    pose = state.end_effector_poses["primary"]
    stale = replace(
        state,
        end_effector_poses={"primary": replace(pose, position=pose.position + [0, 0, 0.01])},
    )
    invalid_provider = SO101GraspProvider(
        lambda: stale, ik_provider=provider.ik, effector_geometry=provider.effector
    )
    result = invalid_provider.generate_grasps(cloud)
    assert not result.ok and result.error.code == ErrorCode.PROVIDER_ERROR
    assert result.diagnostics["ik_calls"] == 0


def test_reordered_state_and_oversized_scene_fail_before_ik(fixture, monkeypatch):
    provider, state, cloud = fixture
    reordered = replace(state, joint_names=tuple(reversed(state.joint_names["primary"])))
    invalid = SO101GraspProvider(
        lambda: reordered, ik_provider=provider.ik, effector_geometry=provider.effector
    )
    result = invalid.generate_grasps(cloud)
    assert not result.ok and result.error.code is ErrorCode.INVALID_REQUEST
    assert result.diagnostics["ik_calls"] == 0
    monkeypatch.setattr(provider, "max_scene_points", 4)
    result = provider.generate_grasps(cloud, scene_point_cloud=cloud)
    assert not result.ok and result.error.code is ErrorCode.INVALID_REQUEST
    assert result.diagnostics["ik_calls"] == 0


def test_shared_rgbd_to_grasp_pipeline_uses_only_public_camera_and_state(fixture):
    from types import SimpleNamespace

    from cap_harness.contracts import CameraObservation, Observation
    from cap_harness.registry import ToolRegistry
    from cap_harness.runtime import ProgramExecutor
    from cap_harness.so101.integration import make_api
    from cap_harness.so101.segmentation import ColorSegmentationProvider

    pytest.importorskip("cv2")
    provider, state, cloud = fixture
    axes = state.end_effector_poses["primary"].as_matrix()[:3, :3]
    center = cloud.points.mean(0)
    rgb = np.full((16, 16, 3), 120, dtype=np.uint8)
    rgb[4:12, 4:12] = [180, 20, 25]
    depth = np.zeros((16, 16))
    depth[4:12, 4:12] = 0.2
    camera = CameraObservation(
        rgb=rgb,
        depth_m=depth,
        intrinsics=[[200, 0, 7.5], [0, 200, 7.5], [0, 0, 1]],
        frame="camera/agentview",
        camera_pose=provider._pose(center - 0.2 * axes[:, 2], axes, "so101_base"),
    )
    observation = Observation(cameras={"agentview": camera}, robot_state=state)
    # Engineering image fixture around a model-derived reachable point; no
    # environment, task object, evaluator or motion callback is supplied.
    adapter = SimpleNamespace(
        embodiment="so101",
        control_period_s=0.05,
        get_robot_state=lambda: state,
        get_observation=lambda *args: observation,
    )
    api = make_api(adapter, segmentation_provider=ColorSegmentationProvider())
    registry = api.register_tools(ToolRegistry())
    execution = ProgramExecutor(registry).execute_program("""
masks = segment_text('agentview', 'red')
assert masks.ok and len(masks.segmentations) == 1
proposals = generate_grasps('agentview', masks.segmentations[0], max_candidates=1)
assert proposals.ok, str(proposals.error)
candidate = select_grasp(proposals, strategy='highest_score')
assert candidate.metadata['grasp_verified'] == False
assert candidate.metadata['approach_check']['path_clear']
result = {'frame': candidate.frame, 'backend': candidate.metadata['provider']}
""")
    assert execution.ok, execution.error
    assert execution.result["backend"] == "so101-geometric"
    assert execution.result["frame"] == "so101_base"
    np.testing.assert_array_equal(
        state.joint_positions["primary"], adapter.get_robot_state().joint_positions["primary"]
    )
