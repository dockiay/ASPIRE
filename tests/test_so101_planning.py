"""Planner contract/search tests; synthetic collisions are not harvesting evidence."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from cap_harness.contracts import PlanningScene, PointCloud, Pose, RobotState
from cap_harness.errors import ErrorCode
from cap_harness.so101.planning import SO101TrajectoryPlanner

NAMES = tuple(f"so101_joint_{index}" for index in range(5))


def state(joints=None, opening=1):
    return RobotState(
        joint_positions=np.zeros(5) if joints is None else joints,
        joint_velocities=np.zeros(5),
        end_effector_poses=Pose(
            position=np.zeros(3), quaternion_wxyz=[1, 0, 0, 0], frame="so101_base"
        ),
        gripper_positions=opening,
        joint_names=NAMES,
        base_frame="so101_base",
        embodiment="so101",
    )


def scene(points=None, frame="so101_base"):
    return PlanningScene(
        point_cloud=PointCloud(points=[[10, 10, 10]] if points is None else points, frame=frame)
    )


class SyntheticGeometry:
    """Config-space obstacle for checking search, not an approximation of the robot."""

    def __init__(self, blocked=None):
        self.blocked = blocked or (lambda q, jaw: False)
        self.calls = []
        self.contact_masks = []
        self.robot = SimpleNamespace(
            low=np.full(6, -2.0),
            high=np.full(6, 2.0),
            joints=list(range(5)),
            model=SimpleNamespace(joint=lambda index: SimpleNamespace(name=NAMES[index])),
        )

    def check_path(self, path, points, *, openings, margin_m, finger_contact_mask=None):
        self.calls.append((np.array(path), np.array(openings), np.array(points)))
        self.contact_masks.append(np.array(finger_contact_mask))
        for q, jaw in zip(
            np.linspace(*path, 100),
            np.linspace(*openings, 100),
        ):
            if self.blocked(q, jaw):
                return {"ok": True, "path_clear": False, "reason": "synthetic_obstacle"}
        return {"ok": True, "path_clear": True}


def planner(monkeypatch, blocked=None, **kwargs):
    result = SO101TrajectoryPlanner(**kwargs)
    result._geometry = SyntheticGeometry(blocked)
    monkeypatch.setattr(result, "_without_start_robot", lambda points, q, jaw: (points, 0))
    return result


def test_clear_path_has_conservative_fixed_native_timing(monkeypatch):
    provider = planner(monkeypatch)
    start = state()
    goal = np.array([0.2, -0.1, 0, 0, 0.03])
    result = provider.plan_to_joints(start, goal, scene=scene())
    assert result.ok, result.error
    trajectory = result.trajectory
    assert trajectory.expected_start is start and trajectory.collision_aware
    np.testing.assert_allclose(trajectory.joint_positions[-1], goal)
    increments = np.diff(
        np.vstack([start.joint_positions["primary"], trajectory.joint_positions]), axis=0
    )
    assert np.max(np.abs(increments)) <= 0.5 * trajectory.dt_s + 1e-12
    assert result.diagnostics["direct_path_clear"]
    assert "occluded" in result.diagnostics["scope"]


def test_search_finds_a_real_detour_around_synthetic_wall(monkeypatch):
    obstacle = lambda q, jaw: abs(q[0]) < 0.18 and abs(q[1]) < 0.6
    provider = planner(monkeypatch, obstacle)
    start = state([-1, 0, 0, 0, 0])
    goal = np.array([1, 0, 0, 0, 0])
    result = provider.plan_to_joints(start, goal, scene=scene())
    assert result.ok, result.error
    assert not result.diagnostics["direct_path_clear"]
    assert result.diagnostics["search_iterations"] > 0
    assert np.max(np.abs(result.trajectory.joint_positions[:, 1])) > 0.6
    assert not any(obstacle(q, 1) for q in result.trajectory.joint_positions)
    repeated = provider.plan_to_joints(start, goal, scene=scene())
    np.testing.assert_array_equal(
        repeated.trajectory.joint_positions, result.trajectory.joint_positions
    )


def test_impenetrable_wall_exhausts_budget_without_fallback(monkeypatch):
    provider = planner(monkeypatch, lambda q, jaw: abs(q[0]) < 0.2, max_iterations=12)
    result = provider.plan_to_joints(state([-1, 0, 0, 0, 0]), [1, 0, 0, 0, 0], scene=scene())
    assert not result.ok and result.trajectory is None
    assert result.error.code is ErrorCode.PLANNING_FAILED
    assert not result.diagnostics["direct_path_clear"]
    assert result.diagnostics["search_iterations"] == 12


def test_pending_jaw_sweep_blocks_an_arm_clear_path(monkeypatch):
    provider = planner(monkeypatch, lambda q, jaw: 0.4 < jaw < 0.7)
    result = provider.plan_to_joints(
        state(opening=1), [0.1, 0, 0, 0, 0], gripper_position=0.2, scene=scene()
    )
    assert not result.ok
    assert "pending gripper" in result.error.message
    assert len(provider.geometry.calls) == 1


def test_pending_jaw_sweep_is_scheduled_at_bounded_rate_before_arm(monkeypatch):
    provider = planner(monkeypatch)
    result = provider.plan_to_joints(
        state(opening=1), [0.1, 0, 0, 0, 0], gripper_position=0.75, scene=scene()
    )
    assert result.ok
    trajectory = result.trajectory
    np.testing.assert_allclose(trajectory.joint_positions[:20], 0)
    assert np.min(trajectory.gripper_positions) == 0.75
    assert np.max(np.abs(np.diff(np.r_[1, trajectory.gripper_positions]))) <= 0.0125 + 1e-12
    assert trajectory.joint_positions[20, 0] > 0


@pytest.mark.parametrize(
    "invalid_arguments",
    [
        {"scene": None},
        {"scene": scene(frame="robot_base")},
        {"target_joints": [0, 0, 0, 0, float("nan")]},
        {"target_joints": [0, 0]},
        {"target_joints": [3, 0, 0, 0, 0]},
        {"robot_state": state([3, 0, 0, 0, 0])},
        {"robot_state": replace(state(), joint_names=tuple(reversed(NAMES)))},
        {"arm": "left"},
        {"gripper_position": -1e-16},
        {"gripper_position": float("nan")},
        {"interpolation_dt_s": 0.02},
        {"maximum_trajectory_dt_s": 0.01},
        {"time_dilation_factor": 0},
        {"context": object()},
    ],
)
def test_invalid_requests_fail_without_checking_motion(monkeypatch, invalid_arguments):
    provider = planner(monkeypatch)
    arguments = {"robot_state": state(), "target_joints": np.zeros(5), "scene": scene()}
    arguments.update(invalid_arguments)
    result = provider.plan_to_joints(**arguments)
    assert not result.ok and result.error.code is ErrorCode.INVALID_REQUEST
    assert not provider.geometry.calls


def test_timing_dilation_slows_motion_without_changing_dt(monkeypatch):
    provider = planner(monkeypatch)
    ordinary = provider.plan_to_joints(state(), [0.2, 0, 0, 0, 0], scene=scene())
    slower = provider.plan_to_joints(
        state(), [0.2, 0, 0, 0, 0], scene=scene(), time_dilation_factor=0.5
    )
    assert slower.ok and ordinary.ok
    assert len(slower.trajectory.joint_positions) == 2 * len(ordinary.trajectory.joint_positions)
    assert slower.trajectory.dt_s == ordinary.trajectory.dt_s == 0.05


def test_tiny_dilation_hits_tick_budget_before_large_allocation(monkeypatch):
    provider = planner(monkeypatch)
    result = provider.plan_to_joints(
        state(), [0.2, 0, 0, 0, 0], scene=scene(), time_dilation_factor=1e-12
    )
    assert not result.ok
    assert result.diagnostics["limit_reason"] == "trajectory_tick_budget"


def test_scene_all_removed_is_a_failure_not_obstacle_free_fallback(monkeypatch):
    provider = planner(monkeypatch)
    monkeypatch.setattr(
        provider, "_without_start_robot", lambda points, q, jaw: (np.empty((0, 3)), len(points))
    )
    result = provider.plan_to_joints(state(), np.zeros(5), scene=scene())
    assert not result.ok and "No observed scene" in result.error.message
    assert not provider.geometry.calls


def test_hypothetical_start_masks_current_observed_robot_not_hypothetical_pose(monkeypatch):
    observed = state([-1, 0, 0, 0, 0], opening=0.8)
    provider = planner(monkeypatch, state_provider=lambda: observed)
    mask_calls = []

    def robot_filter(points, q, jaw):
        mask_calls.append((q.copy(), jaw))
        occupied = np.isclose(points[:, 0], q[0])
        return points[~occupied], int(occupied.sum())

    monkeypatch.setattr(provider, "_without_start_robot", robot_filter)
    # A return at hypothetical joint 0 belongs to an obstacle. The actual robot
    # is observed at -1; only its return may be removed by this synthetic mask.
    cloud = scene([[-1, 0, 0], [0, 0, 0], [10, 10, 10]])
    hypothetical = state([0, 0, 0, 0, 0], opening=0.8)
    result = provider.plan_to_joints(hypothetical, [0.2, 0, 0, 0, 0], scene=cloud)
    assert result.ok, result.error
    assert result.trajectory.expected_start is hypothetical
    assert result.diagnostics["robot_mask_state_source"] == "public_observed_state_callback"
    np.testing.assert_array_equal(mask_calls[0][0], observed.joint_positions["primary"])
    assert mask_calls[0][1] == 0.8
    for _, _, points in provider.geometry.calls:
        np.testing.assert_array_equal(points, [[0, 0, 0], [10, 10, 10]])


def test_invalid_observed_robot_callback_fails_without_collision_check(monkeypatch):
    provider = planner(monkeypatch, state_provider=lambda: object())
    result = provider.plan_to_joints(state(), np.zeros(5), scene=scene())
    assert not result.ok and result.error.code is ErrorCode.PROVIDER_ERROR
    assert not provider.geometry.calls


def test_contact_target_stays_in_scene_and_only_exact_sample_neighbors_are_permitted(monkeypatch):
    provider = planner(monkeypatch)
    filtered_inputs = []

    def remove_all_robot_points(points, q, jaw):
        filtered_inputs.append(points.copy())
        return np.empty((0, 3)), len(points)

    monkeypatch.setattr(provider, "_without_start_robot", remove_all_robot_points)
    cloud = PlanningScene(
        point_cloud=PointCloud(points=[[0, 0, 0], [0, 0, 0.002], [10, 10, 10]], frame="so101_base"),
        contact_target=PointCloud(points=[[0, 0, 0]], frame="so101_base"),
    )
    result = provider.plan_to_joints(state(), np.zeros(5), scene=cloud)
    assert result.ok, result.error
    np.testing.assert_array_equal(filtered_inputs[0], [[0, 0, 0.002], [10, 10, 10]])
    assert result.diagnostics["permitted_pad_contact_point_count"] == 1
    for (_, _, points), mask in zip(provider.geometry.calls, provider.geometry.contact_masks):
        np.testing.assert_array_equal(points, [[0, 0, 0]])
        np.testing.assert_array_equal(mask, [True])


@pytest.mark.parametrize("on_pad", [True, False])
def test_native_contact_target_permits_only_pad_and_cannot_hide_finger_body(on_pad):
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    from cap_harness.geometry import matrix_to_pose
    from cap_harness.so101.effector import EffectorGeometry

    geometry = EffectorGeometry()
    robot = geometry.robot
    joints = np.zeros(5)
    position, rotation = robot.forward(joints, 1)
    transform = np.eye(4)
    transform[:3, :3], transform[:3, 3] = rotation, position
    measured = RobotState(
        joint_positions=joints,
        joint_velocities=np.zeros(5),
        end_effector_poses=matrix_to_pose(transform, frame="so101_base"),
        gripper_positions=1,
        joint_names=tuple(robot.model.joint(int(index)).name for index in robot.joints[:5]),
        base_frame="so101_base",
        embodiment="so101",
    )
    geom = geometry.fingers["fixed"]
    if on_pad:
        point_in_geom = geometry.pads["fixed"].mean(0)
    else:
        mesh = int(robot.model.geom_dataid[geom])
        begin, count = robot.model.mesh_vertadr[mesh], robot.model.mesh_vertnum[mesh]
        point_in_geom = robot.model.mesh_vert[begin : begin + count].mean(0)
    point = point_in_geom @ robot.data.geom_xmat[geom].reshape(3, 3).T + robot.data.geom_xpos[geom]
    cloud = PlanningScene(
        point_cloud=PointCloud(points=[point, [10, 10, 10]], frame="so101_base"),
        contact_target=PointCloud(points=[point], frame="so101_base"),
    )
    provider = SO101TrajectoryPlanner()
    provider._geometry = geometry
    result = provider.plan_to_joints(measured, joints, scene=cloud)
    assert result.ok == on_pad, result
    assert result.diagnostics["permitted_pad_contact_point_count"] == 1
    assert result.diagnostics["start_robot_point_count"] == 0
    if not on_pad:
        assert result.diagnostics["last_rejection"]["robot_link"].startswith("so101_")


@pytest.fixture
def native_detour_fixture():
    """Declare a sampled obstacle crossing the real robot's nominal sweep."""
    from itertools import product

    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    from cap_harness.geometry import matrix_to_pose
    from cap_harness.so101.effector import EffectorGeometry

    geometry = EffectorGeometry()
    robot = geometry.robot
    robot.forward(np.zeros(5), 1)
    geom = geometry.fingers["fixed"]
    mesh = int(robot.model.geom_dataid[geom])
    begin, count = robot.model.mesh_vertadr[mesh], robot.model.mesh_vertnum[mesh]
    center = (
        robot.model.mesh_vert[begin : begin + count].mean(0)
        @ robot.data.geom_xmat[geom].reshape(3, 3).T
        + robot.data.geom_xpos[geom]
    )
    # Engineering fixture: a 16 mm cube sampled every 4 mm. It is explicitly
    # supplied as public points, not read from an environment or a fruit model.
    points = center + np.array(list(product([-0.008, -0.004, 0, 0.004, 0.008], repeat=3)))
    start = np.array([-0.6, 0, 0, 0, 0])
    position, rotation = robot.forward(start, 1)
    transform = np.eye(4)
    transform[:3, :3], transform[:3, 3] = rotation, position
    measured = RobotState(
        joint_positions=start,
        joint_velocities=np.zeros(5),
        end_effector_poses=matrix_to_pose(transform, frame="so101_base"),
        gripper_positions=1,
        joint_names=tuple(robot.model.joint(int(index)).name for index in robot.joints[:5]),
        base_frame="so101_base",
        embodiment="so101",
    )
    cloud = PlanningScene(
        point_cloud=PointCloud(points=points, frame="so101_base"), voxel_size_m=0.004
    )
    provider = SO101TrajectoryPlanner()
    provider._geometry = geometry
    return geometry, measured, cloud, provider


