# ASPIRE public API: retain, carry and place a strawberry in a declared container.
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
    if sensors["fixed"]["normal_force_n"] > 1.0 and sensors["moving"]["normal_force_n"] > 1.0:
        selected_opening = opening
        break
assert selected_opening is not None, "Both fingers did not contact within the bounded closure"
print("3. Mantener el contacto y comprobar las lecturas simuladas.")
hold(grasp, selected_opening, 14)
held = so101.get_finger_contacts()
assert held["fixed"]["normal_force_n"] > 1.0
assert held["moving"]["normal_force_n"] > 1.0
print("4. Mantener la pinza mientras se libera la union de prueba a los 8 segundos.")
end_time = lesson["fixture_release_time_s"] + lesson["retention_seconds"] + 0.5
while get_robot_state().timestamp_s < end_time:
    tick(grasp, selected_opening)
    sensors = so101.get_finger_contacts()
    assert max(sensors["fixed"]["normal_force_n"], sensors["moving"]["normal_force_n"]) < lesson["maximum_finger_force_n"]
withdraw = [0.04939911517935302,-0.8034658886931585,0.661434806328321,0.14203108236483752,1.5707963267948966]
above_container = [0.709420080982545,-0.8052710062079392,0.6624013844505182,0.14286962175742102,1.5707963267948966]
deposit = [0.7094200813641541,-0.3927690024474478,1.2897257052634952,-0.8969567028160474,1.5707963267948966]
grip = {"opening": selected_opening}


def carry_tick(joints):
    sensors = so101.get_finger_contacts()
    forces = [sensors[side]["normal_force_n"] for side in ["fixed", "moving"]]
    assert max(forces) < lesson["maximum_finger_force_n"], "Simulation force bound exceeded"
    if min(forces) < 1.5:
        grip["opening"] -= 0.00025
    elif max(forces) > 3.0:
        grip["opening"] += 0.0001
    assert 0.20 <= grip["opening"] <= 0.26, "Bounded contact adjustment exhausted"
    tick(joints, grip["opening"])


def carry_hold(joints, ticks):
    for tick_index in range(ticks):
        carry_tick(joints)


def carry_interpolate(start, end, ticks):
    for tick_index in range(1, ticks + 1):
        fraction = tick_index / ticks
        target = [start[j] + fraction * (end[j] - start[j]) for j in range(5)]
        carry_tick(target)


print("5. Ajustar el agarre con sensores virtuales y transportar la fresa.")
carry_hold(grasp, 20)
carry_interpolate(grasp, withdraw, 60)
carry_interpolate(withdraw, above_container, 80)
carry_hold(above_container, 10)
print("6. Bajar sobre el centro del recipiente y estabilizar el agarre.")
carry_interpolate(above_container, deposit, 60)
carry_hold(deposit, 20)
carried = so101.get_finger_contacts()
assert carried["fixed"]["normal_force_n"] > 0.1
assert carried["moving"]["normal_force_n"] > 0.1
print("7. Abrir sobre el recipiente, esperar el apoyo y retirar la pinza abierta.")
assert open_gripper().ok
hold(deposit, 1.0, 30)
interpolate(deposit, above_container, 1.0, 60)
assert move_to_joints(home, tolerance=0.003, max_steps=100).ok
hold(home, 1.0, 40)
released = so101.get_finger_contacts()
assert released["fixed"]["contact_count"] == 0
assert released["moving"]["contact_count"] == 0
result = {
    "kind": "so101_strawberry_transport",
    "selected_normalized_opening": selected_opening,
    "final_transport_opening": grip["opening"],
    "carried_contact_sensors": carried,
    "released_contact_sensors": released,
    "fixture": "timed release; uncalibrated torsional friction",
    "container_center_xy_m": lesson["container_center_xy_m"],
}
