# ASPIRE public-API lesson: known coordinates, an open gripper, approach and retreat.
# These joint waypoints were authored for this fixed scene; they are not a planner.
initial = get_robot_state()
assert initial.embodiment == "so101"
lesson = so101.get_task_metadata()["lesson"]
target_position = lesson["target_position_m"]
home = initial.joint_positions["primary"].copy()
preapproach = [0, -1.219625, 0.744906, 0.474719, 0]
approach = [0, -0.783978, 0.584575, 0.199403, 0]


def distance(a, b):
    return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5


def hold(joints):
    # Advance real simulation ticks while retaining the target, rather than sleeping.
    for tick_index in range(10):
        tick = step(
            RobotAction(
                {
                    "primary": ArmCommand(
                        "joint_position", joints, gripper_position=1.0, embodiment="so101"
                    )
                }
            )
        )
        assert tick.ok and not tick.truncated, "Hold interrupted"


assert initial.gripper_positions["primary"] > 0.97
print("1. Orientar el brazo hacia la fresa, manteniendo distancia.")
assert move_to_joints(preapproach, tolerance=0.003, max_steps=100).ok
print("2. Aproximar la pinza abierta al marcador azul y mantener la posicion.")
assert move_to_joints(approach, tolerance=0.003, max_steps=100).ok
hold(approach)
reached = get_robot_state()
approach_error = distance(reached.end_effector_poses["primary"].position_m, target_position)
assert approach_error <= lesson["position_tolerance_m"], "Approach position missed"
assert reached.gripper_positions["primary"] > 0.97
print("3. Retirar la pinza y volver a la postura inicial.")
assert move_to_joints(preapproach, tolerance=0.003, max_steps=100).ok
assert move_to_joints(home, tolerance=0.003, max_steps=100).ok
hold(home)
final = get_robot_state()
retreat_error = distance(
    final.end_effector_poses["primary"].position_m, initial.end_effector_poses["primary"].position_m
)
assert retreat_error <= lesson["position_tolerance_m"], "Retreat position missed"
result = {
    "kind": "so101_strawberry_approach",
    "target_source": lesson["target_source"],
    "approach_error_m": float(approach_error),
    "retreat_error_m": float(retreat_error),
    "final_gripper_opening": final.gripper_positions["primary"],
}