def test_native_rrt_finds_collision_checked_detour_with_real_robot_mesh(native_detour_fixture):
    geometry, measured, cloud, provider = native_detour_fixture
    start = measured.joint_positions["primary"]
    goal = np.array([0.6, 0, 0, 0, 0])
    points = cloud.point_cloud.points
    # The fixture intersects the nominal sweep even without a clearance margin.
    assert not geometry.check_path([start, goal], points, margin_m=0)["path_clear"]
    result = provider.plan_to_joints(measured, goal, scene=cloud)
    assert result.ok, result
    assert not result.diagnostics["direct_path_clear"]
    assert result.diagnostics["search_iterations"] > 0
    assert result.diagnostics["start_robot_point_count"] == 0
    assert result.diagnostics["obstacle_point_count"] == len(points)
    trajectory = np.vstack([start, result.trajectory.joint_positions])
    np.testing.assert_allclose(trajectory[-1], goal)
    assert np.max(np.abs(np.diff(trajectory, axis=0))) <= 0.5 * result.trajectory.dt_s + 1e-12
    assert np.max(np.abs(trajectory[:, 1:])) > 0.05
    # Independently resample the returned, timed path against the complete same
    # scene using the unchanged default clearance and robot/work-plane checks.
    for offset in range(0, len(trajectory) - 1, 127):
        verification = geometry.check_path(trajectory[offset : offset + 128], points, opening=1)
        assert verification["path_clear"], verification


