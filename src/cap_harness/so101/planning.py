"""Bounded joint-space search using public depth points and robot-only geometry."""

from __future__ import annotations

import math
import time

import numpy as np

from cap_harness.contracts import (
    PlanningScene,
    PlanResult,
    RobotPlanningContext,
    RobotState,
    Trajectory,
)
from cap_harness.errors import ApiError, ErrorCode
from cap_harness.so101.effector import EffectorGeometry


class _SearchLimit(Exception):
    pass


# Numerical self-mask tolerance, independent of the path clearance margin.
# Nearby samples 0.1 mm outside robot hulls must remain obstacles. Depth
# reconstruction errors depend on camera resolution and the rendering backend.
SELF_MASK_TOLERANCE_M = 1e-5


def filter_observed_robot_points(geometry, robot_state, points):
    """Return (kept points, removed count) using only current robot occupancy.

    Clearance margins are never used here. Points inside/on a starting robot
    mesh hull are considered robot returns; truly overlapping obstacle
    returns are inherently ambiguous. Callers should retain intended target
    points separately when checking allowed pad contact.
    """
    if (
        not isinstance(robot_state, RobotState)
        or robot_state.embodiment != "so101"
        or robot_state.base_frame != "so101_base"
        or robot_state.arms != ("primary",)
    ):
        raise ValueError("Robot filtering requires public SO-101 state in so101_base")
    return _filter_robot_points(
        geometry,
        points,
        robot_state.joint_positions["primary"],
        robot_state.gripper_positions["primary"],
    )


def _filter_robot_points(geometry, points, joints, opening):
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError("Robot filtering requires finite Nx3 base-frame points")
    robot = geometry.robot
    robot.forward(joints, opening)
    model, data = robot.model, robot.data
    occupied = np.zeros(len(points), dtype=bool)
    for geom in range(model.ngeom):
        name = model.body(int(model.geom_bodyid[geom])).name
        # Rendered robot parts (notably the fixed base) need not have collision
        # enabled. They are still robot returns, so include the declared visual
        # meshes as well as collision meshes, without expanding their surfaces.
        if not name.startswith("so101_"):
            continue
        mesh = int(model.geom_dataid[geom])
        if mesh < 0:
            continue
        start, count = int(model.mesh_vertadr[mesh]), int(model.mesh_vertnum[mesh])
        vertices = model.mesh_vert[start : start + count]
        local = (points - data.geom_xpos[geom]) @ data.geom_xmat[geom].reshape(3, 3)
        tolerance = SELF_MASK_TOLERANCE_M
        candidates = np.flatnonzero(
            ~occupied
            & np.all(local >= vertices.min(0) - tolerance, axis=1)
            & np.all(local <= vertices.max(0) + tolerance, axis=1)
        )
        if not len(candidates):
            continue
        if geom not in geometry.hulls:
            from scipy.spatial import ConvexHull

            geometry.hulls[geom] = ConvexHull(vertices).equations
        planes = geometry.hulls[geom]
        occupied[candidates] = np.all(
            local[candidates] @ planes[:, :3].T + planes[:, 3] <= tolerance,
            axis=1,
        )
    return points[~occupied], int(occupied.sum())


