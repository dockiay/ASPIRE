"""Contact-based success, failed closures, transient collision and force recovery checks."""

from pathlib import Path

import pytest

from cap_harness.api import CapApi
from cap_harness.contracts import ArmCommand, RobotAction
from cap_harness.registry import SO101_PUBLIC_TOOL_NAMES, ToolRegistry
from cap_harness.runtime import ProgramExecutor
from cap_harness.so101.adapter import SO101Adapter


def lesson_source():
    return (
        Path(__file__).resolve().parents[1] / "examples/robosuite/so101_strawberry_grasp_contact.py"
    ).read_text()


@pytest.fixture
def adapter():
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    root = Path(__file__).resolve().parents[1]
    if not (root / "third_party/so_arm100/Simulation/SO101/so101_new_calib.xml").is_file():
        pytest.skip("Run bash scripts/bootstrap_so101.sh")
    instance = SO101Adapter(camera_width=48, camera_height=48, horizon=400)
    instance.reset("so101_strawberry_grasp_contact", 1)
    yield instance
    instance.close()


def execute(adapter, source=None):
    registry = CapApi(adapter).register_tools(
        ToolRegistry(public_extension_allowlist=SO101_PUBLIC_TOOL_NAMES)
    )
    return ProgramExecutor(registry).execute_program(source or lesson_source())


def test_public_grasp_program_and_late_transient_contact(adapter, monkeypatch):
    initial_sensors = adapter.get_finger_contacts()
    assert set(initial_sensors) == {"source", "timestamp_s", "fixed", "moving"}
    assert initial_sensors["fixed"]["normal_force_n"] == 0
    assert initial_sensors["moving"]["normal_force_n"] == 0
    execution = execute(adapter)
    assert execution.ok, execution.error
    assert adapter.check_success()
    env = adapter.native_env
    evidence = env.task_evidence()
    assert evidence["longest_bilateral_contact_s"] >= 0.5
    assert evidence["grasp_verified_time_s"] < evidence["release_verified_time_s"]
    assert evidence["ready_step"] / adapter.control_frequency < evidence["grasp_verified_time_s"]
    assert (
        evidence["release_verified_time_s"]
        < evidence["retreat_verified_step"] / adapter.control_frequency
    )
    assert evidence["grasp_witness"]["normal_dot_product"] <= -0.5
    assert evidence["grasp_witness"]["contact_separation_m"] >= 0.02
    assert all(0.1 <= f <= 12 for f in evidence["grasp_witness"]["finger_forces_n"].values())
    assert max(evidence["peak_finger_forces_n"].values()) <= 12
    assert evidence["maximum_contact_penetration_m"] <= 0.0015
    assert evidence["forbidden_contact_pairs"] == []
    assert not evidence["robot_model_modified"]
    assert not evidence["fruit_detached"]
    # A completed grasp is invalidated by even a brief forbidden contact later.
    original_step = env.sim.step
    initial = env.sim.data.qpos.copy()
    original_ctrl = env.sim.data.ctrl.copy()
    samples = 0

    def transient_step():
        nonlocal samples
        original_step()
        samples += 1
        if samples == 1:
            env.sim.data.qpos[env.qpos_indexes[:5]] = [0, 0.8, 0.8, 0.8, 0]
        elif samples == 2:
            env.sim.data.qpos[:] = initial
            env.sim.data.qvel[:] = 0
            env.sim.data.ctrl[:] = original_ctrl

    monkeypatch.setattr(env.sim, "step", transient_step)
    assert adapter.native_step(
        RobotAction({"primary": ArmCommand("joint_position", env.home, embodiment="so101")})
    ).ok
    assert env.sim.data.ncon == 0
    assert env.task_evidence()["forbidden_contact_pairs"]
    assert not adapter.check_success()


def test_closing_empty_space_is_not_a_grasp_and_reset_clears_failure(adapter):
    api = CapApi(adapter)
    assert api.close_gripper().ok
    assert adapter.get_finger_contacts()["fixed"]["normal_force_n"] == 0
    assert adapter.get_finger_contacts()["moving"]["normal_force_n"] == 0
    assert not adapter.check_success()
    assert adapter.native_env.task_evidence()["early_closure"]
    adapter.reset("so101_strawberry_grasp_contact", 1)
    evidence = adapter.native_env.task_evidence()
    assert not evidence["early_closure"]
    assert evidence["grasp_verified_time_s"] is None


def test_only_one_finger_touching_is_not_a_grasp(adapter):
    source = lesson_source().split('print("2.')[0]
    execution = execute(adapter, source + "\nhold(grasp, 0.25, 15)\n")
    assert execution.ok, execution.error
    sensors = adapter.get_finger_contacts()
    assert sensors["moving"]["normal_force_n"] > 0.1
    assert sensors["fixed"]["normal_force_n"] < 0.1
    assert adapter.native_env.ready_step is not None
    assert adapter.native_env.clean()
    assert adapter.native_env.grasp_time is None
    assert not adapter.check_success()


def test_contacts_must_be_held_before_reopening(adapter):
    execution = execute(
        adapter,
        lesson_source().replace(
            "hold(grasp, selected_opening, 14)", "hold(grasp, selected_opening, 2)"
        ),
    )
    assert execution.ok, execution.error
    evidence = adapter.native_env.task_evidence()
    assert evidence["longest_bilateral_contact_s"] < 0.5
    assert evidence["grasp_verified_time_s"] is None
    assert not adapter.check_success()


def test_excess_force_remains_a_failure_after_opening_and_retreat(adapter):
    source = lesson_source().split('print("2.')[0]
    source += "\nhold(grasp, 0.22, 15)\nassert open_gripper().ok\n"
    source += "interpolate(grasp, preapproach, 1.0, 30)\n"
    source += "assert move_to_joints(home, tolerance=0.003).ok\nhold(home, 1.0, 10)\n"
    execution = execute(adapter, source)
    assert execution.ok, execution.error
    evidence = adapter.native_env.task_evidence()
    assert max(evidence["peak_finger_forces_n"].values()) > 12
    assert "excessive_model_finger_force" in evidence["limit_violations"]
    assert evidence["final_gripper_opening"] > 0.97
    assert evidence["final_retreat_error_m"] < 0.008
    assert not adapter.check_success()
    adapter.reset("so101_strawberry_grasp_contact", 1)
    assert adapter.native_env.clean()
