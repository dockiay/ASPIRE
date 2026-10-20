"""Absolute five-axis arm targets and an independent normalized gripper."""

from __future__ import annotations

import numpy as np

from cap_harness.contracts import RobotAction, RobotState


class SO101ActionCodec:
    def __init__(self, bounds: tuple[np.ndarray, np.ndarray]) -> None:
        low, high = (np.asarray(value, dtype=float).copy() for value in bounds)
        if low.shape != (6,) or high.shape != (6,) or not np.isfinite([low, high]).all():
            raise ValueError("SO-101 requires six finite actuator bounds")
        if np.any(low >= high):
            raise ValueError("SO-101 actuator bounds must be strictly ordered")
        self.low, self.high = low, high

    def encode(
        self,
        action: RobotAction,
        current_state: RobotState,
        *,
        joint_targets: dict[str, np.ndarray] | None = None,
        gripper_targets: dict[str, float] | None = None,
    ) -> np.ndarray:
        if action.embodiment != "so101" or current_state.embodiment != "so101":
            raise ValueError("SO-101 codec requires SO-101 contracts")
        if set(action.arms) != {"primary"} or set(current_state.arms) != {"primary"}:
            raise ValueError("SO-101 has only the primary arm")
        command = action.arms.get("primary")
        joints = (joint_targets or {}).get("primary", current_state.joint_positions["primary"])
        opening = (gripper_targets or {}).get("primary", current_state.gripper_positions["primary"])
        if command is not None:
            joints = command.target
            if command.gripper_position is not None:
                opening = command.gripper_position
        if np.any(joints < self.low[:5]) or np.any(joints > self.high[:5]):
            raise ValueError("SO-101 arm target exceeds actuator limits")
        if not np.isfinite(opening) or not 0 <= opening <= 1:
            raise ValueError("SO-101 gripper opening must be in [0, 1]")
        angle = self.low[5] + opening * (self.high[5] - self.low[5])
        return np.append(joints, angle)
