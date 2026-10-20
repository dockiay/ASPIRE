"""Open-gripper standoff heuristic for the strawberry lesson."""

import math

import numpy as np
from scipy.optimize import least_squares

from cap_harness.so101.kinematics import RobotKinematics as BaseKinematics


class RobotKinematics(BaseKinematics):
    def path_clear(self, waypoints):
        for joints in waypoints:
            self.forward(joints)
            if any(contact.dist <= 0 for contact in self.data.contact):
                return False
        return True

    def plan(self, state, fruit_point, clearance_m=0.065):
        point = np.asarray(fruit_point, dtype=float)
        if point.shape != (3,) or not np.isfinite(point).all():
            raise ValueError("Fruit point must be three finite coordinates in the robot base frame")
        if not np.isfinite(clearance_m) or not 0.055 <= clearance_m <= 0.12:
            raise ValueError("Open approach standoff must be between 55 and 120 mm")
        if state.base_frame != "so101_base" or state.gripper_positions["primary"] < 0.97:
            raise ValueError("SO-101 base frame and fully open gripper are required")
        current = state.joint_positions["primary"]
        position, rotation = self.forward(current)
        if np.linalg.norm(position - state.end_effector_poses["primary"].position) > 0.001:
            raise ValueError("Robot-only kinematics disagrees with measured TCP; do not move")
        radial = np.array([point[0], point[1], 0.0])
        if not 0.1 <= np.linalg.norm(radial) <= 0.5 or not 0.07 <= point[2] <= 0.45:
            raise ValueError("Observed target outside configured initial approach workspace")
        radial /= np.linalg.norm(radial)
        target = point - clearance_m * radial

        # SO-101's tool X is the forward axis. Keep it horizontal and preserve wrist roll.
        def residual(joints):
            actual, axes = self.forward(joints)
            return np.concatenate(
                (actual - target, 0.05 * (axes[:, 0] - radial), [0.015 * (joints[4] - current[4])])
            )

        lower, upper = self.low[:5] + 0.01, self.high[:5] - 0.01
        fit = least_squares(
            residual,
            np.clip(current, lower, upper),
            bounds=(lower, upper),
            max_nfev=160,
            ftol=1e-10,
            xtol=1e-10,
            gtol=1e-10,
        )
        actual, axes = self.forward(fit.x)
        error = float(np.linalg.norm(actual - target))
        angle = float(np.degrees(np.arccos(np.clip(axes[:, 0] @ radial, -1, 1))))
        if not fit.success or error > 0.004 or angle > 5:
            raise ValueError("No reachable open approach satisfying position/axis tolerances")
        count = max(2, math.ceil(float(np.max(np.abs(fit.x - current))) / 0.025) + 1)
        waypoints = np.linspace(current, fit.x, count)
        if not self.path_clear(waypoints):
            raise ValueError("Nominal joint path intersects the robot or work plane")
        return {
            "ok": True,
            "frame": state.base_frame,
            "target_position_m": target.tolist(),
            "fruit_point_m": point.tolist(),
            "clearance_m": clearance_m,
            "joint_target": fit.x.tolist(),
            "waypoints": waypoints.tolist(),
            "ik_position_error_m": error,
            "tool_axis_error_deg": angle,
            "timestamp_s": state.timestamp_s,
            "robot_commit": self.commit,
            "collision_scope": "nominal robot/self/work-plane only; plant/container path not certified",
            "target_source": "runtime public visual point plus radial standoff; no task geometry/waypoints",
        }
