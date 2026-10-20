# Generated-program example: runtime-injected tools, no simulator access.
initial = get_robot_state()
assert initial.embodiment == "so101"
contacts = so101.get_finger_contacts()
assert contacts["timestamp_s"] == initial.timestamp_s

closed = so101.command_gripper(0.75, duration_s=2, speed=0.5)
assert closed.ok and closed.diagnostics["completed"]

target = initial.joint_positions["primary"].copy()
target[0] += 0.05
segment = so101.command_joints(
    target,
    gripper_position=0.5,
    gripper_speed=0.25,
    minimum_duration_s=0.1,
    duration_s=2,
)
assert segment.ok and segment.diagnostics["completed"]
assert segment.diagnostics["gripper_setpoint_preserved"]
retained = segment.diagnostics["retained_gripper_setpoint"]

# Shared motion must preserve the issued jaw setpoint from the extension.
returned = move_to_joints(initial.joint_positions["primary"])
assert returned.ok
measured = get_robot_state()
assert abs(measured.gripper_positions["primary"] - retained) < 0.025

opened = so101.command_gripper(1.0, duration_s=2, speed=0.5)
assert opened.ok and opened.diagnostics["completed"]
result = {
    "scope": "supervised software control; one-joint example, not the complete control task",
    "stop_reason": segment.diagnostics["stop_reason"],
    "requested_jaw_position": 0.5,
    "retained_jaw_setpoint": retained,
    "measured_jaw_after_shared_motion": measured.gripper_positions["primary"],
    "final_jaw_position": get_robot_state().gripper_positions["primary"],
}
