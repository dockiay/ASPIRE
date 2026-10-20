"""Native arm control with explicit sensor fixtures, never a harvesting policy."""

import numpy as np
import pytest

from cap_harness.so101.adapter import SO101Adapter


@pytest.fixture
def adapter(monkeypatch):
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    instance = SO101Adapter(camera_width=48, camera_height=48, horizon=60)
    instance.reset("so101_control", 0)
    image = instance.native_env._observation()
    monkeypatch.setattr(instance.native_env, "_observation", lambda: image)
    yield instance
    instance.close()


def sensor_fixture(adapter, monkeypatch, *, contact_loss=False, terminal=False):
    """Inject a two-millisecond transient, not a native fruit/grasp success."""
    env = adapter.native_env
    original = env._after_physics_step
    ticks = 0

    def after_physics():
        nonlocal ticks
        original()
        ticks += 1
        if terminal and ticks == 2:
            env.safety_stop = "engineering_sensor_fixture_violation"

    def sample():
        fixed = 1.0 if contact_loss else (6.5 if ticks == 2 else 0.0)
        moving = 0.0 if contact_loss and ticks >= 2 else float(contact_loss)
        return {"fixed": {"normal_force_n": fixed}, "moving": {"normal_force_n": moving}}

    monkeypatch.setattr(env, "_after_physics_step", after_physics)
    monkeypatch.setattr(adapter, "get_finger_contacts", sample)


def test_transient_force_stops_arm_even_when_absent_at_return(adapter, monkeypatch):
    sensor_fixture(adapter, monkeypatch)
    target = adapter.get_robot_state().joint_positions["primary"] + [0.1, 0, 0, 0, 0]
    result = adapter.command_joints(target, force_limit_n=3)
    assert result.ok and result.steps_executed == 1
    assert result.diagnostics["stop_reason"] == "force_limit"
    assert result.diagnostics["peak_finger_forces_n"]["fixed"] == 6.5
    assert not result.diagnostics["target_reached"]
    assert adapter.get_finger_contacts()["fixed"]["normal_force_n"] == 0
    assert adapter.native_env.action_guard is None
    np.testing.assert_allclose(
        adapter.native_env.sim.data.ctrl[adapter.native_env.actuator_ids],
        adapter.native_env.sim.data.qpos[adapter.native_env.qpos_indexes],
    )


def test_lost_contact_stops_and_allows_a_subsequent_corrective_command(adapter, monkeypatch):
    sensor_fixture(adapter, monkeypatch, contact_loss=True)
    target = adapter.get_robot_state().joint_positions["primary"] + [0.1, 0, 0, 0, 0]
    result = adapter.command_joints(target, stop_on_contact_loss=True)
    assert result.ok and result.diagnostics["stop_reason"] == "contact_lost"
    assert result.steps_executed == 1 and not result.diagnostics["target_reached"]
    assert adapter.native_env.safety_stop is None
    correction = adapter.command_joints(adapter.get_robot_state().joint_positions["primary"])
    assert correction.ok and correction.diagnostics["target_reached"]


def test_missing_initial_contact_does_not_move(adapter):
    before = adapter.get_robot_state()
    result = adapter.command_joints(
        before.joint_positions["primary"] + 0.1, stop_on_contact_loss=True
    )
    assert result.ok and result.steps_executed == 0
    assert result.diagnostics["stop_reason"] == "contact_lost"
    assert adapter.get_robot_state().timestamp_s == before.timestamp_s


def test_guard_never_hides_or_clears_a_native_violation(adapter, monkeypatch):
    sensor_fixture(adapter, monkeypatch, terminal=True)
    target = adapter.get_robot_state().joint_positions["primary"] + [0.1, 0, 0, 0, 0]
    result = adapter.command_joints(target, force_limit_n=3)
    assert not result.ok and (result.truncated or result.terminated)
    elapsed = adapter.native_env.elapsed
    assert not adapter.command_joints(target).ok
    assert adapter.native_env.elapsed == elapsed
    assert adapter.native_env.action_guard is None


