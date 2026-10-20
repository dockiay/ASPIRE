"""SO-101 foundations and regressions for existing robot dimensions."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from cap_harness.api import CapApi
from cap_harness.contracts import (
    ArmCommand,
    CameraObservation,
    Observation,
    Pose,
    RobotAction,
    RobotPlanningContext,
    RobotState,
    StepResult,
    Trajectory,
)
from cap_harness.so101.codec import SO101ActionCodec


def _state(embodiment: str = "so101", dimension: int = 5) -> RobotState:
    return RobotState(
        joint_positions=np.zeros(dimension),
        joint_velocities=np.zeros(dimension),
        end_effector_poses=Pose(np.zeros(3), np.array([1.0, 0.0, 0.0, 0.0]), "base"),
        gripper_positions=0.5,
        base_frame="base",
        embodiment=embodiment,
    )


@pytest.mark.parametrize(
    ("embodiment", "dimension"), [("so101", 5), ("yam_real", 6), ("robosuite", 7)]
)
def test_contracts_preserve_each_robots_joint_count(embodiment: str, dimension: int) -> None:
    state = _state(embodiment, dimension)
    command = ArmCommand("joint_position", np.zeros(dimension), embodiment=embodiment)
    action = RobotAction({"primary": command})
    trajectory = Trajectory(
        np.zeros((2, dimension)),
        0.05,
        state.joint_names["primary"],
        "test",
        False,
        state,
        embodiment=embodiment,
    )
    context = RobotPlanningContext(
        embodiment, "test-model", state.joint_names, {"primary": np.eye(4)}, {"primary": "tcp"}
    )

    assert action.embodiment == embodiment
    assert trajectory.waypoints.shape == (2, dimension)
    assert len(context.joint_names["primary"]) == dimension
    for wrong_dimension in {5, 6, 7} - {dimension}:
        with pytest.raises(ValueError, match="shape"):
            ArmCommand("joint_position", np.zeros(wrong_dimension), embodiment=embodiment)
        with pytest.raises(ValueError, match="shape"):
            _state(embodiment, wrong_dimension)


@pytest.mark.parametrize(
    ("embodiment", "dimension"), [("so101", 5), ("yam_real", 6), ("robosuite", 7)]
)
@pytest.mark.parametrize("mapped", [False, True])
def test_explicit_home_rejects_another_robots_dimensions(
    embodiment: str, dimension: int, mapped: bool
) -> None:
    adapter = SimpleNamespace(embodiment=embodiment)
    for wrong_dimension in {5, 6, 7} - {dimension}:
        target = np.zeros(wrong_dimension)
        home = {"primary": target} if mapped else target
        with pytest.raises(ValueError, match=f"finite {dimension}-joint"):
            CapApi(adapter, home_joint_positions=home)


@pytest.mark.parametrize("bad_value", [np.nan, np.inf, -np.inf])
def test_explicit_home_rejects_nonfinite_joints(bad_value: float) -> None:
    with pytest.raises(ValueError, match="finite 5-joint"):
        CapApi(
            SimpleNamespace(embodiment="so101"),
            home_joint_positions=np.array([bad_value, 0, 0, 0, 0]),
        )


@pytest.mark.parametrize(
    ("embodiment", "dimension"), [("so101", 5), ("yam_real", 6), ("robosuite", 7)]
)
@pytest.mark.parametrize("mapped", [False, True])
def test_shared_motion_and_home_keep_robot_dimension_and_gripper(
    embodiment: str, dimension: int, mapped: bool
) -> None:
    state = _state(embodiment, dimension)
    camera = CameraObservation(
        rgb=np.zeros((1, 1, 3), dtype=np.uint8),
        depth_m=np.ones((1, 1)),
        intrinsics=np.eye(3),
        frame="camera",
        camera_pose=state.end_effector_poses["primary"],
    )
    actions = []

    def observation() -> Observation:
        return Observation(cameras={"agentview": camera}, robot_state=state)

    def step(action: RobotAction) -> StepResult:
        nonlocal state
        actions.append(action)
        command = action.arms["primary"]
        state = replace(
            state,
            joint_positions={"primary": command.target},
            gripper_positions={"primary": command.gripper_position},
        )
        return StepResult(ok=True, observation=observation())

    adapter = SimpleNamespace(
        embodiment=embodiment,
        control_period_s=0.05,
        get_robot_state=lambda: state,
        get_observation=observation,
        step=step,
    )
    home = np.full(dimension, 0.1)
    explicit_home = {"primary": home} if mapped else home
    api = CapApi(adapter, home_joint_positions=explicit_home)
    home[:] = 0.9

    assert api.set_gripper(0.25).ok
    assert api.move_to_joints(np.full(dimension, 0.2)).ok
    assert api.go_home().ok
    np.testing.assert_allclose(state.joint_positions["primary"], 0.1)
    assert state.gripper_positions["primary"] == 0.25
    assert actions
    assert all(action.embodiment == embodiment for action in actions)
    assert all(action.arms["primary"].target.shape == (dimension,) for action in actions)


@pytest.fixture
def codec() -> SO101ActionCodec:
    return SO101ActionCodec((np.full(6, -1.0), np.array([1, 1, 1, 1, 1, 2.0])))


@pytest.mark.parametrize(("opening", "angle"), [(0.0, -1.0), (0.25, -0.25), (1.0, 2.0)])
def test_codec_maps_gripper_independently_of_five_arm_joints(
    codec: SO101ActionCodec, opening: float, angle: float
) -> None:
    action = RobotAction(
        {"primary": ArmCommand("joint_position", np.full(5, 0.2), opening, "so101")}
    )
    native = codec.encode(action, _state(), gripper_targets={"primary": 0.8})

    assert native.shape == (6,)
    np.testing.assert_allclose(native[:5], 0.2)
    assert native[5] == pytest.approx(angle)


def test_codec_uses_cached_gripper_when_command_omits_it(codec: SO101ActionCodec) -> None:
    action = RobotAction({"primary": ArmCommand("joint_position", np.zeros(5), embodiment="so101")})

    assert codec.encode(action, _state())[5] == pytest.approx(0.5)
    assert codec.encode(action, _state(), gripper_targets={"primary": 0.25})[5] == pytest.approx(
        -0.25
    )


@pytest.mark.parametrize("target", [-1.01, 1.01])
def test_codec_rejects_arm_targets_outside_actuator_limits(
    codec: SO101ActionCodec, target: float
) -> None:
    action = RobotAction(
        {"primary": ArmCommand("joint_position", np.full(5, target), embodiment="so101")}
    )
    with pytest.raises(ValueError, match="actuator limits"):
        codec.encode(action, _state())


@pytest.mark.parametrize("opening", [-0.01, 1.01, np.nan, np.inf])
def test_codec_rejects_invalid_cached_gripper(codec: SO101ActionCodec, opening: float) -> None:
    action = RobotAction({"primary": ArmCommand("joint_position", np.zeros(5), embodiment="so101")})
    with pytest.raises(ValueError, match="opening"):
        codec.encode(action, _state(), gripper_targets={"primary": opening})


def test_codec_rejects_another_robot_and_secondary_arm(codec: SO101ActionCodec) -> None:
    other_action = RobotAction({"primary": ArmCommand("joint_position", np.zeros(7))})
    action = RobotAction({"primary": ArmCommand("joint_position", np.zeros(5), embodiment="so101")})
    with pytest.raises(ValueError, match="SO-101 contracts"):
        codec.encode(other_action, _state())
    with pytest.raises(ValueError, match="SO-101 contracts"):
        codec.encode(action, _state("robosuite", 7))
    with pytest.raises(ValueError, match="only the primary arm"):
        codec.encode(RobotAction({"secondary": action.arms["primary"]}), _state())
    secondary_state = replace(
        _state(),
        joint_positions={"secondary": np.zeros(5)},
        joint_velocities={"secondary": np.zeros(5)},
        end_effector_poses={"secondary": _state().end_effector_poses["primary"]},
        gripper_positions={"secondary": 0.5},
        joint_names={"secondary": _state().joint_names["primary"]},
    )
    with pytest.raises(ValueError, match="only the primary arm"):
        codec.encode(action, secondary_state)


@pytest.mark.parametrize(
    ("low", "high"),
    [
        (np.zeros(5), np.ones(6)),
        (np.zeros(6), np.ones(7)),
        (np.zeros(6), np.zeros(6)),
        (np.ones(6), np.zeros(6)),
        (np.full(6, np.nan), np.ones(6)),
        (np.zeros(6), np.full(6, np.inf)),
    ],
)
def test_codec_rejects_malformed_bounds(low: np.ndarray, high: np.ndarray) -> None:
    with pytest.raises(ValueError, match="bounds"):
        SO101ActionCodec((low, high))
