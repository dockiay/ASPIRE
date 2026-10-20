"""Configure local, task-independent SO-101 planning providers."""

from cap_harness.api import CapApi
from cap_harness.artifacts import TracedProvider
from cap_harness.contracts import MotionStrategy
from cap_harness.so101.grasp_provider import SO101GraspProvider
from cap_harness.so101.planning import SO101TrajectoryPlanner
from cap_harness.so101.providers import SO101IKProvider


def make_api(adapter, *, segmentation_provider=None, recorder=None):
    """Build the same shared API used by recorded SO-101 runs."""

    def traced(provider, name="so101"):
        return TracedProvider(provider, recorder, name) if recorder is not None else provider

    ik = SO101IKProvider()

    return CapApi(
        adapter,
        segmentation_provider=segmentation_provider,
        grasp_providers={
            "so101-geometric": traced(
                SO101GraspProvider(state_provider=adapter.get_robot_state, ik_provider=ik),
                "so101-geometric",
            ),
        },
        ik_providers={"so101": traced(ik)},
        trajectory_planning_providers={
            "so101": traced(
                SO101TrajectoryPlanner(
                    dt_s=adapter.control_period_s,
                    state_provider=adapter.get_robot_state,
                )
            ),
        },
        default_motion_strategy=MotionStrategy(ik_solver="so101", trajectory_planner="so101"),
        default_grasp_backend="so101-geometric",
        recorder=recorder,
    )