def test_native_planner_rejects_goal_inside_obstacle_without_clearing_scene(native_detour_fixture):
    _, measured, cloud, provider = native_detour_fixture
    result = provider.plan_to_joints(measured, np.zeros(5), scene=cloud)
    assert not result.ok and result.trajectory is None
    assert result.error.code is ErrorCode.PLANNING_FAILED
    assert result.error.message == "Target configuration is obstructed"
    assert result.diagnostics["start_robot_point_count"] == 0
    assert result.diagnostics["obstacle_point_count"] == len(cloud.point_cloud.points)
    assert result.diagnostics["last_rejection"]["robot_link"].startswith("so101_")


@pytest.mark.parametrize("task", ["so101_control"])
def test_native_full_camera_scene_plans_without_treating_robot_depth_as_obstacles(task):
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    from cap_harness.so101.adapter import SO101Adapter
    from cap_harness.so101.integration import make_api

    adapter = SO101Adapter(camera_width=1280, camera_height=960, horizon=10)
    try:
        adapter.reset(task, 0)
        api = make_api(adapter)
        current = api.get_robot_state()
        goal = current.joint_positions["primary"] + [0.15, 0, 0, 0, 0]
        result = api.plan_motion(goal)
        assert result.ok, result
        assert result.trajectory.collision_aware
        assert result.diagnostics["margin_m"] == 0.003
        assert result.diagnostics["input_point_count"] > 1000
        assert result.diagnostics["obstacle_point_count"] > 1000
        assert result.diagnostics["start_robot_point_count"] > 0
        assert adapter.current_time_s == current.timestamp_s  # planning does not move
    finally:
        adapter.close()


