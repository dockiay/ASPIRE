"""Cross-tool command lifetimes, supervised validation, and frequency invariance."""

from types import SimpleNamespace

import numpy as np
import pytest

from cap_harness.api import CapApi
from cap_harness.contracts import ArmCommand, RobotAction
from cap_harness.errors import ErrorCode
from cap_harness.so101.adapter import SO101Adapter
from cap_harness.so101.environment import SO101ControlEnvironment


@pytest.fixture
def adapter(monkeypatch):
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    instance = SO101Adapter(camera_width=48, camera_height=48, horizon=300)
    instance.reset("so101_control", 0)
    image = instance.native_env._observation()
    monkeypatch.setattr(instance.native_env, "_observation", lambda: image)
    yield instance
    instance.close()


def snapshot(adapter):
    env = adapter.native_env
    return (
        adapter.current_time_s,
        env.sim.data.ctrl[env.actuator_ids].copy(),
        adapter._joint_targets["primary"].copy(),
        adapter.commanded_gripper_position(),
    )


def assert_unchanged(adapter, before):
    after = snapshot(adapter)
    for expected, actual in zip(before, after, strict=True):
        np.testing.assert_array_equal(actual, expected)


@pytest.mark.parametrize("reason", ["duration_limit", "force_limit", "contact_lost"])
def test_jaw_only_command_never_revives_cancelled_arm_goal(adapter, monkeypatch, reason):
    env = adapter.native_env
    if reason != "duration_limit":
        ticks = 0

        def after_physics():
            nonlocal ticks
            ticks += 1

        def contacts():
            force = 1.0 if reason == "contact_lost" else (4.0 if ticks >= 2 else 0.0)
            return {
                "fixed": {"normal_force_n": force},
                "moving": {
                    "normal_force_n": 0.0 if reason == "contact_lost" and ticks >= 2 else force
                },
            }

        monkeypatch.setattr(env, "_after_physics_step", after_physics)
        monkeypatch.setattr(adapter, "get_finger_contacts", contacts)
    target = adapter.get_robot_state().joint_positions["primary"] + [0.2, 0, 0, 0, 0]
    stopped = adapter.command_joints(
        target,
        duration_s=0.05,
        speed_rad_s=1,
        force_limit_n=3,
        stop_on_contact_loss=reason == "contact_lost",
    )
    assert stopped.diagnostics["stop_reason"] == reason
    measured = adapter.get_robot_state().joint_positions["primary"].copy()
    np.testing.assert_allclose(adapter._joint_targets["primary"], measured)
    assert adapter.set_grippers({"primary": adapter.commanded_gripper_position()}).ok
    np.testing.assert_allclose(env.active_command["arms"]["primary"]["joints_rad"], measured)


def test_normal_guarded_motion_latches_cached_arm_before_jaw_only_command(adapter):
    target = adapter.get_robot_state().joint_positions["primary"] + [0.03, 0, 0, 0, 0]
    assert adapter.command_joints(target).ok
    measured = adapter.get_robot_state().joint_positions["primary"].copy()
    assert adapter.set_grippers({"primary": 0.9}).ok
    np.testing.assert_allclose(
        adapter.native_env.active_command["arms"]["primary"]["joints_rad"], measured
    )


def test_shared_arm_motion_preserves_pending_jaw_goal_past_rate_limiter(adapter):
    api = CapApi(adapter)
    assert api.set_grippers({"primary": 0.25}).ok
    issued = adapter.issued_gripper_position()
    assert issued > 0.25
    assert adapter.commanded_gripper_position() == 0.25
    for angle in [0.15, 0.0, 0.15, 0.0]:
        target = adapter.get_robot_state().joint_positions["primary"].copy()
        target[0] = angle
        assert api.move_to_joints(target).ok
        assert adapter.commanded_gripper_position() == 0.25
    assert adapter.issued_gripper_position() == pytest.approx(0.25)
    assert adapter.get_robot_state().gripper_positions["primary"] == pytest.approx(0.25, abs=0.025)


def test_bounded_explicit_segment_starts_at_issued_jaw_not_pending_goal(adapter):
    assert adapter.set_grippers({"primary": 0.25}).ok
    issued = adapter.issued_gripper_position()
    assert issued > adapter.commanded_gripper_position()
    result = adapter.command_joints(
        adapter.get_robot_state().joint_positions["primary"],
        gripper_position=0.5,
        gripper_speed=0.1,
        minimum_duration_s=0.05,
    )
    assert result.ok and result.diagnostics["gripper_setpoint_preserved"]
    assert adapter.commanded_gripper_position() == pytest.approx(
        issued - 0.1 * adapter.control_period_s
    )
    assert adapter.issued_gripper_position() == pytest.approx(adapter.commanded_gripper_position())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"position": "bad"},
        {"position": None},
        {"position": [0.5]},
        {"position": True},
        {"position": np.bool_(False)},
        {"duration_s": {}},
        {"duration_s": True},
        {"speed": False},
        {"force_limit_n": float("nan")},
        {"force_limit_n": float("inf")},
        {"force_limit_n": [3]},
        {"stop_on_contact": "false"},
        {"stop_on_contact": 1},
        {"arm": "secondary"},
    ],
)
def test_gripper_malformed_request_is_typed_and_preserves_pending_goals(adapter, kwargs):
    assert adapter.set_grippers({"primary": 0.25}).ok
    before = snapshot(adapter)
    inputs = {"position": 0.5}
    inputs.update(kwargs)
    result = adapter.command_gripper(**inputs)
    assert not result.ok and result.steps_executed == 0
    assert result.error.code == ErrorCode.INVALID_REQUEST
    assert_unchanged(adapter, before)


