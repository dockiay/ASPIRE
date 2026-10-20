# Public ASPIRE tools only; geometry queries and planning do not move the robot.
initial = get_robot_state()
geometry = so101.get_gripper_geometry()
target = initial.joint_positions["primary"].copy()
target[0] += 0.15
outbound = plan_motion(target)
assert outbound.ok, str(outbound.error)
assert outbound.trajectory.collision_aware
assert get_robot_state().timestamp_s == initial.timestamp_s
moved = execute_trajectory(outbound.trajectory)
assert moved.ok, str(moved.error)

home_pose = initial.end_effector_poses["primary"]
home_axes = home_pose.as_matrix()[:3, :3]
constraints = so101.solve_point_axis_ik(
    [0, 0, 0], home_pose.position, [1, 0, 0], home_axes[:, 0]
)
assert constraints.ok, str(constraints.error)
returned = plan_motion(home_pose)
assert returned.ok, str(returned.error)
execution = execute_trajectory(returned.trajectory)
assert execution.ok, str(execution.error)
final = get_robot_state()
error = float(max(abs(final.joint_positions["primary"] - initial.joint_positions["primary"])))
assert error < 0.01
result = {
    "kind": "so101_planning",
    "model_commit": geometry["robot_commit"],
    "pad_center_separation_m": geometry["pad_center_separation_m"],
    "point_error_m": constraints.diagnostics["point_error_m"],
    "axis_error_deg": constraints.diagnostics["axis_error_deg"],
    "final_joint_error_rad": error,
    "outbound_diagnostics": outbound.diagnostics,
    "return_diagnostics": returned.diagnostics,
}
