"""Configure local, task-independent SO-101 planning providers."""

from cap_harness.api import CapApi
from cap_harness.artifacts import TracedProvider
from cap_harness.contracts import MotionStrategy
from cap_harness.so101.planning import SO101TrajectoryPlanner
from cap_harness.so101.providers import SO101IKProvider


def make_api(adapter, *, recorder=None):
    """Build the same shared API used by recorded SO-101 runs."""

    def traced(provider):
        return TracedProvider(provider, recorder, "so101") if recorder is not None else provider

    return CapApi(
        adapter,
        ik_providers={"so101": traced(SO101IKProvider())},
        trajectory_planning_providers={
            "so101": traced(
                SO101TrajectoryPlanner(
                    dt_s=adapter.control_period_s,
                    state_provider=adapter.get_robot_state,
                )
            ),
        },
        default_motion_strategy=MotionStrategy(ik_solver="so101", trajectory_planner="so101"),
        recorder=recorder,
    )
