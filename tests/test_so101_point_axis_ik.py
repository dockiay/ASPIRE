"""Robot-only five-constraint IK and its restricted public extension."""

from dataclasses import replace

import numpy as np
import pytest

from cap_harness.contracts import RobotState
from cap_harness.errors import ErrorCode
from cap_harness.geometry import matrix_to_pose
from cap_harness.so101.providers import SO101IKProvider


@pytest.fixture
def model_state():
    pytest.importorskip("mujoco")
    provider = SO101IKProvider()
    joints = (provider.robot.low[:5] + provider.robot.high[:5]) / 2
    position, axes = provider.robot.forward(joints, 0.42)
    transform = np.eye(4)
    transform[:3, :3], transform[:3, 3] = axes, position
    state = RobotState(
        joint_positions={"primary": joints},
        joint_velocities={"primary": np.zeros(5)},
        end_effector_poses={"primary": matrix_to_pose(transform, frame="so101_base")},
        gripper_positions={"primary": 0.42},
        joint_names=tuple(
            provider.robot.model.joint(int(index)).name for index in provider.robot.joints[:5]
        ),
        base_frame="so101_base",
        embodiment="so101",
    )
    return provider, state


@pytest.mark.parametrize("opening", [0.15, 0.8])
@pytest.mark.parametrize("axis", [[1, 0, 0], [0.3, -0.4, 0.5]])
def test_point_and_direction_reach_actual_forward_targets(model_state, opening, axis):
    provider, state = model_state
    state = replace(state, gripper_positions={"primary": opening})
    point = np.array([0.015, -0.012, 0.025])
    axis = np.asarray(axis) / np.linalg.norm(axis)
    desired = state.joint_positions["primary"] + [0.12, -0.08, 0.1, 0.06, -0.15]
    position, axes = provider.robot.forward(desired, opening)
    target, direction = position + axes @ point, axes @ axis
    answer = provider.solve_point_axis_ik(point, target, axis, direction * 3, state)
    assert answer.ok, answer
    actual, actual_axes = provider.robot.forward(answer.joint_positions, opening)
    assert np.linalg.norm(actual + actual_axes @ point - target) <= 0.0005
    assert (actual_axes @ axis) @ direction >= np.cos(np.deg2rad(1))
    assert np.all(answer.joint_positions >= provider.robot.low[:5])
    assert np.all(answer.joint_positions <= provider.robot.high[:5])
    assert answer.diagnostics["collision_aware"] is False
    np.testing.assert_array_equal(
        state.joint_positions["primary"], (provider.robot.low[:5] + provider.robot.high[:5]) / 2
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"point_in_tool_m": [1, 2]},
        {"target_point_m": [0, 0, float("nan")]},
        {"axis_in_tool": [0, 0, 0]},
        {"target_axis": [0, float("inf"), 0]},
        {"target_axis": [0, 0, 0]},
        {"frame": "world"},
        {"arm": "secondary"},
        {"seed_joints": [0, 0]},
        {"seed_joints": [0, 0, 0, 0, float("nan")]},
    ],
)
def test_invalid_constraints_return_typed_failure(model_state, kwargs):
    provider, state = model_state
    inputs = dict(
        point_in_tool_m=[0, 0, 0],
        target_point_m=[0.2, 0, 0.1],
        axis_in_tool=[1, 0, 0],
        target_axis=[1, 0, 0],
    )
    inputs.update(kwargs)
    result = provider.solve_point_axis_ik(**inputs, state=state)
    assert not result.ok and result.error.code == ErrorCode.INVALID_REQUEST


def test_unreachable_constraints_are_not_relaxed(model_state):
    provider, state = model_state
    result = provider.solve_point_axis_ik([0, 0, 0], [5, 5, 5], [1, 0, 0], [0, 1, 0], state)
    assert not result.ok and result.error.code == ErrorCode.IK_FAILED
    assert result.joint_positions is None
    assert result.diagnostics["point_error_m"] > 0.0005


def test_both_ik_entry_points_reject_reordered_state(model_state):
    provider, state = model_state
    state = replace(state, joint_names=tuple(reversed(state.joint_names["primary"])))
    pose_result = provider.solve_ik(state.end_effector_poses["primary"], state)
    axis_result = provider.solve_point_axis_ik(
        [0, 0, 0], [0.2, 0, 0.1], [1, 0, 0], [1, 0, 0], state
    )
    for result in (pose_result, axis_result):
        assert not result.ok and result.error.code is ErrorCode.INVALID_REQUEST
        assert result.joint_positions is None


def test_pose_ik_rejects_untyped_inputs(model_state):
    provider, state = model_state
    assert provider.solve_ik(object(), state).error.code is ErrorCode.INVALID_REQUEST
    assert (
        provider.solve_ik(state.end_effector_poses["primary"], object()).error.code
        is ErrorCode.INVALID_REQUEST
    )


def test_public_program_can_solve_constraints_without_moving(tmp_path):
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    from cap_harness.run import run_program

    program = tmp_path / "point-axis.py"
    program.write_text(
        "state = get_robot_state()\n"
        "pose = state.end_effector_poses['primary']\n"
        "transform = pose.as_matrix()\n"
        "answer = so101.solve_point_axis_ik([0, 0, 0], pose.position, [1, 0, 0], transform[:3, 0], seed_joints=state.joint_positions['primary'])\n"
        "assert answer.ok, str(answer.error)\n"
        "assert answer.diagnostics['collision_aware'] == False\n"
        "after = get_robot_state()\n"
        "assert after.timestamp_s == state.timestamp_s\n"
        "result = {'point_error_m': answer.diagnostics['point_error_m']}\n"
    )
    outcome = run_program(
        benchmark="so101",
        suite="so101_control",
        task_id=0,
        seed=0,
        program_path=program,
        output_root=tmp_path / "run",
        max_steps=10,
        camera_width=64,
        camera_height=64,
        capture_videos=False,
    )
    assert outcome.program_ok, outcome
