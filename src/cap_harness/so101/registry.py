"""Learning tasks for the SO-101 simulation profile."""

from cap_harness.robosuite.registry import RobosuiteTaskMetadata, RobosuiteTaskRegistry

SO101_CONTROL = RobosuiteTaskMetadata(
    task_name="so101_control",
    environment="SO101Control",
    language=(
        "Move each of the five arm joints away from its initial position and return it, "
        "then close and reopen the gripper while keeping the arm at its initial pose."
    ),
    robots=("SO101",),
    camera_names=("agentview", "sideview"),
    family="so101",
)

SO101_STRAWBERRY_APPROACH = RobosuiteTaskMetadata(
    task_name="so101_strawberry_approach",
    environment="SO101StrawberryApproach",
    language=(
        "Keep the gripper open, approach the marked point in front of the strawberry, "
        "hold still for 0.25 seconds, then return to the initial arm pose and hold. "
        "Avoid robot self-contact and all robot contacts with the plant, fruit and work surface."
    ),
    robots=("SO101",),
    camera_names=("agentview", "sideview"),
    family="so101",
)


SO101_STRAWBERRY_GRASP_CONTACT = RobosuiteTaskMetadata(
    task_name="so101_strawberry_grasp_contact",
    environment="SO101StrawberryGraspContact",
    language=(
        "Approach the attached strawberry with the gripper open. Establish opposing "
        "fingertip contacts on both sides for 0.5 seconds within the declared simulation "
        "force and penetration limits. Reopen, release contact and return to the initial "
        "arm pose. Avoid all other robot contacts with the plant or surface and self-contact."
    ),
    robots=("SO101",),
    camera_names=("agentview", "sideview"),
    family="so101",
)


SO101_STRAWBERRY_RETENTION = RobosuiteTaskMetadata(
    task_name="so101_strawberry_retention",
    environment="SO101StrawberryRetention",
    language=(
        "Grasp the strawberry with opposing fingertip contacts before the timed fixture "
        "releases at 8 seconds. Retain the free fruit under gravity for 2 continuous seconds "
        "with both fingers, within 8 mm relative slip and the declared force limits. "
        "Keep holding at the end. No other fruit support or forbidden robot contacts."
    ),
    robots=("SO101",),
    camera_names=("agentview", "sideview"),
    family="so101",
)

SO101_STRAWBERRY_RETENTION_TORSION = RobosuiteTaskMetadata(
    task_name="so101_strawberry_retention_torsion",
    environment="SO101StrawberryRetentionTorsion",
    language=SO101_STRAWBERRY_RETENTION.language
    + (
        " This variant enables uncalibrated torsional contact friction; "
        "success is conditional on that contact-model assumption."
    ),
    robots=("SO101",),
    camera_names=("agentview", "sideview"),
    family="so101",
)


SO101_STRAWBERRY_TRANSPORT = RobosuiteTaskMetadata(
    task_name="so101_strawberry_transport",
    environment="SO101StrawberryTransport",
    language=(
        "Grasp the strawberry and retain it for 2 seconds after the timed fixture release. "
        "Carry it at least 15 cm to the declared container while preserving the grasp. "
        "Hold over the container for 0.25 seconds, open to release, and withdraw the open "
        "gripper. Leave the entire fruit inside, supported by the base and stable for "
        "1 second. Avoid all robot collisions and fruit supports outside the container. "
        "This lesson uses uncalibrated torsional contact friction."
    ),
    robots=("SO101",),
    camera_names=("agentview", "sideview"),
    family="so101",
)


SO101_STRAWBERRY_DETACHMENT = RobosuiteTaskMetadata(
    task_name="so101_strawberry_detachment",
    environment="SO101StrawberryDetachment",
    language=(
        "Grasp one strawberry, bend and withdraw to load its releasable junction. "
        "The mechanical proxy releases only under its declared measured load and "
        "relative-motion conditions, never on a timer. Retain the free fruit for "
        "2 seconds with both original fingertips and no other support. Avoid all "
        "robot collisions. The junction and contacts are not biologically calibrated."
    ),
    robots=("SO101",),
    camera_names=("agentview", "sideview"),
    family="so101",
)


SO101_STRAWBERRY_DETACHMENT_CASES = RobosuiteTaskMetadata(
    task_name="so101_strawberry_detachment_cases",
    environment="SO101StrawberryDetachmentCases",
    language=(
        "Grasp, bend and withdraw one strawberry, then retain it free for 2 seconds. "
        "Geometry is fixed; junction load and compliance vary by registered case seed. "
        "Use the available observations; hidden release parameters are evaluator-only. "
        "Avoid collisions, excess forces, slipping and other supports. "
        "These synthetic cases are not biologically calibrated."
    ),
    robots=("SO101",),
    camera_names=("agentview", "sideview"),
    family="so101",
)


SO101_FRUITGYM_HARVEST = RobosuiteTaskMetadata(
    task_name="so101_fruitgym_harvest",
    environment="SO101FruitGymHarvest",
    language=(
        "Harvest the ripe strawberry from the FruitGym plant: grasp with both fingertips, "
        "mechanically release its junction while preserving the grasp, and retain it free for 2 seconds (carry may overlap). "
        "Carry the same fruit at least 15 cm to the container, hold over it for 0.25 seconds, "
        "release, and withdraw the open gripper. Leave the whole fruit stably supported inside "
        "for 1 second. Avoid collisions, other fruit supports, slipping and excessive force. "
        "Rigid foliage and the release proxy are not biologically calibrated."
    ),
    robots=("SO101",),
    camera_names=("agentview", "sideview"),
    family="so101",
    horizon=1200,
)


class SO101TaskRegistry(RobosuiteTaskRegistry):
    def __init__(self) -> None:
        super().__init__(
            tasks=(
                SO101_CONTROL,
                SO101_STRAWBERRY_APPROACH,
                SO101_STRAWBERRY_GRASP_CONTACT,
                SO101_STRAWBERRY_RETENTION,
                SO101_STRAWBERRY_RETENTION_TORSION,
                SO101_STRAWBERRY_TRANSPORT,
                SO101_STRAWBERRY_DETACHMENT,
                SO101_STRAWBERRY_DETACHMENT_CASES,
                SO101_FRUITGYM_HARVEST,
            )
        )
