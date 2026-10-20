"""Discovery for the SO-101 simulation control task."""

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


class SO101TaskRegistry(RobosuiteTaskRegistry):
    def __init__(self) -> None:
        super().__init__((SO101_CONTROL,))
