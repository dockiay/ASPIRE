"""Ordered approach/retreat evidence and collision monitoring in real MuJoCo."""

from pathlib import Path

import pytest

from cap_harness.api import CapApi
from cap_harness.contracts import ArmCommand, RobotAction
from cap_harness.registry import SO101_PUBLIC_TOOL_NAMES, ToolRegistry
from cap_harness.runtime import ProgramExecutor
from cap_harness.so101.adapter import SO101Adapter


@pytest.fixture
def adapter():
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    root = Path(__file__).resolve().parents[1]
    if not (root / "third_party/so_arm100/Simulation/SO101/so101_new_calib.xml").is_file():
        pytest.skip("Run bash scripts/bootstrap_so101.sh")
    instance = SO101Adapter(camera_width=48, camera_height=48, horizon=300)
    instance.reset("so101_strawberry_approach", 1)
    yield instance
    instance.close()


def execute_lesson(adapter, source=None):
    if source is None:
        source = (
            Path(__file__).resolve().parents[1] / "examples/robosuite/so101_strawberry_approach.py"
        ).read_text()
    api = CapApi(adapter)
    tools = api.register_tools(ToolRegistry(public_extension_allowlist=SO101_PUBLIC_TOOL_NAMES))
    return ProgramExecutor(tools).execute_program(source)


def hold(adapter, ticks=10):
    joints = adapter.get_robot_state().joint_positions["primary"]
    for _ in range(ticks):
        assert adapter.native_step(
            RobotAction({"primary": ArmCommand("joint_position", joints, embodiment="so101")})
        ).ok


def test_public_lesson_has_ordered_measured_evidence_and_no_score_leak(adapter):
    lesson = adapter.get_task_metadata()["lesson"]
    assert lesson["target_source"] == "declared_fixed_lesson_coordinates"
    assert "task_success" not in lesson
    assert "approach_verified_step" not in lesson
    execution = execute_lesson(adapter)
    assert execution.ok, execution.error
    assert adapter.check_success()
    evidence = adapter.native_env.task_evidence()
    assert evidence["verified_target_error_m"] < 0.008
    assert evidence["verified_axis_error_deg"] < 10
    assert evidence["final_retreat_error_m"] < 0.008
    assert evidence["approach_verified_step"] < evidence["retreat_verified_step"]
    assert evidence["gripper_open_throughout"]
    assert evidence["forbidden_contact_pairs"] == []
    assert evidence["contact_monitor_period_s"] == pytest.approx(0.002)
    # Leaving the final retreat pose invalidates success again.
    assert CapApi(adapter).move_to_joints([0, -1.219625, 0.744906, 0.474719, 0]).ok
    assert not adapter.check_success()


def test_holding_initial_pose_cannot_complete_task(adapter):
    hold(adapter)
    assert not adapter.check_success()
    assert adapter.native_env.task_evidence()["approach_verified_step"] is None


def test_approach_without_retreat_cannot_complete_task(adapter):
    api = CapApi(adapter)
    assert api.move_to_joints([0, -1.219625, 0.744906, 0.474719, 0]).ok
    assert api.move_to_joints([0, -0.783978, 0.584575, 0.199403, 0]).ok
    hold(adapter)
    assert adapter.native_env.task_evidence()["approach_verified_step"] is not None
    assert not adapter.check_success()


def test_closed_gripper_failure_is_latched_and_reset_clears_it(adapter):
    assert CapApi(adapter).close_gripper().ok
    assert CapApi(adapter).open_gripper().ok
    assert execute_lesson(adapter).ok
    assert not adapter.check_success()
    assert not adapter.native_env.task_evidence()["gripper_open_throughout"]
    adapter.reset("so101_strawberry_approach", 1)
    assert adapter.native_env.task_evidence()["gripper_open_throughout"]
    assert adapter.native_env.task_evidence()["approach_verified_step"] is None


def test_transient_contact_between_control_frames_is_latched(adapter, monkeypatch):
    env = adapter.native_env
    original_step = env.sim.step
    initial = env.sim.data.qpos.copy()
    original_ctrl = env.sim.data.ctrl.copy()
    samples = 0

    def transient_step():
        nonlocal samples
        original_step()
        samples += 1
        if samples == 1:
            # Test-only fault injection: lower the tool into the work surface for
            # one physics sample, then restore it before the rendered 20 Hz frame.
            env.sim.data.qpos[env.qpos_indexes[:5]] = [0, 0.8, 0.8, 0.8, 0]
        elif samples == 2:
            env.sim.data.qpos[:] = initial
            env.sim.data.qvel[:] = 0
            env.sim.data.ctrl[:] = original_ctrl

    monkeypatch.setattr(env.sim, "step", transient_step)
    hold(adapter, ticks=1)
    assert samples == env.substeps
    assert env.forbidden_contacts, "Fault must produce a real MuJoCo contact"
    assert env.sim.data.ncon == 0, "Transient contact must be absent from the final frame"
    monkeypatch.setattr(env.sim, "step", original_step)
    assert execute_lesson(adapter).ok
    assert not adapter.check_success()
    assert env.task_evidence()["forbidden_contact_pairs"]
    adapter.reset("so101_strawberry_approach", 1)
    assert not adapter.native_env.forbidden_contacts


def test_initial_pose_must_be_distinct_from_target(adapter):
    env = adapter.native_env
    env.home[:] = [0, -0.783978, 0.584575, 0.199403, 0]
    with pytest.raises(ValueError, match="at least 8 cm"):
        env.reset()
