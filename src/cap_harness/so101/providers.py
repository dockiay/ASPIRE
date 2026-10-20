"""Task-independent five-axis IK using public robot state and robot geometry."""

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from cap_harness.contracts import IKResult, Pose, RobotState
from cap_harness.errors import ApiError, ErrorCode
from cap_harness.so101.kinematics import RobotKinematics


class SO101IKProvider:
    """Numerical five-axis pose IK against the official robot-only model."""

    def __init__(self):
        self.robot = RobotKinematics()

    def _valid_state(self, state, arm):
        names = tuple(self.robot.model.joint(int(index)).name for index in self.robot.joints[:5])
        return (
            isinstance(state, RobotState)
            and state.embodiment == "so101"
            and state.base_frame == "so101_base"
            and state.arms == ("primary",)
            and arm == "primary"
            and tuple(state.joint_names[arm]) == names
        )

    def solve_ik(self, target_pose, state, *, arm="primary"):
        def failure(code, message, **diagnostics):
            return IKResult(
                ok=False,
                arm=arm,
                embodiment="so101",
                error=ApiError(code, message),
                diagnostics=diagnostics,
            )

        if not self._valid_state(state, arm):
            return failure(
                ErrorCode.INVALID_REQUEST, "State must match SO-101 base, arm and joint order"
            )
        if not isinstance(target_pose, Pose):
            return failure(ErrorCode.INVALID_REQUEST, "Provide a Pose in so101_base")
        if target_pose.frame != state.base_frame or state.base_frame != "so101_base":
            return failure(ErrorCode.INVALID_REQUEST, "Pose must use so101_base")
        target = target_pose.as_matrix()
        opening = state.gripper_positions[arm]
        seed = state.joint_positions[arm]
        lower, upper = self.robot.low[:5] + 0.001, self.robot.high[:5] - 0.001

        def errors(joints):
            position, axes = self.robot.forward(joints, opening)
            rotation = Rotation.from_matrix(target[:3, :3].T @ axes).as_rotvec()
            return position - target[:3, 3], rotation

        def residual(joints):
            translation, rotation = errors(joints)
            return np.concatenate((translation, 0.05 * rotation))

        fit = least_squares(
            residual,
            np.clip(seed, lower, upper),
            bounds=(lower, upper),
            max_nfev=240,
            ftol=1e-10,
            xtol=1e-10,
            gtol=1e-10,
        )
        translation, rotation = errors(fit.x)
        diagnostics = {
            "position_error_m": float(np.linalg.norm(translation)),
            "orientation_error_rad": float(np.linalg.norm(rotation)),
            "robot_commit": self.robot.commit,
            "collision_aware": False,
            "scope": "robot-only five-axis pose IK; no task or obstacle geometry",
        }
        # Five axes cannot realize every six-dimensional pose. Never silently
        # discard the requested orientation to make an unreachable goal pass.
        if (
            not fit.success
            or diagnostics["position_error_m"] > 0.004
            or diagnostics["orientation_error_rad"] > np.deg2rad(5)
        ):
            return failure(
                ErrorCode.IK_FAILED,
                "Requested pose is not reachable within 4 mm / 5 degrees",
                **diagnostics,
            )
        return IKResult(
            ok=True,
            joint_positions=fit.x,
            arm=arm,
            embodiment="so101",
            diagnostics=diagnostics,
        )

    def solve_point_axis_ik(
        self,
        point_in_tool_m,
        target_point_m,
        axis_in_tool,
        target_axis,
        state,
        *,
        frame="so101_base",
        arm="primary",
        seed_joints=None,
    ):
        """Constrain a tool-fixed point and direction; leave axial twist free.

        All geometry is supplied by the caller. This robot-only calculation
        neither moves the arm nor checks scene contacts or path clearance.
        """

        def failure(code, message, **diagnostics):
            return IKResult(
                ok=False,
                arm=arm,
                embodiment="so101",
                error=ApiError(code, message),
                diagnostics=diagnostics,
            )

        if not self._valid_state(state, arm):
            return failure(
                ErrorCode.INVALID_REQUEST, "State must match SO-101 base, arm and joint order"
            )
        if frame != "so101_base" or state.base_frame != frame:
            return failure(ErrorCode.INVALID_REQUEST, "Targets must use so101_base")
        try:
            point, target, axis, direction = [
                np.asarray(value, dtype=float)
                for value in (point_in_tool_m, target_point_m, axis_in_tool, target_axis)
            ]
            if any(
                value.shape != (3,) or not np.isfinite(value).all()
                for value in (point, target, axis, direction)
            ):
                raise ValueError("Points and axes must have three finite coordinates")
            if np.linalg.norm(axis) < 1e-12 or np.linalg.norm(direction) < 1e-12:
                raise ValueError("Axis directions must be nonzero")
            axis = axis / np.linalg.norm(axis)
            direction = direction / np.linalg.norm(direction)
            seed = np.asarray(
                state.joint_positions[arm] if seed_joints is None else seed_joints,
                dtype=float,
            )
            if seed.shape != (5,) or not np.isfinite(seed).all():
                raise ValueError("Seed must have five finite joint positions")
        except (TypeError, ValueError) as error:
            return failure(ErrorCode.INVALID_REQUEST, str(error))
        opening = state.gripper_positions[arm]
        lower, upper = self.robot.low[:5] + 0.001, self.robot.high[:5] - 0.001

        def errors(joints):
            position, axes = self.robot.forward(joints, opening)
            return position + axes @ point - target, axes @ axis

        def residual(joints):
            translation, actual_axis = errors(joints)
            return np.concatenate((translation, 0.05 * (actual_axis - direction)))

        fit = least_squares(
            residual,
            np.clip(seed, lower, upper),
            bounds=(lower, upper),
            max_nfev=240,
            ftol=1e-10,
            xtol=1e-10,
            gtol=1e-10,
        )
        translation, actual_axis = errors(fit.x)
        diagnostics = {
            "point_error_m": float(np.linalg.norm(translation)),
            "axis_error_deg": float(np.degrees(np.arccos(np.clip(actual_axis @ direction, -1, 1)))),
            "robot_commit": self.robot.commit,
            "collision_aware": False,
            "scope": "robot-only point/direction IK; axial twist unconstrained; no scene or path checks",
        }
        if (
            not fit.success
            or diagnostics["point_error_m"] > 0.0005
            or diagnostics["axis_error_deg"] > 1.0
        ):
            return failure(
                ErrorCode.IK_FAILED,
                "Point/direction constraints not satisfied within 0.5 mm / 1 degree",
                **diagnostics,
            )
        return IKResult(
            ok=True,
            joint_positions=fit.x,
            arm=arm,
            embodiment="so101",
            diagnostics=diagnostics,
        )
