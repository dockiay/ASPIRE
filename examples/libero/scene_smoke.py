# First simulator check: record one second of the initial scene at 20 Hz.
# Run through cap-harness, which injects the public API and contract types.
# This program makes no perception, grasp, IK, or planning service calls.
initial = get_robot_state()
action = RobotAction(
    arms={
        "primary": ArmCommand(
            embodiment=initial.embodiment,
            mode="joint_position",
            target=initial.joint_positions["primary"],
            gripper_position=initial.gripper_positions["primary"],
        )
    }
)
steps = 0
for tick in range(20):
    tick_result = step(action)
    assert tick_result.ok, "Simulator step failed"
    steps = steps + 1
    if tick_result.terminated or tick_result.truncated:
        break

result = {"kind": "scene_smoke", "steps_recorded": steps}
