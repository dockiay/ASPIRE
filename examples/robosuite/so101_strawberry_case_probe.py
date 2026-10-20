# Integration probe only: observes the registered case and holds the arm open.
# task_success=false is expected: this program does not attempt harvesting.
initial = get_robot_state()
lesson = so101.get_task_metadata()["lesson"]
assert initial.gripper_positions["primary"] > .97
for tick_index in range(8):
    motion = step(RobotAction({"primary": ArmCommand(
        "joint_position", initial.joint_positions["primary"],
        gripper_position=1.0, embodiment="so101")}))
    assert motion.ok and not motion.truncated
result = {"kind": "case_initialization_probe", "lesson": lesson,
          "finger_contacts": so101.get_finger_contacts()}
