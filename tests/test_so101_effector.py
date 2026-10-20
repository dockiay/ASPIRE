"""Native robot geometry fixtures; no task object or harvest policy."""

import numpy as np
import pytest

from cap_harness.so101.adapter import SO101Adapter


@pytest.fixture
def adapter(monkeypatch):
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    instance = SO101Adapter(camera_width=96, camera_height=96, horizon=300)
    instance.reset("so101_control", 0)
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


def test_public_point_obstacle_check_and_nominal_self_clearance(adapter):
    state = adapter.get_robot_state()
    joints = state.joint_positions["primary"]
    assert adapter.check_joint_path([joints], [])["path_clear"]
    env = adapter.native_env
    from cap_harness.so101.sensing import finger_geom_ids

    geom = finger_geom_ids(env.model)["fixed"]
    # Supply a sample as a perceived obstacle. The checker only receives points.
    mesh = env.model.geom_dataid[geom]
    start, count = env.model.mesh_vertadr[mesh], env.model.mesh_vertnum[mesh]
    center = env.model.mesh_vert[start : start + count].mean(axis=0)
    point = (
        center @ env.sim.data.geom_xmat[geom].reshape(3, 3).T + env.sim.data.geom_xpos[geom]
    ).tolist()
    assert not adapter.check_joint_path([joints], [point])["path_clear"]
    # Permitting target contact must not permit the body of a finger to hit it.
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
