"""Load release must follow actual relative motion, never elapsed time or score."""

from pathlib import Path

import numpy as np
import pytest

from cap_harness.api import CapApi
from cap_harness.registry import SO101_PUBLIC_TOOL_NAMES, ToolRegistry
from cap_harness.runtime import ProgramExecutor
from cap_harness.so101.adapter import SO101Adapter
from cap_harness.so101.detachment import release_regime


def regime(angle, load, extension=0.001, work=0.001):
    return release_regime(
        angle,
        load,
        extension,
        work,
        bent_force_n=3.175,
        straight_force_n=13.9366666667,
        bend_trial_deg=70,
    )


@pytest.mark.parametrize(
    "angle,load,extension,work,expected",
    [
        (75, 3.2, 0.001, 0.001, "bend_and_pull_proxy"),
        (0, 14, 0.001, 0.001, "straight_pull_proxy"),
        (90, 0, 0.001, 0.001, None),  # bend alone
        (0, 3.2, 0.001, 0.001, None),  # low force is not enough for straight pull
        (45, 8, 0.001, 0.001, None),  # unsupported intermediate regime
        (75, 3.2, -0.001, 0.001, None),  # compression, even with large load
        (75, 3.2, 0.001, -0.001, None),
        (75, 3.2, 0, 0.001, None),
        (np.nan, 20, 0.001, 0.001, None),
    ],
)
def test_relative_motion_and_loading_regimes(angle, load, extension, work, expected):
    assert regime(angle, load, extension, work) == expected


@pytest.fixture
def adapter(monkeypatch):
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    root = Path(__file__).resolve().parents[1]
    if not (root / "third_party/so_arm100/Simulation/SO101/so101_new_calib.xml").is_file():
        pytest.skip("Run bash scripts/bootstrap_so101.sh")
    instance = SO101Adapter(camera_width=48, camera_height=48, horizon=1000)
    instance.reset("so101_strawberry_detachment", 1)
    # Policy uses joints and virtual contacts only. Separate CLI run renders all frames.
    images = instance.native_env._observation()
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
    for sample_index in range(round(seconds / env.model.opt.timestep)):
        env.sim.step()
        env._after_physics_step()


def test_waiting_does_not_release_and_reset_restores_attachment(adapter):
    env = adapter.native_env
    advance(env, 12)
    assert env.detached_time is None
    assert env.sim.data._data.eq_active[env.fixture_id]
    assert np.linalg.norm(env.fruit_position() - [0.365, 0, 0.24]) < 0.001
    assert not adapter.check_success()
    assert env.maximum_load_n < 0.5


@pytest.mark.parametrize("force_z", [-1.0, 1.0])
def test_native_junction_force_and_tensile_direction(adapter, force_z):
    env = adapter.native_env
    # Known host-side load tests the constraint-force measurement independently
    # of the gripper/controller. It is never used by the public manipulation.
    env.sim.data._data.xfrc_applied[env.fruit_body_id, 2] = force_z
    advance(env, 0.5)
    state = env.junction_state()
    assert state["load_n"] == pytest.approx(abs(force_z), abs=0.02)
    assert np.sign(state["extension_m"]) == -np.sign(force_z)
    assert env.detached_time is None
    env.sim.data._data.xfrc_applied[env.fruit_body_id] = 0


def test_public_bend_pull_release_retention_and_later_drop(adapter):
    execution = execute(adapter)
    assert execution.ok, execution.error
    env = adapter.native_env
    evidence = env.task_evidence()
    assert adapter.check_success(), evidence
    event = evidence["release_event"]
    assert event["regime"] == "bend_and_pull_proxy"
    assert evidence["grasp_verified_time_s"] < event["time_s"]
    assert event["bend_deg"] >= 70 and event["load_n"] >= 3.175
    assert event["extension_m"] >= 0.0001 and event["outward_work_j"] > 0
    assert evidence["current_retention_s"] >= 2
    assert not evidence["fixture_active"]
    assert evidence["maximum_relative_slip_m"] <= 0.008
    assert not evidence["forbidden_contact_pairs"] and not evidence["limit_violations"]
    assert not evidence["non_finger_support_contacts"]
    assert not evidence["retention_violations"]
    assert not evidence["biological_fracture_calibrated"]
    assert not evidence["robot_geometry_and_actuators_modified"]
    assert evidence["minimum_arm_joint_limit_margin_rad"] > 0
    assert "fixture_release_time_s" not in adapter.get_task_metadata()["lesson"]
    # Actual opening invalidates previous success; the junction never reattaches.
    assert CapApi(adapter).open_gripper().ok
    advance(env, 0.5)
    assert not adapter.check_success()
    assert not env.sim.data._data.eq_active[env.fixture_id]
    assert "fruit_slipped_or_dropped" in env.retention_violations
    env.reset()
    assert env.release_event is None and env.detached_time is None
    assert env.sim.data._data.eq_active[env.fixture_id]
    assert not env.retention_violations


def test_bend_without_withdrawal_keeps_junction(adapter):
    program = source().replace("range(len(bend_and_pull_points))", "range(7)")
    execution = execute(adapter, program)
    assert execution.ok, execution.error
    env = adapter.native_env
    assert env.maximum_bend_deg >= 70
    assert env.detached_time is None
    assert env.sim.data._data.eq_active[env.fixture_id]
    assert not adapter.check_success()


@pytest.mark.parametrize("force_n", [1.57, 5.10])
def test_empirical_force_endpoints_are_not_silently_clamped(adapter, force_n):
    env = adapter.native_env
    env.bent_force_n = force_n
    execution = execute(adapter)
    assert execution.ok, execution.error
    # Sensitivity is measured, not forced to pass at every force sample.
    if env.release_event:
        assert env.release_event["load_n"] >= force_n
        assert env.release_event["bend_deg"] >= 70
    else:
        assert env.maximum_load_n < force_n or env.maximum_bend_deg < 70
        assert not adapter.check_success()
