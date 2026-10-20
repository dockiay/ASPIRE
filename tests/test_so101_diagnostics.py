"""Physical postconditions, transient faults and public/privileged separation."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from cap_harness.api import CapApi
from cap_harness.contracts import ArmCommand, RobotAction
from cap_harness.registry import SO101_PUBLIC_TOOL_NAMES, ToolRegistry
from cap_harness.runtime import ProgramExecutor
from cap_harness.so101.adapter import SO101Adapter


@pytest.fixture
def adapter(monkeypatch):
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    root = Path(__file__).resolve().parents[1]
    if not (root / "third_party/so_arm100/Simulation/SO101/so101_new_calib.xml").is_file():
        pytest.skip("Run bash scripts/bootstrap_so101.sh")
    instance = SO101Adapter(camera_width=48, camera_height=48, horizon=1000)
    instance.reset("so101_strawberry_detachment", 1)
    images = instance.native_env._observation()
    # Contact/joint policy; separate CLI runs exercise actual image recording.
    monkeypatch.setattr(instance.native_env, "_observation", lambda: images)
    yield instance
    instance.close()


def source():
    return (
        Path(__file__).resolve().parents[1] / "examples/robosuite/so101_strawberry_detachment.py"
    ).read_text()


def execute(adapter, program=None):
    registry = CapApi(adapter).register_tools(
        ToolRegistry(public_extension_allowlist=SO101_PUBLIC_TOOL_NAMES)
    )
    return ProgramExecutor(registry).execute_program(program or source())


def advance(env, seconds):
    for tick_index in range(round(seconds / env.model.opt.timestep)):
        env.sim.step()
        env._after_physics_step()


def diagnosis(adapter):
    result = adapter.native_env.task_evidence()["diagnostics"]
    assert result["task_success"] == adapter.check_success()
    if result["status"] == "failed":
        env = adapter.native_env
        assert not env.clean() or env.support_contacts or env.retention_violations
    assert [e["event_id"] for e in result["events"]] == list(range(1, len(result["events"]) + 1))
    assert [e["time_s"] for e in result["events"]] == sorted(e["time_s"] for e in result["events"])
    return result


def test_no_attempt_is_incomplete_and_does_not_invent_a_drop(adapter):
    env = adapter.native_env
    advance(env, 0.5)
    d = diagnosis(adapter)
    assert d["status"] == "incomplete"
    assert d["primary_finding"]["code"] == "grasp_not_qualified"
    assert d["primary_finding"]["time_s"] == pytest.approx(0.5)
    assert d["primary_finding"]["basis"] == "unmet_predicate_at_finalization"
    assert not any(e["code"] == "fruit_dropped" for e in d["events"])
    assert d["last_attached_junction_state"]["time_s"] == pytest.approx(0.5)


def test_grasped_attached_fruit_reports_missing_separation(adapter):
    program = source().split('print("4.')[0]
    result = execute(adapter, program)
    assert result.ok, result.error
    d = diagnosis(adapter)
    assert d["primary_finding"]["code"] == "junction_not_released"
    assert d["primary_finding"]["phase"] == "detachment"
    assert d["final_state"]["grasp_time_s"] is not None
    assert d["final_state"]["fixture_active"]


def test_short_current_hold_cannot_reuse_earlier_progress(adapter):
    program = source().replace("range(len(bend_and_pull_points))", "range(10)")
    program = program.replace("for tick_index in range(100):", "for tick_index in range(0):")
    result = execute(adapter, program)
    assert result.ok, result.error
    d = diagnosis(adapter)
    assert d["status"] == "incomplete"
    assert d["primary_finding"]["code"] == "retention_duration_short"
    assert d["final_state"]["bilateral_qualified"]
    assert 0 < d["final_state"]["current_retention_s"] < 2


def test_success_tolerates_recovered_contact_loss_but_later_drop_is_latched(adapter):
    result = execute(adapter)
    assert result.ok, result.error
    env = adapter.native_env
    d = diagnosis(adapter)
    assert d["status"] == "completed" and d["primary_finding"] is None
    assert d["findings"] == []
    assert any(e["code"] == "bilateral_contact_lost" for e in d["events"])
    assert any(e["code"] == "retention_verified" for e in d["events"])
    assert CapApi(adapter).open_gripper().ok
    advance(env, 0.5)
    d = diagnosis(adapter)
    assert d["status"] == "failed"
    assert d["primary_finding"]["code"] == "fruit_dropped"
    assert "relative_slip_exceeded" in {f["code"] for f in d["findings"]}
    event = next(e for e in d["events"] if e["code"] == "fruit_dropped")
    assert event["time_s"] > env.detached_time
    assert event["detail"]["descent_since_release_m"] >= 0.03
    assert event["visual_reference"]["frame_before"] <= event["time_s"] * 20
    assert event["visual_reference"]["frame_after"] >= event["time_s"] * 20 - 1e-6
    env.reset()
    assert env.diagnostic_monitor.events == []
    assert diagnosis(adapter)["primary_finding"]["code"] == "grasp_not_qualified"


def test_transient_collision_keeps_its_original_time_after_pose_is_restored(adapter):
    env = adapter.native_env
    saved = env.sim.data.qpos.copy()
    env.sim.data.qpos[env.qpos_indexes[:5]] = [0, 0.8, 0.8, 0.8, 0]
    env.sim.forward()
    advance(env, 0.002)
    env.sim.data.qpos[:] = saved
    env.sim.data.qvel[:] = 0
    env.sim.forward()
    advance(env, 0.1)
    d = diagnosis(adapter)
    assert d["primary_finding"]["code"] == "robot_collision"
    assert d["primary_finding"]["time_s"] == pytest.approx(0.002)
    event = next(e for e in d["events"] if e["code"] == "robot_collision")
    assert event["detail"]["contact_pair"]
    assert event["detail"]["measured_contacts"]
    assert all(c["distance_m"] <= 0 for c in event["detail"]["measured_contacts"])
    assert event["evidence"]["time_s"] == pytest.approx(0.002)


def test_real_overclosure_records_force_and_penetration_evidence(adapter):
    result = execute(adapter, source().split('print("4.')[0])
    assert result.ok, result.error
    env = adapter.native_env
    # Continue actual servo dynamics with the original gripper commanded closed.
    env.sim.data.ctrl[env.actuator_ids[5]] = env.action_spec[0][5]
    advance(env, 0.3)
    d = diagnosis(adapter)
    codes = {f["code"] for f in d["findings"]}
    assert "finger_force_limit_exceeded" in codes
    event = next(e for e in d["events"] if e["code"] == "finger_force_limit_exceeded")
    assert max(event["evidence"]["peak_finger_forces_n"].values()) > 12
    assert "penetration_limit_exceeded" in codes
    penetration = next(e for e in d["events"] if e["code"] == "penetration_limit_exceeded")
    assert penetration["evidence"]["maximum_penetration_m"] > 0.0015
    assert d["status"] == "failed"


def test_transient_floor_support_is_not_lost_after_restoring_free_pose(adapter):
    assert execute(adapter).ok
    env = adapter.native_env
    qpos, qvel = env.sim.data.qpos.copy(), env.sim.data.qvel.copy()
    fruit_qpos = int(env.model.jnt_qposadr[env.fruit_joint_id])
    env.sim.data.qpos[fruit_qpos : fruit_qpos + 3] = [0.40, -0.35, 0.010]
    env.sim.forward()
    advance(env, 0.002)
    first = next(e for e in env.diagnostic_monitor.events if e["code"] == "unexpected_support")
    env.sim.data.qpos[:] = qpos
    env.sim.data.qvel[:] = qvel
    env.sim.forward()
    advance(env, 0.002)
    d = diagnosis(adapter)
    finding = next(f for f in d["findings"] if f["code"] == "unexpected_support")
    assert finding["time_s"] == first["time_s"]
    assert "work_surface" in first["detail"]["contact_pair"]
    assert d["status"] == "failed"


def test_case_policy_cannot_query_diagnostics_or_reward_and_contract_stays_fixed(adapter):
    nominal_contract = diagnosis(adapter)["contract"]
    adapter.reset("so101_strawberry_detachment_cases", 101)
    env = adapter.native_env
    assert diagnosis(adapter)["contract"] == nominal_contract
    registry = CapApi(adapter).register_tools(
        ToolRegistry(public_extension_allowlist=SO101_PUBLIC_TOOL_NAMES)
    )
    result = ProgramExecutor(registry).execute_program("result = so101.get_diagnostics()")
    assert not result.ok
    assert "diagnostics" not in adapter.get_task_metadata()["lesson"]
    public = adapter.step(
        RobotAction(
            {
                "primary": ArmCommand(
                    "joint_position", env.home, gripper_position=1.0, embodiment="so101"
                )
            }
        )
    )
    assert public.ok
    assert public.reward is None
    assert not {"case", "diagnostics", "task_success", "release_event"} & public.diagnostics.keys()


def test_early_closure_records_the_actual_opening_without_claiming_a_drop(adapter):
    assert CapApi(adapter).close_gripper().ok
    d = diagnosis(adapter)
    event = next(e for e in d["events"] if e["code"] == "early_closure")
    assert event["evidence"]["gripper_opening"] < 0.9
    assert event["evidence"]["approach_ready_step"] is None
    assert "early_closure" in {f["code"] for f in d["findings"]}
    assert not any(e["code"] == "fruit_dropped" for e in d["events"])


def test_external_load_release_without_grasp_is_reported_as_invalid_physics(adapter):
    env = adapter.native_env
    # Deliberate host-side fault: this force is never available to a public policy.
    env.sim.data._data.xfrc_applied[env.fruit_body_id, 2] = -15.0
    advance(env, 0.15)
    d = diagnosis(adapter)
    assert env.detached_time is not None
    assert d["primary_finding"]["code"] == "invalid_physics"
    assert "released_without_qualified_grasp" in {f["code"] for f in d["findings"]}
    event = next(e for e in d["events"] if e["code"] == "released_without_qualified_grasp")
    assert event["evidence"]["grasp_time_s"] is None
    assert d["status"] == "failed"


def test_summary_preserves_execution_errors_when_no_physical_report_exists(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    error = {"type": "RuntimeError", "message": "Environment setup failed"}
    (run / "outcome.json").write_text(
        json.dumps(
            {
                "program_ok": False,
                "task_success": None,
                "termination_reason": "exception",
                "error": error,
            }
        )
    )
    script = Path(__file__).resolve().parents[1] / "scripts/summarize_so101_strawberry_run.py"
    output = tmp_path / "summary.json"
    subprocess.run(
        [sys.executable, str(script), str(run), "--output", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(output.read_text())
    assert summary["physical_status"] == "unavailable"
    assert summary["primary_finding"] is None
    assert summary["execution_error"] == error
    forbidden_output = run / "new-file.json"
    refusal = subprocess.run(
        [sys.executable, str(script), str(run), "--output", str(forbidden_output)],
        capture_output=True,
        text=True,
    )
    assert refusal.returncode != 0
    assert not forbidden_output.exists()
