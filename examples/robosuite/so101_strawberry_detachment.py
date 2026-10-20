# Single-fruit ASPIRE experiment: bending and pulling with a load-released proxy.
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
assert held["fixed"]["normal_force_n"] > 0.1
assert held["moving"]["normal_force_n"] > 0.1
# Fixed waypoints prepared offline: 10..70 deg bend about the calyx,
# then 1, 2, 4, 8, 15 mm withdrawal along the rotated fruit axis.
# The simulator measures actual fruit rotation and junction load independently.
bend_and_pull_points = [[0.050501236869647435, -0.23418925132636892, 0.20689938766914437, 0.02728986365722455, 1.7453292519943295],
    [0.061736676787538206, -0.23378793453339305, 0.18247944375003283, 0.05130849078336022, 1.9198621771937625],
    [0.07108379808033943, -0.23209207965531525, 0.15232839101869577, 0.07976368863661948, 2.0943951023931953],
    [0.07825568992175568, -0.22859295210637898, 0.11673063820303413, 0.11186231390334485, 2.2689280275926285],
    [0.08303120907620867, -0.22289634678232265, 0.07616864658870032, 0.14672770019362233, 2.443460952792061],
    [0.08526257168741583, -0.21478648081668122, 0.03136334735817046, 0.18342313345851077, 2.617993877991494],
    [0.08488057073828648, -0.20427246516951095, -0.01669600002942625, 0.2209684651989372, 2.792526803190927],
    [0.08777237746641192, -0.2057685017073237, -0.012528121063908335, 0.21829662277123202, 2.792526803190927],
    [0.09066492027596877, -0.20727904607927158, -0.008349123083346495, 0.21562816916261807, 2.792526803190927],
    [0.09645231332772763, -0.21034380037530864, 4.224621274993622E-05, 0.21030155416255872, 2.792526803190927],
    [0.10803702684528048, -0.21664902240989592, 0.016958604829337337, 0.19969041758055858, 2.792526803190927],
    [0.12834632160337106, -0.22825379242736404, 0.046991824357744905, 0.18126196806961914, 2.792526803190927]]
grip = {"opening": 0.2445}


def loaded_tick(joints):
    sensors = so101.get_finger_contacts()
    forces = [sensors[side]["normal_force_n"] for side in ["fixed", "moving"]]
    assert max(forces) < lesson["maximum_finger_force_n"], "Simulation force bound exceeded"
    if min(forces) < 2.5:
        grip["opening"] -= 0.00025
    elif max(forces) > 6.0:
        grip["opening"] += 0.0001
    grip["opening"] = min(0.26, max(0.20, grip["opening"]))
    tick(joints, grip["opening"])


print("4. Inclinar alrededor del caliz: siete pasos hasta 70 grados nominales.")
previous = grasp
for point_index in range(len(bend_and_pull_points)):
    destination = bend_and_pull_points[point_index]
    if point_index == 7:
        print("5. Retirar en el eje del fruto: hasta 15 mm; liberacion por carga, sin reloj.")
    for tick_index in range(1, 31):
        fraction = tick_index / 30
        target = [previous[j] + fraction * (destination[j] - previous[j]) for j in range(5)]
        loaded_tick(target)
    previous = destination
print("6. Conservar el fruto en la pinza y registrar la evidencia fisica.")
for tick_index in range(100):
    loaded_tick(previous)
result = {
    "kind": "so101_strawberry_detachment",
    "final_normalized_opening": grip["opening"],
    "final_contact_sensors": so101.get_finger_contacts(),
    "junction": "load-released mechanical proxy; biological calibration pending",
}