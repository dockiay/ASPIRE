# ruff: noqa: F821
# Public observations -> estimated fruit -> robot-only IK -> open standoff.
localized = so101.localize_ripe_fruit()
assert localized["ok"] and localized["frame"] == get_robot_state().base_frame
plan = so101.plan_open_approach(localized["point_m"], clearance_m=0.065)
assert plan["ok"]
for waypoint in plan["waypoints"]:
    for tick_index in range(2):
        motion = step(
            RobotAction(
                {
                    "primary": ArmCommand(
                        "joint_position", waypoint, gripper_position=1.0, embodiment="so101"
                    )
                }
            )
        )
        assert motion.ok and not motion.truncated
settled = move_to_joints(plan["joint_target"], tolerance=0.004, max_steps=80)
assert settled.ok
for tick_index in range(8):
    motion = step(
        RobotAction(
            {
                "primary": ArmCommand(
                    "joint_position", plan["joint_target"], gripper_position=1.0, embodiment="so101"
                )
            }
        )
    )
    assert motion.ok and not motion.truncated
final = get_robot_state()
result = {
    "scope": "visual open approach only; no grasp or harvest",
    "localization": localized,
    "plan": plan,
    "final_tcp_m": list(final.end_effector_poses["primary"].position),
    "final_opening": final.gripper_positions["primary"],
}