@pytest.mark.parametrize("collidable", [True, False])
def test_robot_filter_does_not_remove_nearby_points_within_clearance(monkeypatch, collidable):
    from itertools import product

    provider = SO101TrajectoryPlanner()
    vertices = np.array(list(product([-0.01, 0.01], repeat=3)))
    model = SimpleNamespace(
        ngeom=1,
        geom_bodyid=[0],
        body=lambda index: SimpleNamespace(name="so101_link"),
        geom_contype=[int(collidable)],
        geom_conaffinity=[int(collidable)],
        geom_dataid=[0],
        mesh_vertadr=[0],
        mesh_vertnum=[8],
        mesh_vert=vertices,
    )
    provider._geometry = SimpleNamespace(
        hulls={},
        robot=SimpleNamespace(
            model=model,
            data=SimpleNamespace(geom_xpos=np.zeros((1, 3)), geom_xmat=np.eye(3).reshape(1, 9)),
            forward=lambda q, jaw: None,
        ),
    )
    cloud = np.array(
        [[0, 0, 0], [0.01, 0, 0], [0.010002, 0, 0], [0.0101, 0, 0], [0.011, 0, 0], [0.1, 0, 0]]
    )
    remaining, removed = provider._without_start_robot(cloud, np.zeros(5), 1)
    assert removed == 3  # on/inside plus 2 micrometre reconstruction residual
    np.testing.assert_array_equal(remaining, cloud[3:])


def test_geometry_failure_is_typed_and_does_not_return_a_path(monkeypatch):
    provider = planner(monkeypatch)

    def fail(*args, **kwargs):
        raise RuntimeError("fixture collision service error")

    monkeypatch.setattr(provider.geometry, "check_path", fail)
    result = provider.plan_to_joints(state(), np.zeros(5), scene=scene())
    assert not result.ok and result.error.code is ErrorCode.PROVIDER_ERROR


def test_oversized_contact_target_is_rejected_before_geometry(monkeypatch):
    provider = planner(monkeypatch)
    cloud = PlanningScene(
        point_cloud=PointCloud([[10, 10, 10]], "so101_base"),
        contact_target=PointCloud(np.zeros((32769, 3)), "so101_base"),
    )
    result = provider.plan_to_joints(state(), np.zeros(5), scene=cloud)
    assert not result.ok and result.error.code is ErrorCode.INVALID_REQUEST
    assert not provider.geometry.calls


@pytest.mark.parametrize("speed", [True, np.array([0.5]), 0, float("nan"), 1.1])
def test_invalid_planner_rate_is_rejected(speed):
    with pytest.raises(ValueError):
        SO101TrajectoryPlanner(joint_speed_rad_s=speed)
