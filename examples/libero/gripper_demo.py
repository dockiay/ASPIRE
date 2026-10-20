# Simulator-only example: open, close, and reopen the gripper.
# Uses the public API injected by cap-harness; no model services are needed.
opened = open_gripper()
assert opened.ok, "Gripper did not open"
open_position = get_robot_state().gripper_positions["primary"]

closed = close_gripper()
assert closed.ok, "Gripper did not close"
closed_position = get_robot_state().gripper_positions["primary"]
assert open_position - closed_position > 0.5, "No clear gripper motion observed"

reopened = open_gripper()
assert reopened.ok, "Gripper did not reopen"
reopened_position = get_robot_state().gripper_positions["primary"]
assert reopened_position - closed_position > 0.5, "Gripper did not visibly reopen"

result = {
    "kind": "gripper_demo",
    "open_position": open_position,
    "closed_position": closed_position,
    "reopened_position": reopened_position,
}