def test_duration_limit_returns_failure_and_cancels_pending_setpoint(adapter):
    target = adapter.get_robot_state().joint_positions["primary"] + [0.2, 0, 0, 0, 0]
    result = adapter.command_joints(target, duration_s=0.05, speed_rad_s=0.1)
    assert not result.ok and result.diagnostics["stop_reason"] == "duration_limit"
    assert result.steps_executed == 1 and not result.diagnostics["target_reached"]
    np.testing.assert_allclose(
        adapter.native_env.sim.data.ctrl[adapter.native_env.actuator_ids],
        adapter.native_env.sim.data.qpos[adapter.native_env.qpos_indexes],
    )


def test_reachable_small_motion_preserves_aperture(adapter):
    state = adapter.get_robot_state()
    target = state.joint_positions["primary"] + [0.03, 0, 0, 0, 0]
    result = adapter.command_joints(target, duration_s=2, speed_rad_s=0.1)
    assert result.ok and result.diagnostics["target_reached"]
    actual = adapter.get_robot_state()
    assert np.max(np.abs(actual.joint_positions["primary"] - target)) <= 0.003
    assert abs(actual.gripper_positions["primary"] - state.gripper_positions["primary"]) < 0.025


def test_explicit_jaw_moves_with_stationary_arm_and_keeps_issued_target(adapter):
    state = adapter.get_robot_state()
    result = adapter.command_joints(
        state.joint_positions["primary"],
        gripper_position=0.5,
        gripper_speed=0.1,
        minimum_duration_s=0.2,
        duration_s=0.3,
    )
    assert result.ok and result.diagnostics["completed"]
    assert result.steps_executed == 4
    assert result.diagnostics["gripper_setpoint_preserved"]
    # Only the rate-limited issued target persists, never a jump to the request.
    assert result.diagnostics["retained_gripper_setpoint"] == pytest.approx(0.98, abs=1e-6)
    assert (
        adapter.get_robot_state().gripper_positions["primary"] < state.gripper_positions["primary"]
    )


def test_explicit_jaw_target_is_cancelled_on_force_stop(adapter, monkeypatch):
    sensor_fixture(adapter, monkeypatch)
    target = adapter.get_robot_state().joint_positions["primary"] + [0.1, 0, 0, 0, 0]
    result = adapter.command_joints(target, gripper_position=0, force_limit_n=3)
    assert result.diagnostics["stop_reason"] == "force_limit"
    assert not result.diagnostics["completed"]
    assert not result.diagnostics["gripper_setpoint_preserved"]
    np.testing.assert_allclose(
        adapter.native_env.sim.data.ctrl[adapter.native_env.actuator_ids],
        adapter.native_env.sim.data.qpos[adapter.native_env.qpos_indexes],
    )


def test_segmented_explicit_commands_preserve_setpoint_continuity(adapter):
    target = adapter.get_robot_state().joint_positions["primary"]
    first = adapter.command_joints(target, gripper_position=0.5, gripper_speed=0.1)
    second = adapter.command_joints(target, gripper_position=0.5, gripper_speed=0.1)
    assert first.ok and second.ok
    assert first.diagnostics["retained_gripper_setpoint"] == pytest.approx(0.995)
    assert second.diagnostics["retained_gripper_setpoint"] == pytest.approx(0.990)


