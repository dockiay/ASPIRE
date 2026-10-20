"""Retain real simulated mass; reject fixture support, falling and transient support."""

from pathlib import Path

import numpy as np
import pytest

from cap_harness.api import CapApi
from cap_harness.registry import SO101_PUBLIC_TOOL_NAMES, ToolRegistry
from cap_harness.runtime import ProgramExecutor
from cap_harness.so101.adapter import SO101Adapter


def lesson_source():
    return (
        Path(__file__).resolve().parents[1] / "examples/robosuite/so101_strawberry_retention.py"
    ).read_text()


@pytest.fixture
def adapter():
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    root = Path(__file__).resolve().parents[1]
    if not (root / "third_party/so_arm100/Simulation/SO101/so101_new_calib.xml").is_file():
        pytest.skip("Run bash scripts/bootstrap_so101.sh")
    instance = SO101Adapter(camera_width=48, camera_height=48, horizon=400)
    instance.reset("so101_strawberry_retention_torsion", 1)
    yield instance
    instance.close()


def execute(adapter, source=None):
    registry = CapApi(adapter).register_tools(
        ToolRegistry(public_extension_allowlist=SO101_PUBLIC_TOOL_NAMES)
    )
    return ProgramExecutor(registry).execute_program(source or lesson_source())


def advance(env, seconds):
    """Host-side physics probe holding existing controls; no rendering required."""
    for sample_index in range(round(seconds / env.model.opt.timestep)):
        env.sim.step()
        env._after_physics_step()


def test_public_retention_then_opening_invalidates_success_and_reset(adapter):
    env = adapter.native_env
    assert env.model.body_mass[env.fruit_body_id] == pytest.approx(0.020)
    assert env.model.body_gravcomp[env.fruit_body_id] == 0
    assert env.model.neq == 1
    assert env.model.eq_obj1id[0] == env.fruit_body_id
    assert env.model.body(env.model.eq_obj2id[0]).name == "lesson_plant"
    assert env.sim.data.ncon == 0
    execution = execute(adapter)
    assert execution.ok, execution.error
    assert adapter.check_success()
    evidence = env.task_evidence()
    assert evidence["grasp_verified_time_s"] < evidence["fixture_release_time_s"]
    assert evidence["fixture_release_time_s"] == pytest.approx(8.0)
    assert evidence["current_retention_s"] >= 2
    assert not evidence["fixture_active"]
    assert evidence["maximum_relative_slip_m"] <= 0.008
    assert evidence["non_finger_support_contacts"] == []
    assert evidence["retention_violations"] == []
    assert not evidence["robot_model_modified"]
    # An old successful hold cannot survive opening and dropping the fruit.
    assert CapApi(adapter).open_gripper().ok
    advance(env, 0.6)
    assert not adapter.check_success()
    assert "fruit_slipped_or_dropped" in env.retention_violations
    assert env.fruit_position()[2] < 0.10
    adapter.reset("so101_strawberry_retention_torsion", 1)
    env = adapter.native_env
    assert env.sim.data._data.eq_active[env.fixture_id]
    assert np.allclose(env.fruit_position(), [0.365, 0, 0.24])
    assert env.detached_time is None and env.retention_start is None
    assert not env.retention_violations and not env.support_contacts
    assert env.maximum_relative_slip == 0 and not adapter.check_success()


def test_release_without_fingers_falls_under_gravity(adapter):
    env = adapter.native_env
    initial = env.fruit_position().copy()
    advance(env, 8.0)
    # It must really remain held by the fixture until its declared release time.
    assert np.linalg.norm(env.fruit_position() - initial) < 0.001
    assert not env.sim.data._data.eq_active[env.fixture_id]
    advance(env, 0.15)
    assert initial[2] - env.fruit_position()[2] > 0.08
    assert not adapter.check_success()
    assert "fixture_released_without_qualified_grasp" in env.retention_violations
    assert "fruit_slipped_or_dropped" in env.retention_violations
    assert env.current_retention_duration == 0


def test_same_program_with_point_contacts_drops_the_fruit(adapter):
    adapter.reset("so101_strawberry_retention", 1)
    assert adapter.get_task_metadata()["lesson"]["contact_dimension"] == 3
    execution = execute(adapter)
    assert execution.ok, execution.error
    env = adapter.native_env
    assert env.grasp_time is not None
    assert env.detached_time is not None
    assert "fruit_slipped_or_dropped" in env.retention_violations
    assert env.longest_retention_duration < 2
    assert not adapter.check_success()


def test_short_free_contact_cannot_complete_retention(adapter):
    source = lesson_source().replace(
        'lesson["fixture_release_time_s"] + lesson["retention_seconds"] + 0.5', "8.25"
    )
    execution = execute(adapter, source)
    assert execution.ok, execution.error
    env = adapter.native_env
    assert env.detached_time is not None
    assert env._bilateral_witness() is not None
    assert 0 < env.current_retention_duration < 0.30
    assert not adapter.check_success()


def test_active_fixture_is_never_retention_and_reactivation_is_latched(adapter):
    # Stop just before release: stable contact supported by the fixture cannot pass.
    source = lesson_source().replace(
        'lesson["fixture_release_time_s"] + lesson["retention_seconds"] + 0.5', "7.9"
    )
    execution = execute(adapter, source)
    assert execution.ok, execution.error
    env = adapter.native_env
    assert env.grasp_time is not None and env._bilateral_witness() is not None
    assert env.sim.data._data.eq_active[env.fixture_id]
    assert not adapter.check_success()
    advance(env, 8.0 - env.sim.data.time)
    assert not env.sim.data._data.eq_active[env.fixture_id]
    # The release boundary must use fresh free-body forces, not cached loads
    # from the still-attached fixture's previous forward pass.
    sensors = adapter.get_finger_contacts()
    for side, contacts in env.current_contacts.items():
        assert sum(c["normal_force_n"] for c in contacts) == pytest.approx(
            sensors[side]["normal_force_n"], abs=1e-8
        )
    env.sim.data._data.eq_active[env.fixture_id] = True
    advance(env, 0.002)
    env.sim.data._data.eq_active[env.fixture_id] = False
    advance(env, 2.2)
    assert "fixture_reactivated" in env.retention_violations
    assert not adapter.check_success()


def test_transient_non_robot_support_is_latched(adapter):
    execution = execute(adapter)
    assert execution.ok, execution.error
    env = adapter.native_env
    assert adapter.check_success()
    # Move the dynamic fruit briefly onto the existing floor, away from the
    # robot. Moving a static plant geom would leave its compiled BVH stale.
    initial_qpos = env.sim.data.qpos.copy()
    initial_qvel = env.sim.data.qvel.copy()
    fruit_qpos = int(env.model.jnt_qposadr[env.fruit_joint_id])
    env.sim.data.qpos[fruit_qpos : fruit_qpos + 3] = [0.30, 0.10, 0.020]
    env.sim.forward()
    advance(env, 0.002)
    env.sim.data.qpos[:] = initial_qpos
    env.sim.data.qvel[:] = initial_qvel
    env.sim.forward()
    advance(env, 0.002)
    assert any("work_surface" in pair for pair in env.support_contacts)
    assert not env.forbidden_contacts  # This is fruit support, not robot contact.
    assert not adapter.check_success()