def test_gripper_rejects_active_guard_without_replacing_it(adapter):
    env = adapter.native_env
    other_guard = lambda: None
    env.action_guard = other_guard
    before = snapshot(adapter)
    result = adapter.command_gripper(0.5)
    assert not result.ok and result.error.code == ErrorCode.INVALID_REQUEST
    assert env.action_guard is other_guard
    assert_unchanged(adapter, before)
    env.action_guard = None


def test_gripper_initial_force_stop_does_not_step_and_cancels_cached_arm(adapter, monkeypatch):
    assert adapter.step(
        RobotAction({"primary": ArmCommand("joint_position", [0.2, 0, 0, 0, 0], 0.25, "so101")})
    ).ok
    env = adapter.native_env
    monkeypatch.setattr(
        adapter,
        "get_finger_contacts",
        lambda: {"fixed": {"normal_force_n": 4.0}, "moving": {"normal_force_n": 0.0}},
    )
    state = adapter.get_robot_state()
    result = adapter.command_gripper(0.0, force_limit_n=3.0)
    assert result.ok and result.steps_executed == 0
    assert result.diagnostics["stop_reason"] == "force_limit"
    assert not result.diagnostics["completed"]
    assert adapter.current_time_s == state.timestamp_s
    assert env.action_guard is None
    np.testing.assert_allclose(adapter._joint_targets["primary"], state.joint_positions["primary"])
    assert adapter.commanded_gripper_position() == state.gripper_positions["primary"]
    assert adapter.set_grippers({"primary": state.gripper_positions["primary"]}).ok
    np.testing.assert_allclose(
        env.active_command["arms"]["primary"]["joints_rad"], state.joint_positions["primary"]
    )


@pytest.mark.parametrize("terminal", ["horizon", "native_violation"])
def test_terminal_step_cancels_both_goals_and_rejects_further_motion(
    adapter, monkeypatch, terminal
):
    env = adapter.native_env
    if terminal == "horizon":
        env.horizon = 1
    else:
        monkeypatch.setattr(env, "requires_safe_continuation", lambda: False)

        def violation():
            env.safety_stop = "engineering_native_violation"

        monkeypatch.setattr(env, "_after_physics_step", violation)
    result = adapter.step(
        RobotAction({"primary": ArmCommand("joint_position", [0.2, 0, 0, 0, 0], 0.25, "so101")})
    )
    assert result.truncated
    measured = adapter.get_robot_state()
    np.testing.assert_allclose(
        adapter._joint_targets["primary"], measured.joint_positions["primary"]
    )
    assert adapter.commanded_gripper_position() == measured.gripper_positions["primary"]
    before = snapshot(adapter)
    for method, target in [
        (adapter.command_gripper, 0.5),
        (adapter.command_joints, measured.joint_positions["primary"]),
        (adapter.set_grippers, {"primary": 0.5}),
    ]:
        stopped = method(target)
        assert not stopped.ok and stopped.steps_executed == 0 and stopped.truncated
        assert_unchanged(adapter, before)


def test_native_rejected_target_does_not_overwrite_accepted_goals(adapter):
    assert adapter.set_grippers({"primary": 0.25}).ok
    before = snapshot(adapter)
    result = adapter.step(
        RobotAction({"primary": ArmCommand("joint_position", [99] * 5, 0.8, "so101")})
    )
    assert not result.ok and result.error.code == ErrorCode.INVALID_REQUEST
    assert_unchanged(adapter, before)


def test_native_execution_error_cancels_goals_before_later_commands(adapter, monkeypatch):
    def failure(_action):
        raise RuntimeError("engineering execution failure")

    monkeypatch.setattr(adapter.native_env, "step", failure)
    result = adapter.step(
        RobotAction({"primary": ArmCommand("joint_position", [0.2, 0, 0, 0, 0], 0.25, "so101")})
    )
    assert not result.ok and result.error.code == ErrorCode.ADAPTER_FAILED
    measured = adapter.get_robot_state()
    np.testing.assert_allclose(
        adapter._joint_targets["primary"], measured.joint_positions["primary"]
    )
    assert adapter.commanded_gripper_position() == measured.gripper_positions["primary"]


@pytest.mark.parametrize("frequency", [10, 20, 50])
def test_native_rate_limits_are_per_second_at_supported_frequencies(frequency):
    # Isolate setpoint generation from dynamics; no simulated success is asserted.
    env = SO101ControlEnvironment.__new__(SO101ControlEnvironment)
    env.frequency = frequency
    env.safety_stop = None
    env.action_guard = None
    env.action_stop = None
    env.elapsed = 0
    env.horizon = 100
    env.substeps = 1
    env.actuator_ids = np.arange(6)
    env.qpos_indexes = np.arange(6)
    env.action_spec = (-np.full(6, 10), np.full(6, 10))
    env.sim = SimpleNamespace(
        data=SimpleNamespace(ctrl=np.zeros(6), qpos=np.zeros(6)),
        step=lambda: None,
        forward=lambda: None,
    )
    env._after_physics_step = lambda: None
    env._after_control_step = lambda: None
    env._observation = dict
    env._check_success = lambda: False
    for _ in range(round(frequency * 0.2)):
        env.step(np.full(6, 5.0))
    np.testing.assert_allclose(env.sim.data.ctrl, [0.2] * 5 + [0.6], atol=1e-12)
