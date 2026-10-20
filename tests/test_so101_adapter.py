"""Five-axis contracts, simulator bounds and public-API control regressions."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cap_harness.api import CapApi
from cap_harness.contracts import ArmCommand, RobotAction, Trajectory
from cap_harness.errors import ErrorCode
from cap_harness.registry import SO101_PUBLIC_TOOL_NAMES, ToolRegistry
from cap_harness.runtime import ProgramExecutor
from cap_harness.so101.adapter import SO101Adapter


@pytest.fixture
def adapter():
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    if not (
        Path(__file__).resolve().parents[1]
        / "third_party/so_arm100/Simulation/SO101/so101_new_calib.xml"
    ).is_file():
        pytest.skip("Run bash scripts/bootstrap_so101.sh")
    instance = SO101Adapter(camera_width=48, camera_height=48, horizon=300)
    instance.reset("so101_control", 1)
    yield instance
    instance.close()


def test_generated_program_moves_so101_and_keeps_gripper_target(adapter):
    api = CapApi(adapter, home_joint_positions=np.zeros(5))
    registry = api.register_tools(ToolRegistry(public_extension_allowlist=SO101_PUBLIC_TOOL_NAMES))
    execution = ProgramExecutor(registry).execute_program("""
initial = get_robot_state()
assert initial.embodiment == 'so101'
assert len(initial.joint_positions['primary']) == 5
bulk = set_grippers({'primary': 0.25})
assert bulk.ok
assert bulk.steps_executed == 1
assert set_gripper(0.25).ok
target = initial.joint_positions['primary'].copy()
target[0] = target[0] + 0.18
assert move_to_joints(target, tolerance=0.005).ok
state = get_robot_state()
assert abs(state.gripper_positions['primary'] - 0.25) < 0.025
assert abs(state.joint_positions['primary'][0] - target[0]) < 0.005
assert go_home().ok
result = {'joint_count': len(state.joint_names['primary'])}
""")
    assert execution.ok, execution.error
    assert execution.result["joint_count"] == 5
    assert not adapter.check_success()  # One joint is not the complete five-joint task.
    observation = adapter.get_observation()
    assert set(observation.cameras) == {"agentview", "sideview"}
    for image in observation.cameras.values():
        assert image.rgb.shape == (48, 48, 3)
        assert np.isfinite(image.depth_m).all()
        assert image.camera_pose.frame == "so101_base"
    assert len(adapter.get_planning_context().joint_names["primary"]) == 5


def test_invalid_target_and_stale_trajectory_never_advance_simulation(adapter):
    api = CapApi(adapter)
    before = adapter.get_robot_state()
    bad = api.move_to_joints(np.full(5, 10))
    assert not bad.ok
    assert bad.error.code == ErrorCode.INVALID_REQUEST
    assert adapter.current_time_s == 0
    target = before.joint_positions["primary"].copy()
    target[0] += 0.18
    assert api.move_to_joints(target).ok
    now = adapter.current_time_s
    stale = Trajectory(
        joint_positions=np.array([np.zeros(5)]),
        dt_s=0.05,
        joint_names=before.joint_names["primary"],
        expected_start=before,
        embodiment="so101",
        planner="interpolation",
        collision_aware=False,
    )
    result = api.execute_trajectory(stale)
    assert not result.ok
    assert result.error.code == ErrorCode.STALE_PLAN
    assert adapter.current_time_s == now


def test_horizon_is_reported_as_truncation(adapter):
    adapter._require_env().horizon = 1
    target = adapter.get_robot_state().joint_positions["primary"].copy()
    target[0] += 0.18
    result = CapApi(adapter).move_to_joints(target)
    assert not result.ok
    assert result.truncated
    assert result.error.code == ErrorCode.TRUNCATED


def test_invalid_native_target_preserves_pending_goals(adapter):
    before = adapter.get_robot_state()
    goals = adapter._joint_targets["primary"].copy()
    opening = adapter._gripper_targets["primary"]
    action = RobotAction(
        {"primary": ArmCommand("joint_position", np.full(5, 10), 0.25, "so101")}
    )
    result = adapter.step(action)
    assert not result.ok
    assert result.error.code == ErrorCode.INVALID_REQUEST
    assert adapter.current_time_s == before.timestamp_s
    np.testing.assert_array_equal(adapter._joint_targets["primary"], goals)
    assert adapter._gripper_targets["primary"] == opening


def test_terminal_episode_rejects_additional_steps(adapter):
    adapter.native_env.horizon = 1
    action = RobotAction(
        {"primary": ArmCommand("joint_position", np.full(5, 0.18), embodiment="so101")}
    )
    assert adapter.step(action).truncated
    before = adapter.get_robot_state()
    result = adapter.step(action)
    assert not result.ok
    assert result.truncated
    assert adapter.current_time_s == before.timestamp_s
    np.testing.assert_array_equal(
        adapter.get_robot_state().joint_positions["primary"], before.joint_positions["primary"]
    )


@pytest.mark.parametrize("frequency", [10, 20, 50])
def test_servo_setpoint_rates_are_independent_of_control_frequency(adapter, frequency):
    adapter.close()
    instance = SO101Adapter(
        control_frequency=frequency, camera_width=48, camera_height=48, horizon=10
    )
    try:
        instance.reset("so101_control", 1)
        env = instance.native_env
        previous = env.sim.data.ctrl[env.actuator_ids].copy()
        target = np.minimum(previous + 0.5, env.action_spec[1])
        target[5] = env.action_spec[0][5]
        env.step(target)
        issued = env.sim.data.ctrl[env.actuator_ids]
        # Check issued setpoints, rather than confusing them with measured
        # physical velocity. The same rates apply at each configured frequency.
        limits = np.array([1.0] * 5 + [3.0]) / frequency
        np.testing.assert_allclose(issued - previous, np.clip(target - previous, -limits, limits))
    finally:
        instance.close()


def test_joint_interpolation_executes_without_a_planning_provider(adapter):
    api = CapApi(adapter)
    target = adapter.get_robot_state().joint_positions["primary"].copy()
    target[0] += 0.18
    plan = api.plan_motion(target)
    assert plan.ok, plan.error
    assert plan.trajectory.embodiment == "so101"
    assert plan.trajectory.waypoints.shape[1] == 5
    assert not plan.trajectory.collision_aware
    execution = api.execute_trajectory(plan.trajectory)
    assert execution.ok, execution.error


def test_recorded_runner_needs_no_perception_or_planning_service(adapter, monkeypatch, tmp_path):
    import json

    import cap_harness.run as run_module

    def unexpected_service(*args, **kwargs):
        raise AssertionError("SO-101 control must not instantiate model-service clients")

    for provider in ("Sam3Provider", "ContactGraspNetProvider", "PyRokiProvider", "CuRoboProvider"):
        monkeypatch.setattr(run_module, provider, unexpected_service)
    # Free the fixture renderer before the recorded runner creates its own.
    adapter.close()
    program = tmp_path / "observation.py"
    program.write_text("result = {'embodiment': get_robot_state().embodiment}\n")
    outcome = run_module.run_program(
        benchmark="so101",
        suite="so101_control",
        task_id=0,
        seed=1,
        program_path=program,
        output_root=tmp_path / "runs",
        max_steps=10,
        camera_width=48,
        camera_height=48,
        capture_videos=False,
    )
    assert outcome.program_ok
    assert outcome.task_success is False
    assert outcome.termination_reason == "program_completed"
    recorded = json.loads((outcome.run_dir / "run.json").read_text())
    assert recorded["providers"]["segmentation"] == "color-rgbd"
    assert recorded["providers"]["grasping"] == ["so101-geometric"]
    assert recorded["providers"]["ik"] == ["so101"]
    assert recorded["providers"]["trajectory_planning"] == ["interpolation", "so101"]
