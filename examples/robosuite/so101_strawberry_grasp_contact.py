# ASPIRE public API: qualify a two-finger grasp against an attached, rigid fruit.
# Virtual tactile sensors supply simulated forces; the real stock SO-101 has none.
initial = get_robot_state()
lesson = so101.get_task_metadata()["lesson"]
home = initial.joint_positions["primary"].copy()
preapproach = [0.04939912, -0.80346568, 0.66143451, 0.14203117, 1.57079633]
grasp = [0.03954880, -0.23135522, 0.22131879, 0.01003643, 1.57079633]


def tick(joints, opening):
    motion = step(
        RobotAction(
            {
                "primary": ArmCommand(
                    "joint_position", joints, gripper_position=opening, embodiment="so101"
                )
            }
        )
    )
    assert motion.ok and not motion.truncated, "Motion interrupted"


def hold(joints, opening, ticks):
    for tick_index in range(ticks):
        tick(joints, opening)


def interpolate(start, end, opening, ticks):
    for tick_index in range(1, ticks + 1):
        fraction = tick_index / ticks
        target = [start[j] + fraction * (end[j] - start[j]) for j in range(5)]
        tick(target, opening)


print("1. Orientar la pinza de lado y aproximarse con los dedos abiertos.")
assert initial.gripper_positions["primary"] > 0.97
assert move_to_joints(preapproach, tolerance=0.003, max_steps=100).ok
interpolate(preapproach, grasp, 1.0, 40)
hold(grasp, 1.0, 12)
print("2. Cerrar por etapas y detener el cierre al detectar ambos dedos.")
for opening in [0.4, 0.3, 0.26]:
    hold(grasp, opening, 10)
selected_opening = None
for close_index in range(1, 51):
    opening = 0.26 - close_index * 0.0005
    tick(grasp, opening)
    sensors = so101.get_finger_contacts()
    assert (
        max(sensors["fixed"]["normal_force_n"], sensors["moving"]["normal_force_n"])
        < lesson["maximum_finger_force_n"]
    ), "Simulation force bound exceeded"
    if sensors["fixed"]["normal_force_n"] > 0.1 and sensors["moving"]["normal_force_n"] > 0.1:
        selected_opening = opening
        break
assert selected_opening is not None, "Both fingers did not contact within the bounded closure"
print("3. Mantener el contacto y comprobar las lecturas simuladas.")
hold(grasp, selected_opening, 14)
held = so101.get_finger_contacts()
assert held["fixed"]["normal_force_n"] > 0.1
assert held["moving"]["normal_force_n"] > 0.1
print("4. Abrir, liberar los contactos y volver al inicio.")
assert open_gripper().ok
interpolate(grasp, preapproach, 1.0, 30)
assert move_to_joints(home, tolerance=0.003, max_steps=100).ok
hold(home, 1.0, 10)
released = so101.get_finger_contacts()
assert released["fixed"]["contact_count"] == 0
assert released["moving"]["contact_count"] == 0
result = {
    "kind": "so101_strawberry_grasp_contact",
    "selected_normalized_opening": selected_opening,
    "held_contact_sensors": held,
    "released_contact_sensors": released,
    "fruit_condition": "rigid and attached; detached retention not tested",
}
