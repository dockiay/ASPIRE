# ASPIRE public-API program. The runtime injects these functions; no simulator imports.
initial = get_robot_state()
assert initial.embodiment == "so101"
assert len(initial.joint_positions["primary"]) == 5
metadata = so101.get_controller_metadata()
checks = []

# Move each joint and return, checking the measured state after each action.
for index in range(5):
    target = initial.joint_positions["primary"].copy()
    target[index] = target[index] + 0.18
    motion = move_to_joints(target, tolerance=0.005, max_steps=80)
    assert motion.ok, "Joint movement failed"
    measured = get_robot_state().joint_positions["primary"]
    error = float(max(abs(measured - target)))
    assert error <= 0.005
    returned = move_to_joints(initial.joint_positions["primary"], tolerance=0.005, max_steps=80)
    assert returned.ok, "Joint return failed"
    checks.append(
        {
            "joint": initial.joint_names["primary"][index],
            "target_rad": float(target[index]),
            "error_rad": error,
        }
    )

closed = close_gripper()
assert closed.ok, "Gripper close failed"
closed_position = get_robot_state().gripper_positions["primary"]
assert closed_position < 0.025

opened = open_gripper()
assert opened.ok, "Gripper open failed"
final = get_robot_state()
assert final.gripper_positions["primary"] > 0.975
assert float(max(abs(final.joint_positions["primary"] - initial.joint_positions["primary"]))) < 0.01

result = {
    "kind": "so101_aspire_control",
    "model_commit": metadata["model_commit"],
    "joint_checks": checks,
    "closed_position": closed_position,
    "opened_position": final.gripper_positions["primary"],
    "final_joint_error_rad": float(
        max(abs(final.joint_positions["primary"] - initial.joint_positions["primary"]))
    ),
}
