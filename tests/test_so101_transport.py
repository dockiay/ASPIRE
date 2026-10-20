"""Placement needs ordered carry, release, base support, stability and withdrawal."""

from pathlib import Path

import numpy as np
import pytest

from cap_harness.api import CapApi
from cap_harness.registry import SO101_PUBLIC_TOOL_NAMES, ToolRegistry
from cap_harness.runtime import ProgramExecutor
from cap_harness.so101.adapter import SO101Adapter


def lesson_source():
    return (
        Path(__file__).resolve().parents[1] / "examples/robosuite/so101_strawberry_transport.py"
    ).read_text()


@pytest.fixture
def adapter(monkeypatch):
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    root = Path(__file__).resolve().parents[1]
    if not (root / "third_party/so_arm100/Simulation/SO101/so101_new_calib.xml").is_file():
        pytest.skip("Run bash scripts/bootstrap_so101.sh")
    instance = SO101Adapter(camera_width=48, camera_height=48, horizon=1000)
    instance.reset("so101_strawberry_transport", 1)
    # This policy reads joints and contacts only. Avoid repeated camera rendering
    # in physics unit tests; the separately recorded CLI run verifies real images.
    first_images = instance.native_env._observation()
    monkeypatch.setattr(instance.native_env, "_observation", lambda: first_images)
    yield instance
    instance.close()


def execute(adapter, source=None):
    registry = CapApi(adapter).register_tools(
        ToolRegistry(public_extension_allowlist=SO101_PUBLIC_TOOL_NAMES)
    )
    return ProgramExecutor(registry).execute_program(source or lesson_source())


def advance(env, seconds):
    for sample_index in range(round(seconds / env.model.opt.timestep)):
        env.sim.step()
        env._after_physics_step()


def test_public_placement_current_stability_late_support_and_reset(adapter):
    execution = execute(adapter)
    assert execution.ok, execution.error
    assert adapter.check_success()
    env = adapter.native_env
    e = env.task_evidence()
    assert (
        e["grasp_verified_time_s"]
        < e["fixture_release_time_s"]
        < e["free_hold_verified_time_s"]
        < e["destination_ready_time_s"]
        < e["deposit_started_time_s"]
        < e["first_container_base_contact_time_s"]
    )
    assert e["maximum_carried_distance_m"] >= 0.15
    assert e["maximum_relative_slip_m"] <= 0.008
    assert e["placement_hold_s"] >= 1.0
    assert e["final_tool_to_fruit_distance_m"] >= 0.08
    assert e["final_gripper_opening"] > 0.97
    assert e["final_container_base_support_force_n"] == pytest.approx(0.020 * 9.81, abs=0.005)
    assert e["container_base_contact_dimension"] == 6
    assert e["fruit_contact_dimension"] == [4, 4]
    assert e["final_contact_witness"] is None
    assert not e["transport_violations"] and not e["retention_violations"]
    assert not e["forbidden_contact_pairs"] and not e["limit_violations"]
    assert not e["contact_parameters_calibrated"]
    assert not e["robot_geometry_and_actuators_modified"]
    # A fruit still inside but moving cannot reuse an earlier successful hold.
    saved_qpos, saved_qvel = env.sim.data.qpos.copy(), env.sim.data.qvel.copy()
    env.sim.data.qvel[env.fruit_dof + 3] = 1.0
    advance(env, 0.002)
    assert not adapter.check_success()
    assert env.placement_duration == 0
    env.sim.data.qpos[:] = saved_qpos
    env.sim.data.qvel[:] = saved_qvel
    env.sim.forward()
    advance(env, 1.2)
    assert adapter.check_success()
    # Even a one-physics-step floor contact after placement remains forbidden.
    fruit_qpos = int(env.model.jnt_qposadr[env.fruit_joint_id])
    env.sim.data.qpos[fruit_qpos : fruit_qpos + 3] = [0.40, -0.35, 0.010]
    env.sim.forward()
    advance(env, 0.002)
    env.sim.data.qpos[:] = saved_qpos
    env.sim.data.qvel[:] = saved_qvel
    env.sim.forward()
    advance(env, 1.2)
    assert any("work_surface" in pair for pair in env.support_contacts)
    assert not adapter.check_success()
    adapter.reset("so101_strawberry_transport", 1)
    env = adapter.native_env
    assert env.sim.data._data.eq_active[env.fixture_id]
    assert env.deposit_started_time is None and env.destination_ready_time is None
    assert env.free_hold_verified_time is None and env.placement_duration == 0
    assert not env.support_contacts and not env.transport_violations
    assert np.allclose(env.fruit_position(), [0.365, 0, 0.24])
    assert not adapter.check_success()


def test_retention_alone_does_not_complete_transport(adapter):
    source = lesson_source().split("withdraw =")[0]
    execution = execute(adapter, source)
    assert execution.ok, execution.error
    env = adapter.native_env
    assert env.free_hold_verified_time is not None
    assert env.destination_ready_time is None
    assert env.deposit_started_time is None
    assert not adapter.check_success()


def test_opening_away_from_container_is_a_failed_deposit(adapter):
    source = lesson_source().split("withdraw =")[0]
    source += "\nassert open_gripper().ok\nhold(grasp, 1.0, 40)\n"
    execution = execute(adapter, source)
    assert execution.ok, execution.error
    env = adapter.native_env
    assert "opened_before_verified_destination" in env.transport_violations
    assert env.deposit_started_time is None
    assert not adapter.check_success()


def test_held_over_destination_is_not_placement(adapter):
    source = lesson_source().split('print("7.')[0]
    execution = execute(adapter, source)
    assert execution.ok, execution.error
    env = adapter.native_env
    assert env.destination_ready_time is not None
    assert env.deposit_started_time is None
    assert env._bilateral_witness() is not None
    assert not env.has_base_contact()
    assert not adapter.check_success()


def test_fixed_opening_without_feedback_loses_the_fruit(adapter):
    source = lesson_source().split('print("6.')[0]
    source = source.replace('grip["opening"] -= 0.00025', 'grip["opening"] -= 0.0')
    source = source.replace('grip["opening"] += 0.0001', 'grip["opening"] += 0.0')
    execution = execute(adapter, source)
    assert execution.ok, execution.error
    env = adapter.native_env
    assert "fruit_slipped_or_dropped" in env.retention_violations
    assert env.destination_ready_time is None
    assert not adapter.check_success()