class SO101TrajectoryPlanner:
    """A deterministic RRT-Connect provider, not a certificate for unseen space.

    The robot model contains only the SO-101 and its work plane. Obstacles are
    supplied through PlanningScene; no environment instance or hidden task state
    is accepted. A public state callback can locate observed robot returns when
    the requested planning start is hypothetical. Pending jaw motion is checked
    and scheduled before arm motion.
    """

    def __init__(
        self,
        *,
        dt_s=0.05,
        joint_speed_rad_s=0.5,
        gripper_speed=0.25,
        margin_m=0.003,
        max_iterations=256,
        max_seconds=8.0,
        seed=0,
        state_provider=None,
    ):
        self.dt_s = self._number(dt_s, "dt_s", 0, 0.2)
        self.speed = self._number(joint_speed_rad_s, "joint_speed_rad_s", 0, 1)
        self.gripper_speed = self._number(gripper_speed, "gripper_speed", 0, 1)
        self.margin_m = self._number(margin_m, "margin_m", -1e-15, 0.02)
        if self.margin_m < 0:
            raise ValueError("margin_m must be nonnegative")
        self.max_seconds = self._number(max_seconds, "max_seconds", 0, 60)
        if type(max_iterations) is not int or not 1 <= max_iterations <= 2048:
            raise ValueError("max_iterations must be an integer from 1 to 2048")
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError("seed must be an integer from 0 to 2**32 - 1")
        if state_provider is not None and not callable(state_provider):
            raise ValueError("state_provider must be a public RobotState callback or None")
        self.max_iterations = max_iterations
        self.seed = seed
        self.state_provider = state_provider
        self._geometry = None

    @staticmethod
    def _number(value, name, lower, upper):
        if isinstance(value, (bool, np.bool_)) or np.ndim(value) != 0:
            raise ValueError(f"{name} must be a finite number")
        value = float(value)
        if not np.isfinite(value) or not lower < value <= upper:
            raise ValueError(f"{name} must be finite, > {lower} and <= {upper}")
        return value

    @property
    def geometry(self):
        if self._geometry is None:
            self._geometry = EffectorGeometry()
        return self._geometry

    @staticmethod
    def _failure(code, message, diagnostics):
        return PlanResult(
            ok=False,
            error=ApiError(code, message),
            diagnostics=diagnostics,
        )

    def _without_start_robot(self, points, joints, opening):
        return _filter_robot_points(self.geometry, points, joints, opening)

    def plan_to_joints(
        self,
        robot_state,
        target_joints,
        *,
        arm="primary",
        gripper_position=None,
        scene=None,
        context=None,
        time_dilation_factor=None,
        interpolation_dt_s=None,
        maximum_trajectory_dt_s=None,
    ):
        diagnostics = {
            "trajectory_planner": "so101",
            "algorithm": "bounded_rrt_connect",
            "seed": self.seed,
            "scope": (
                "sampled robot convex collision meshes, self/work-plane and supplied "
                "public depth points; occluded geometry, gaps between depth/sweep samples, "
                "and tracking error are not certified"
            ),
            "start_robot_filter": (
                "observed robot visual/collision mesh hull occupancy only; "
                "10 micrometre numerical tolerance, "
                "no clearance inflation; overlapping obstacle/robot returns are ambiguous"
            ),
            "target_exclusion": (
                "no target points removed; optional public contact_target permits "
                "only distal pad contact within 1 mm of its observed samples"
            ),
            "jaw_schedule": "pending jaw motion first with arm stationary, then arm path",
            "margin_m": self.margin_m,
            "robot_mask_numerical_tolerance_m": SELF_MASK_TOLERANCE_M,
            "collision_checks": 0,
        }
        started = time.monotonic()
        try:
            start, goal, measured_jaw, jaw, dilation = self._validate(
                robot_state,
                target_joints,
                arm,
                gripper_position,
                scene,
                context,
                time_dilation_factor,
                interpolation_dt_s,
                maximum_trajectory_dt_s,
            )
        except (ValueError, TypeError, KeyError) as exc:
            return self._failure(ErrorCode.INVALID_REQUEST, str(exc), diagnostics)
        try:
            geometry = self.geometry
            low, high = geometry.robot.low[:5], geometry.robot.high[:5]
            names = tuple(
                geometry.robot.model.joint(int(index)).name for index in geometry.robot.joints[:5]
            )
            if tuple(robot_state.joint_names[arm]) != names:
                return self._failure(
                    ErrorCode.INVALID_REQUEST,
                    "State joint names/order disagree with the SO-101 robot model",
                    diagnostics,
                )
            if np.any(start < low) or np.any(start > high):
                return self._failure(
                    ErrorCode.INVALID_REQUEST, "Start joints exceed SO-101 limits", diagnostics
                )
            if np.any(goal < low) or np.any(goal > high):
                return self._failure(
                    ErrorCode.INVALID_REQUEST, "Target joints exceed SO-101 limits", diagnostics
                )
            mask_state = robot_state if self.state_provider is None else self.state_provider()
            if (
                not isinstance(mask_state, RobotState)
                or mask_state.embodiment != "so101"
                or mask_state.base_frame != "so101_base"
                or mask_state.arms != ("primary",)
                or tuple(mask_state.joint_names["primary"]) != names
            ):
                return self._failure(
                    ErrorCode.PROVIDER_ERROR,
                    "Observed robot state callback does not match the SO-101 model/frame",
                    diagnostics,
                )
            raw_points = scene.point_cloud.points
            contact_target = getattr(scene, "contact_target", None)
            target_tree = None
            target_mask = np.zeros(len(raw_points), dtype=bool)
            if contact_target is not None:
                from scipy.spatial import cKDTree

                target_tree = cKDTree(contact_target.points)
                target_mask = target_tree.query(raw_points, k=1)[0] <= 0.001
            points, removed = self._without_start_robot(
                raw_points[~target_mask],
                mask_state.joint_positions["primary"],
                mask_state.gripper_positions["primary"],
            )
            # Intended target returns are not robot returns, even if already
            # touching a pad. Keep them so palm/forearm intersections are still
            # rejected by the geometry checker.
            points = np.concatenate((points, raw_points[target_mask]), axis=0)
            permitted = np.concatenate(
                (
                    np.zeros(len(points) - int(target_mask.sum()), dtype=bool),
                    np.ones(int(target_mask.sum()), dtype=bool),
                )
            )
            diagnostics.update(
                robot_mask_state_source=(
                    "public_observed_state_callback"
                    if self.state_provider is not None
                    else "provided_start_state"
                ),
                input_point_count=len(scene.point_cloud.points),
                start_robot_point_count=removed,
                obstacle_point_count=len(points),
                permitted_pad_contact_point_count=int(permitted.sum()),
                scene_voxel_size_m=scene.voxel_size_m,
            )
            if not len(points):
                return self._failure(
                    ErrorCode.PLANNING_FAILED,
                    "No observed scene remains after start-robot filtering",
                    diagnostics,
                )

            def clear(a, b, opening_a=jaw, opening_b=jaw):
                if time.monotonic() - started >= self.max_seconds:
                    raise _SearchLimit("wall_time_budget")
                if diagnostics["collision_checks"] >= self.max_iterations * 12 + 4:
                    raise _SearchLimit("collision_check_budget")
                diagnostics["collision_checks"] += 1
                for offset in range(0, len(points), 8192):
                    result = geometry.check_path(
                        [a, b],
                        points[offset : offset + 8192],
                        openings=[opening_a, opening_b],
                        finger_contact_mask=permitted[offset : offset + 8192],
                        margin_m=self.margin_m,
                    )
                    if not result.get("ok") or not result.get("path_clear"):
                        diagnostics["last_rejection"] = result
                        return False
                return True

            if not clear(start, start, measured_jaw, jaw):
                return self._failure(
                    ErrorCode.PLANNING_FAILED,
                    "Start configuration or pending gripper sweep is obstructed",
                    diagnostics,
                )
            if not clear(goal, goal):
                return self._failure(
                    ErrorCode.PLANNING_FAILED, "Target configuration is obstructed", diagnostics
                )
            if clear(start, goal):
                path = [start, goal]
                diagnostics["search_iterations"] = 0
                diagnostics["direct_path_clear"] = True
            else:
                diagnostics["direct_path_clear"] = False
                path = self._search(start, goal, low, high, clear, diagnostics)
                if path is None:
                    return self._failure(
                        ErrorCode.PLANNING_FAILED,
                        "No path found within the bounded search; no fallback was executed",
                        diagnostics,
                    )
            positions, grippers = self._timed(path, measured_jaw, jaw, dilation)
            if len(positions) > 8192:
                return self._failure(
                    ErrorCode.PLANNING_FAILED, "Timed path exceeds 8192 control ticks", diagnostics
                )
            diagnostics.update(
                path_vertex_count=len(path),
                elapsed_s=time.monotonic() - started,
                joint_speed_limit_rad_s=self.speed * dilation,
                gripper_speed_limit=self.gripper_speed * dilation,
                duration_s=len(positions) * self.dt_s,
            )
            return PlanResult(
                ok=True,
                trajectory=Trajectory(
                    joint_positions=positions,
                    gripper_positions=grippers,
                    dt_s=self.dt_s,
                    joint_names=robot_state.joint_names[arm],
                    planner="so101_rrt_connect",
                    collision_aware=True,
                    expected_start=robot_state,
                    arm=arm,
                    embodiment="so101",
                ),
                diagnostics=diagnostics,
            )
        except _SearchLimit as exc:
            diagnostics.update(limit_reason=str(exc), elapsed_s=time.monotonic() - started)
            return self._failure(
                ErrorCode.PLANNING_FAILED, "SO-101 planning budget exhausted", diagnostics
            )
        except Exception as exc:
            diagnostics["exception_type"] = type(exc).__name__
            return self._failure(
                ErrorCode.PROVIDER_ERROR, f"SO-101 geometry planning failed: {exc}", diagnostics
            )

    def _validate(self, state, goal, arm, jaw, scene, context, dilation, dt, maximum_dt):
        if not isinstance(state, RobotState) or state.embodiment != "so101":
            raise ValueError("SO-101 planning requires a SO-101 RobotState")
        if state.base_frame != "so101_base" or arm != "primary" or state.arms != ("primary",):
            raise ValueError("SO-101 planning requires primary arm in so101_base")
        if not isinstance(scene, PlanningScene) or scene.frame != state.base_frame:
            raise ValueError("Provide a public PlanningScene in so101_base")
        contact_target = getattr(scene, "contact_target", None)
        if contact_target is not None and contact_target.frame != scene.frame:
            raise ValueError("Contact target must share the public planning scene frame")
        if contact_target is not None and len(contact_target.points) > 32768:
            raise ValueError("Contact target exceeds 32768 public points; explicitly voxelize it")
        if len(scene.point_cloud.points) > 32768:
            raise ValueError("Planning scene exceeds 32768 public points; explicitly voxelize it")
        if context is not None:
            if (
                not isinstance(context, RobotPlanningContext)
                or context.embodiment != "so101"
                or context.model != "so101"
                or context.arms != ("primary",)
                or tuple(context.joint_names[arm]) != tuple(state.joint_names[arm])
                or not np.allclose(context.base_transforms[arm], np.eye(4), atol=1e-9)
            ):
                raise ValueError("Planning context does not match the SO-101 base and joint order")
        goal = np.asarray(goal, dtype=float)
        if goal.shape != (5,) or not np.isfinite(goal).all():
            raise ValueError("Target must contain five finite joint positions")
        measured_jaw = state.gripper_positions[arm]
        jaw = measured_jaw if jaw is None else self._number(jaw, "gripper_position", -1e-15, 1)
        if jaw < 0:
            raise ValueError("gripper_position must be nonnegative")
        dilation = 1 if dilation is None else self._number(dilation, "time_dilation_factor", 0, 1)
        if dt is not None:
            dt = self._number(dt, "interpolation_dt_s", 0, 1)
            if not np.isclose(dt, self.dt_s, rtol=0, atol=1e-9):
                raise ValueError("interpolation_dt_s must equal the native SO-101 control period")
        if maximum_dt is not None:
            maximum_dt = self._number(maximum_dt, "maximum_trajectory_dt_s", 0, 60)
            if maximum_dt + 1e-9 < self.dt_s:
                raise ValueError("maximum_trajectory_dt_s is below the native control period")
        return state.joint_positions[arm], goal, measured_jaw, jaw, dilation

    def _search(self, start, goal, low, high, clear, diagnostics):
        random = np.random.default_rng(self.seed)
        trees = [([start.copy()], [-1]), ([goal.copy()], [-1])]

        def extend(tree, target):
            nodes, parents = tree
            near = int(np.argmin(np.max(np.abs(np.asarray(nodes) - target), axis=1)))
            delta = target - nodes[near]
            distance = float(np.max(np.abs(delta)))
            if distance < 1e-10:
                return near, True
            new = nodes[near] + delta * min(1, 0.25 / distance)
            if not clear(nodes[near], new):
                return None, False
            nodes.append(new)
            parents.append(near)
            return len(nodes) - 1, distance <= 0.25

        def branch(tree, index):
            nodes, parents = tree
            result = []
            while index >= 0:
                result.append(nodes[index])
                index = parents[index]
            return list(reversed(result))

        for iteration in range(self.max_iterations):
            diagnostics["search_iterations"] = iteration + 1
            first = iteration % 2
            second = 1 - first
            sample = random.uniform(low, high)
            if iteration % 5 == 0:
                sample = trees[second][0][0]
            index, _ = extend(trees[first], sample)
            if index is None:
                continue
            target = trees[first][0][index]
            for _ in range(32):
                connected, reached = extend(trees[second], target)
                if connected is None:
                    break
                if reached:
                    a, b = branch(trees[first], index), branch(trees[second], connected)
                    path = a + b[-2::-1]
                    return path if first == 0 else list(reversed(path))
        return None

    def _timed(self, path, measured_jaw, jaw, dilation):
        positions, grippers = [], []
        jaw_count = math.ceil(abs(jaw - measured_jaw) / (self.gripper_speed * dilation * self.dt_s))
        if jaw_count > 8192:
            raise _SearchLimit("trajectory_tick_budget")
        if jaw_count:
            positions.extend([path[0]] * jaw_count)
            grippers.extend(np.linspace(measured_jaw, jaw, jaw_count + 1)[1:])
        for start, end in zip(path, path[1:]):
            count = max(
                1,
                math.ceil(float(np.max(np.abs(end - start))) / (self.speed * dilation * self.dt_s)),
            )
            if len(positions) + count > 8192:
                raise _SearchLimit("trajectory_tick_budget")
            positions.extend(np.linspace(start, end, count + 1)[1:])
            grippers.extend([jaw] * count)
        return np.asarray(positions), np.asarray(grippers)
