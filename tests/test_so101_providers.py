"""Shared pose IK integration against the official SO-101 model."""

from dataclasses import replace

import numpy as np
import pytest

from cap_harness.api import CapApi
from cap_harness.contracts import MotionStrategy, Pose
from cap_harness.geometry import matrix_to_pose
from cap_harness.so101.providers import SO101IKProvider


@pytest.fixture
def adapter():
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    from cap_harness.so101.adapter import SO101Adapter

    instance = SO101Adapter(camera_width=64, camera_height=64, horizon=100)
    instance.reset("so101_control", 0)
    yield instance
    instance.close()


def pose_for(provider, joints):
    position, rotation = provider.robot.forward(joints)
    transform = np.eye(4)
    transform[:3, :3] = rotation
    transform[:3, 3] = position
    return matrix_to_pose(transform, frame="so101_base")


def test_shared_ik_recovers_multiple_robot_poses_without_moving_live_arm(adapter):
    provider = SO101IKProvider()
    api = CapApi(
        adapter,
        ik_providers={"so101": provider},
        default_motion_strategy=MotionStrategy(ik_solver="so101"),
    )
    initial = adapter.get_robot_state()
    for offset in ([0.08, -0.10, 0.08, 0.02, -0.10], [-0.10, 0.08, -0.08, 0.04, 0.12]):
        target = pose_for(provider, initial.joint_positions["primary"] + offset)
        answer = api.solve_ik(target)
        assert answer.ok, answer
        position, _ = provider.robot.forward(answer.joint_positions)
        assert np.linalg.norm(position - target.position) < 0.004
        plan = api.plan_motion(target)
        assert plan.ok and plan.trajectory.collision_aware is False
        assert plan.trajectory.embodiment == "so101"
    current = adapter.get_robot_state()
    np.testing.assert_array_equal(
        initial.joint_positions["primary"], current.joint_positions["primary"]
    )
    assert current.timestamp_s == initial.timestamp_s


def test_ik_rejects_unreachable_pose_and_wrong_frame(adapter):
    provider = SO101IKProvider()
    state = adapter.get_robot_state()
    bad = Pose([5, 5, 5], [1, 0, 0, 0], "so101_base")
    assert not provider.solve_ik(bad, state).ok
    assert not provider.solve_ik(replace(bad, frame="world"), state).ok


def test_native_run_wires_shared_providers_and_measured_motion(tmp_path):
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    from cap_harness.run import run_program

    program = tmp_path / "public.py"
    program.write_text(
        "state = get_robot_state()\n"
        "target = state.end_effector_poses['primary']\n"
        "ik = solve_ik(target)\n"
        "assert ik.ok, str(ik.error)\n"
        "motion = move_to_pose(target, max_steps=20)\n"
        "assert motion.ok, str(motion.error)\n"
        "result = {'steps': motion.steps_executed}\n"
    )
    outcome = run_program(
        benchmark="so101",
        suite="so101_control",
        task_id=0,
        seed=0,
        program_path=program,
        output_root=tmp_path / "run",
        max_steps=30,
        camera_width=1280,
        camera_height=960,
        capture_videos=False,
    )
    assert outcome.program_ok, outcome


def test_full_task_public_metadata_omits_solver_targets():
    from cap_harness.so101.harvest import SO101FruitGymHarvestEnvironment

    metadata = SO101FruitGymHarvestEnvironment.lesson_metadata()
    for key in (
        "fruit_center_m",
        "fruit_center_in_tool_m",
        "container_center_xy_m",
        "container_inner_half_size_m",
        "container_floor_z_m",
        "container_rim_z_m",
        "release_fruit_center_z_m",
        "bent_load_threshold_n",
    ):
        assert key not in metadata
