"""Render/check the imported scene while holding runtime-measured robot state."""
# ruff: noqa: F821

state = get_robot_state()
joints = state.joint_positions["primary"]
opening = state.gripper_positions["primary"]
for tick_index in range(8):
    motion = step(
        RobotAction(
            {
                "primary": ArmCommand(
                    "joint_position", joints, gripper_position=opening, embodiment="so101"
                )
            }
        )
    )
    assert motion.ok and not motion.truncated
result = {"scope": "scene integration probe; no harvesting attempted"}