def test_shared_motion_uses_extension_setpoint_instead_of_stale_open_cache(adapter):
    from cap_harness.api import CapApi

    api = CapApi(adapter)
    before = adapter.get_robot_state()
    assert api.move_to_joints(before.joint_positions["primary"]).ok
    result = adapter.command_joints(
        before.joint_positions["primary"],
        gripper_position=0.5,
        gripper_speed=0.5,
        minimum_duration_s=0.3,
        duration_s=0.5,
    )
    assert result.ok
    target_opening = adapter.commanded_gripper_position()
    assert target_opening < 0.9
    assert api.move_to_joints(
        adapter.get_robot_state().joint_positions["primary"] + [0.03, 0, 0, 0, 0]
    ).ok
    assert adapter.commanded_gripper_position() == pytest.approx(target_opening)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"gripper_position": -1},
        {"gripper_position": float("nan")},
        {"gripper_position": True},
        {"gripper_speed": 0},
        {"minimum_duration_s": 3, "duration_s": 2},
    ],
)
def test_invalid_coordinated_jaw_request_does_not_move(adapter, kwargs):
    before = adapter.get_robot_state()
    result = adapter.command_joints(before.joint_positions["primary"], **kwargs)
    assert not result.ok
    assert before.timestamp_s == adapter.get_robot_state().timestamp_s


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target": [0, 0]},
        {"target": [float("nan")] * 5},
        {"target": [99] * 5},
        {"duration_s": 0},
        {"speed_rad_s": 2},
        {"force_limit_n": 13},
        {"stop_on_contact_loss": "yes"},
        {"tolerance_rad": 0},
        {"arm": "secondary"},
    ],
)
def test_invalid_request_never_advances_physics(adapter, kwargs):
    state = adapter.get_robot_state()
    inputs = {"target": state.joint_positions["primary"]}
    inputs.update(kwargs)
    result = adapter.command_joints(**inputs)
    assert not result.ok and result.steps_executed == 0
    assert result.error.code.value == "invalid_request"
    assert adapter.get_robot_state().timestamp_s == state.timestamp_s


def test_registered_tool_is_callable_from_restricted_program(adapter):
    from cap_harness.api import CapApi
    from cap_harness.registry import SO101_PUBLIC_TOOL_NAMES, ToolRegistry
    from cap_harness.runtime import ProgramExecutor

    registry = CapApi(adapter).register_tools(
        ToolRegistry(public_extension_allowlist=SO101_PUBLIC_TOOL_NAMES)
    )
    execution = ProgramExecutor(registry).execute_program(
        "state = get_robot_state()\n"
        "r = so101.command_joints(state.joint_positions['primary'])\n"
        "assert r.ok and r.diagnostics['target_reached']\n"
        "assert r.steps_executed == 0\n"
        "r = so101.command_joints(state.joint_positions['primary'], "
        "gripper_position=0.5, gripper_speed=0.1, minimum_duration_s=0.05)\n"
        "assert r.ok and r.diagnostics['completed']\n"
        "assert r.steps_executed == 1\n"
        "assert r.diagnostics['gripper_setpoint_preserved']\n"
        "result = {'stopped': r.diagnostics['stop_reason']}\n"
    )
    assert execution.ok, execution.error


@pytest.mark.parametrize("tool", ["command_joints", "command_gripper"])
def test_published_duration_boundary_matches_actual_validation(adapter, tool):
    limits = adapter.get_controller_metadata()["action_limits"][tool]
    maximum = limits["duration_s"]["maximum"]
    state = adapter.get_robot_state()
    target = (
        state.joint_positions["primary"]
        if tool == "command_joints"
        else state.gripper_positions["primary"]
    )
    method = getattr(adapter, tool)
    assert method(target, duration_s=maximum).ok
    before = adapter.get_robot_state().timestamp_s
    rejected = method(target, duration_s=maximum + 0.01)
    assert not rejected.ok and rejected.steps_executed == 0
    assert adapter.get_robot_state().timestamp_s == before


@pytest.mark.parametrize(
    "kwargs",
    [
        {"duration_s": True},
        {"speed_rad_s": np.bool_(True)},
        {"force_limit_n": [3.0]},
        {"minimum_duration_s": True},
        {"gripper_position": np.bool_(False)},
        {"gripper_position": [0.5]},
    ],
)
def test_joint_scalar_arguments_reject_booleans_and_arrays_before_motion(adapter, kwargs):
    state = adapter.get_robot_state()
    pending = adapter._joint_targets["primary"].copy()
    result = adapter.command_joints(state.joint_positions["primary"], **kwargs)
    assert not result.ok
    assert result.steps_executed == 0
    assert result.error.code.value == "invalid_request"
    assert adapter.current_time_s == state.timestamp_s
    np.testing.assert_array_equal(adapter._joint_targets["primary"], pending)
