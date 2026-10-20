"""Native primitive fixtures; prepositioning here is never a harvesting policy."""

import numpy as np
import pytest

from cap_harness.so101.adapter import SO101Adapter


@pytest.fixture
def adapter(monkeypatch):
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    instance = SO101Adapter(camera_width=96, camera_height=96, horizon=300)
    instance.reset("so101_fruitgym_harvest", 0)
    first = instance.native_env._observation()
    monkeypatch.setattr(instance.native_env, "_observation", lambda: first)
    yield instance
    instance.close()


def test_effector_geometry_changes_with_opening_without_moving_robot(adapter):
    before = adapter.get_robot_state()
    closed = adapter.get_gripper_geometry(0)
    opened = adapter.get_gripper_geometry(1)
    assert closed["pad_center_separation_m"] < 0.01
    assert opened["pad_center_separation_m"] > 0.09
    assert not np.allclose(closed["grasp_center_in_tcp_m"], opened["grasp_center_in_tcp_m"])
    assert adapter.current_time_s == before.timestamp_s
    assert np.array_equal(
        adapter.get_robot_state().joint_positions["primary"], before.joint_positions["primary"]
    )
    with pytest.raises(ValueError):
        adapter.get_gripper_geometry(2)


@pytest.mark.parametrize(
    "side_shift,yaw,valid",
    [(-0.001, -0.12, False), (0, 0, True), (0.001, 0.12, False), (0, -0.1, True), (0, 0.1, True)],
)
def test_mesh_primitive_accepts_hold_and_rejects_unstable_or_excessive_contacts(
    adapter, monkeypatch, side_shift, yaw, valid
):
    env = adapter.native_env
    # ENGINEERING FIXTURE: position the mesh at the robot's aperture to isolate
    # contact mechanics. No approach/harvest trajectory or task success claimed.
    env.sim.data._data.eq_active[env.fixture_id] = False
    monkeypatch.setattr(env, "_release_due", lambda: False)
    original_axes = env.sim.data.get_site_xmat("so101_gripperframe").copy()
    if valid:
        env.sim.data.qpos[env.qpos_indexes[0]] += yaw
        env.sim.data.ctrl[env.actuator_ids[0]] += yaw
    opening = 0.23
    low, high = env.action_spec
    env.sim.data.qpos[env.qpos_indexes[5]] = low[5] + opening * (high[5] - low[5])
    env.sim.data.ctrl[env.actuator_ids[5]] = env.sim.data.qpos[env.qpos_indexes[5]]
    env.sim.forward()
    geometry = adapter.get_gripper_geometry(opening)
    tcp = env.sim.data.get_site_xpos("so101_gripperframe")
    axes = env.sim.data.get_site_xmat("so101_gripperframe")
    address = int(env.model.jnt_qposadr[env.fruit_joint_id])
    relative = np.asarray(geometry["grasp_center_in_tcp_m"]) + [0, side_shift, 0]
    env.sim.data.qpos[address : address + 3] = tcp + axes @ relative
    env.sim.data.qpos[address + 3 : address + 7] = [np.cos(yaw / 2), 0, 0, np.sin(yaw / 2)]
    if valid:
        import mujoco

        quaternion = np.empty(4)
        mujoco.mju_mat2Quat(quaternion, (axes @ original_axes.T).ravel())
        env.sim.data.qpos[address + 3 : address + 7] = quaternion
    env.sim.forward()
    for _ in range(300):
        env.sim.step()
        env._after_physics_step()
    assert env.ready_step is None and not env.early_closure
    if valid:
        assert env.grasp_time is not None and env.longest_contact_duration_s >= 0.5
        assert env._bilateral_witness() is not None
        assert not env.limit_violations and not env.forbidden_contacts
        assert max(env.peak_finger_force.values()) < 12
    else:
        assert env.grasp_time is None
        assert env.longest_contact_duration_s < 0.5 or env.limit_violations
    assert not adapter.check_success()  # no harvest/carry/deposit


def test_transient_force_between_control_reads_stops_and_is_returned(adapter, monkeypatch):
    env = adapter.native_env
    original = env._after_physics_step
    original_sensor = adapter.get_finger_contacts
    count = 0

    def sensor_fixture():
        nonlocal count
        original()
        count += 1

    def read_sensor():
        reading = dict(original_sensor())
        if count == 2:
            reading["fixed"] = {"normal_force_n": 6.5, "contact_count": 1, "contacts": []}
        return reading

    monkeypatch.setattr(env, "_after_physics_step", sensor_fixture)
    monkeypatch.setattr(adapter, "get_finger_contacts", read_sensor)
    result = adapter.command_gripper(0.7, force_limit_n=3)
    assert result.ok and result.steps_executed == 1
    assert result.diagnostics["stop_reason"] == "force_limit"
    assert result.diagnostics["peak_finger_forces_n"]["fixed"] == 6.5
    assert not result.diagnostics["target_reached"]
    assert not any(env.current_contacts.values())  # spike is gone at action return


def test_terminal_violation_prevents_following_commands(adapter, monkeypatch):
    env = adapter.native_env
    original = env._after_physics_step

    def collision_fixture():
        original()
        env.forbidden_contacts.add(("robot_fixture_link", "obstacle_fixture"))

    monkeypatch.setattr(env, "_after_physics_step", collision_fixture)
    result = adapter.command_gripper(0.7)
    assert not result.ok and result.truncated
    elapsed = env.elapsed
    following = adapter.command_gripper(1)
    assert not following.ok and env.elapsed == elapsed


def test_public_point_obstacle_check_and_nominal_self_clearance(adapter):
    state = adapter.get_robot_state()
    joints = state.joint_positions["primary"]
    assert adapter.check_joint_path([joints], [])["path_clear"]
    env = adapter.native_env
    geom = env.fingers["fixed"]
    # Supply a sample as a perceived obstacle. The checker only receives points.
    mesh = env.model.geom_dataid[geom]
    start, count = env.model.mesh_vertadr[mesh], env.model.mesh_vertnum[mesh]
    center = env.model.mesh_vert[start : start + count].mean(axis=0)
    point = (center @ env.sim.data.geom_xmat[geom].reshape(3, 3).T + env.sim.data.geom_xpos[geom]).tolist()
    assert not adapter.check_joint_path([joints], [point])["path_clear"]
    # Permitting fruit contact must not permit the body of a finger to hit it.
    assert not adapter.check_joint_path([joints], [point], finger_contact_mask=[True])["path_clear"]


def test_path_checker_samples_jaw_sweep_even_with_stationary_arm(adapter):
    joints = adapter.get_robot_state().joint_positions["primary"]
    result = adapter.check_joint_path([joints, joints], [], gripper_positions=[1.0, 0.8])
    assert result["path_clear"], result
    assert result["sample_count"] >= 11


def test_path_checker_rejects_mismatched_jaw_path(adapter):
    joints = adapter.get_robot_state().joint_positions["primary"]
    with pytest.raises(ValueError, match="one finite gripper opening"):
        adapter.check_joint_path([joints, joints], [], gripper_positions=[0.5])
