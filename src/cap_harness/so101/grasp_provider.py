"""Observed-cloud grasp proposals for the SO-101 angular jaw.

This is a deterministic geometry heuristic, not Contact-GraspNet. It consumes
only public points and measured robot state. A candidate is a reachable open
pinch pose plus a checked final approach, not evidence of grasp or retention.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import replace

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from cap_harness.contracts import GraspCandidate, GraspSet, ObjectGeometry, PointCloud, RobotState
from cap_harness.errors import ApiError, ErrorCode
from cap_harness.geometry import matrix_to_pose
from cap_harness.so101.effector import EffectorGeometry
from cap_harness.so101.planning import (
    SELF_MASK_TOLERANCE_M,
    filter_observed_robot_points,
)
from cap_harness.so101.providers import SO101IKProvider


class SO101GraspProvider:
    """Propose bounded five-axis grasps with the robot's actual pinch offset."""

    backend = "so101-geometric"
    max_ik_calls = 24
    max_target_points = 65536
    max_scene_points = 2097152

    def __init__(
        self,
        state_provider: Callable[[], RobotState],
        *,
        ik_provider=None,
        effector_geometry=None,
    ):
        if not callable(state_provider):
            raise ValueError("state_provider must return public RobotState")
        self.state_provider = state_provider
        self.ik = ik_provider if ik_provider is not None else SO101IKProvider()
        self.effector = effector_geometry if effector_geometry is not None else EffectorGeometry()

    @staticmethod
    def _pose(position, axes, frame):
        matrix = np.eye(4)
        matrix[:3, :3], matrix[:3, 3] = axes, position
        return matrix_to_pose(matrix, frame=frame)

    @staticmethod
    def _sample(points, limit):
        """Deterministic coverage cap; omitted geometry remains uncertified."""
        if len(points) <= limit:
            return points
        return points[np.linspace(0, len(points) - 1, limit, dtype=int)]

    @staticmethod
    def _target_component(points):
        """Resolve mask/depth boundary outliers, never complete an occluded object."""
        count = len(points)
        scale_neighbors = min(9, max(3, count // 2))
        neighbors = min(32, count)
        distances, indexes = cKDTree(points).query(points, k=neighbors)
        # A local scale avoids fruit-specific crop boxes or a fixed workspace:
        # the same rule handles millimetre samples and sparse engineering clouds.
        radius = max(0.001, 3.0 * float(np.median(distances[:, scale_neighbors - 1])))
        sources = np.repeat(np.arange(count), neighbors)
        valid = (distances <= radius).ravel()
        graph = coo_matrix(
            (np.ones(int(valid.sum())), (sources[valid], indexes.ravel()[valid])),
            shape=(count, count),
        )
        component_count, labels = connected_components(graph, directed=False)
        sizes = np.bincount(labels, minlength=component_count)
        order = np.argsort(-sizes, kind="stable")
        selected = labels == order[0]
        largest = int(sizes[order[0]])
        second = int(sizes[order[1]]) if len(order) > 1 else 0
        unambiguous = largest >= 6 and largest / count >= 0.7 and second / count < 0.2
        return selected, {
            "method": "dominant connected 3D component of public mask points",
            "radius_m": radius,
            "component_count": int(component_count),
            "selected_points": largest,
            "excluded_points": count - largest,
            "selected_fraction": largest / count,
            "second_component_fraction": second / count,
            "unambiguous": unambiguous,
            "scope": (
                "requires >=70% support and no second component >=20%; excluded mask "
                "samples retain obstacle status, not target-contact permission"
            ),
        }

    @staticmethod
    def _directions(center, current_axes):
        radial = np.array([center[0], center[1], 0.0])
        if np.linalg.norm(radial) < 1e-9:
            radial = np.array([1.0, 0.0, 0.0])
        radial /= np.linalg.norm(radial)
        options = [
            current_axes[:, 0],
            radial,
            radial + [0, 0, -0.6],
            radial + [0, 0, 0.6],
            [0, 0, -1],
            -radial,
        ]
        directions = []
        for option in options:
            direction = np.asarray(option, dtype=float)
            direction = direction / np.linalg.norm(direction)
            if not any(direction @ previous > 0.999 for previous in directions):
                directions.append(direction)
        return directions

    def generate_grasps(
        self,
        point_cloud,
        *,
        scene_point_cloud=None,
        geometry=None,
        max_candidates=None,
    ):
        diagnostics = {
            "provider": self.backend,
            "method": "angular-jaw geometry and point/axis IK",
            "learned_model": False,
            "grasp_verified": False,
            "ik_call_budget": self.max_ik_calls,
            "ik_calls": 0,
            "max_target_points": self.max_target_points,
            "max_scene_points": self.max_scene_points,
            "scope": (
                "reachable TCP and sampled final approach against supplied public points; "
                "object completion, occluded geometry, current-to-pregrasp transit, opening "
                "the jaw, closure, force and retention are not certified"
            ),
        }

        def failure(code, message):
            return GraspSet(ok=False, error=ApiError(code, message), diagnostics=diagnostics)

        if not isinstance(point_cloud, PointCloud):
            return failure(ErrorCode.INVALID_REQUEST, "point_cloud must be PointCloud")
        if point_cloud.frame != "so101_base":
            return failure(ErrorCode.INVALID_REQUEST, "Point cloud must use so101_base")
        if scene_point_cloud is not None and (
            not isinstance(scene_point_cloud, PointCloud)
            or scene_point_cloud.frame != point_cloud.frame
        ):
            return failure(ErrorCode.INVALID_REQUEST, "Scene must be a PointCloud in so101_base")
        if geometry is not None and (
            not isinstance(geometry, ObjectGeometry) or geometry.frame != point_cloud.frame
        ):
            return failure(ErrorCode.INVALID_REQUEST, "Geometry must use the point cloud frame")
        if scene_point_cloud is not None and len(scene_point_cloud.points) > self.max_scene_points:
            return failure(
                ErrorCode.INVALID_REQUEST, "Scene point budget exceeded; explicitly voxelize it"
            )
        if max_candidates is not None and (
            isinstance(max_candidates, bool)
            or not isinstance(max_candidates, int)
            or not 1 <= max_candidates <= 32
        ):
            return failure(ErrorCode.INVALID_REQUEST, "max_candidates must be an integer 1..32")
        limit = 5 if max_candidates is None else max_candidates
        supplied_points = point_cloud.points
        points = supplied_points
        if len(points) > self.max_target_points:
            return failure(
                ErrorCode.INVALID_REQUEST,
                f"Target exceeds {self.max_target_points} points; explicitly refine or "
                "subsample the target mask before grasp generation",
            )
        # A single pixel/line does not constrain an observed object cross-section.
        if len(points) < 6 or np.linalg.matrix_rank(points - points.mean(0), tol=1e-6) < 2:
            return failure(ErrorCode.NO_GRASP, "Insufficient observed surface for grasp proposals")
        selected, component = self._target_component(points)
        diagnostics["target_component"] = component
        if not component["unambiguous"]:
            return failure(
                ErrorCode.NO_GRASP,
                "Mask points do not identify one dominant connected observed surface",
            )
        points = points[selected]
        if np.linalg.matrix_rank(points - points.mean(0), tol=1e-6) < 2:
            return failure(ErrorCode.NO_GRASP, "Dominant surface has insufficient cross-section")
        try:
            state = self.state_provider()
        except Exception as error:
            return failure(ErrorCode.PROVIDER_ERROR, f"Cannot read public robot state: {error}")
        if (
            not isinstance(state, RobotState)
            or state.embodiment != "so101"
            or state.base_frame != "so101_base"
            or state.arms != ("primary",)
        ):
            return failure(ErrorCode.INVALID_REQUEST, "A measured primary SO-101 state is required")
        current = state.joint_positions["primary"]
        names = tuple(
            self.ik.robot.model.joint(int(index)).name for index in self.ik.robot.joints[:5]
        )
        if tuple(state.joint_names["primary"]) != names:
            return failure(
                ErrorCode.INVALID_REQUEST, "State joint names/order disagree with SO-101"
            )
        current_pose = state.end_effector_poses["primary"]
        model_position, model_axes = self.ik.robot.forward(
            current, state.gripper_positions["primary"]
        )
        if np.linalg.norm(model_position - current_pose.position) > 0.001 or not np.allclose(
            model_axes, current_pose.as_matrix()[:3, :3], atol=0.001
        ):
            return failure(ErrorCode.PROVIDER_ERROR, "Robot model disagrees with measured TCP")

        target_points = self._sample(points, 4096)
        excluded_mask_points = supplied_points[~selected]
        if len(excluded_mask_points) >= 4096:
            return failure(
                ErrorCode.NO_GRASP,
                "Too many excluded mask points to retain all as obstacles; refine the observation",
            )
        removed_robot_points = 0
        if scene_point_cloud is None:
            other_obstacles = np.empty((0, 3))
        else:
            # Only the observed target samples, not its bounding box or all nearby
            # foliage, may receive distal-pad contact permission.
            distances, _ = cKDTree(supplied_points).query(scene_point_cloud.points, k=1)
            other_obstacles, removed_robot_points = filter_observed_robot_points(
                self.effector,
                state,
                scene_point_cloud.points[distances > 1e-6],
            )
        # Keep *every* rejected mask sample, without self masking, before
        # budgeting the rest of the observed scene. A component rejected as a
        # grasp target must not disappear from collision checks through sampling.
        obstacles = np.vstack(
            [
                excluded_mask_points,
                self._sample(other_obstacles, 4096 - len(excluded_mask_points)),
            ]
        )
        check_points = np.vstack([target_points, obstacles])
        permitted = np.arange(len(check_points)) < len(target_points)
        diagnostics["target_points"] = len(supplied_points)
        diagnostics["component_target_points"] = len(points)
        diagnostics["checked_target_points"] = len(target_points)
        diagnostics["checked_obstacle_points"] = len(obstacles)
        diagnostics["excluded_mask_points_preserved_as_obstacles"] = len(excluded_mask_points)
        diagnostics["removed_robot_points"] = removed_robot_points
        diagnostics["robot_filter_numerical_tolerance_m"] = SELF_MASK_TOLERANCE_M
        diagnostics["robot_filter_scope"] = (
            "current public robot visual/collision mesh-hull occupancy with "
            f"{SELF_MASK_TOLERANCE_M * 1e6:g} micrometre numerical "
            "tolerance; no clearance inflation; overlapping robot/obstacle returns are "
            "ambiguous; target samples are never removed by this filter"
        )
        diagnostics["scene_supplied"] = scene_point_cloud is not None
        center = (points.min(0) + points.max(0)) / 2
        openings = np.linspace(0.0, 1.0, 81)
        jaw_geometry = [self.effector.describe(current, opening) for opening in openings]
        separations = np.array([item["pad_center_separation_m"] for item in jaw_geometry])
        rejected = Counter()
        candidates = []
        attempts = []
        diagnostics["attempts"] = attempts

        def solve(local_center, target, direction, jaw, seed):
            diagnostics["ik_calls"] += 1
            return self.ik.solve_point_axis_ik(
                local_center,
                target,
                [1, 0, 0],
                direction,
                replace(state, gripper_positions={"primary": float(jaw)}),
                frame=point_cloud.frame,
                seed_joints=seed,
            )

        for direction in self._directions(center, model_axes):
            if len(candidates) >= limit or diagnostics["ik_calls"] + 4 > self.max_ik_calls:
                break
            attempt = {"approach_direction": direction.tolist()}
            attempts.append(attempt)
            jaw_index = len(openings) - 1
            seed = current
            target = center.copy()
            fitted = None
            # Up to three solves: discover achieved closing direction, choose a
            # mesh-derived aperture, then re-solve the changed pinch-center offset.
            for _ in range(3):
                jaw = float(openings[jaw_index])
                shape = jaw_geometry[jaw_index]
                local_center = np.asarray(shape["grasp_center_in_tcp_m"])
                fitted = solve(local_center, target, direction, jaw, seed)
                if not fitted.ok:
                    rejected["ik_unreachable"] += 1
                    attempt.update(status="ik_unreachable", ik=dict(fitted.diagnostics))
                    fitted = None
                    break
                joints = fitted.joint_positions
                position, axes = self.ik.robot.forward(joints, jaw)
                closing = axes @ np.asarray(shape["closing_direction_in_tcp"])
                projection = points @ closing
                width = float(np.ptp(projection))
                possible = np.flatnonzero(separations >= width + 0.004)
                if not len(possible):
                    rejected["object_too_wide"] += 1
                    attempt.update(status="object_too_wide", observed_object_width_m=width)
                    fitted = None
                    break
                local_points = points @ axes
                next_target = ((local_points.min(0) + local_points.max(0)) / 2) @ axes.T
                next_index = int(possible[0])
                if next_index == jaw_index and np.linalg.norm(next_target - target) < 0.0005:
                    break
                seed, target, jaw_index = joints, next_target, next_index
                fitted = None
            if fitted is None:
                if "status" not in attempt:
                    rejected["aperture_fit_unresolved"] += 1
                    attempt["status"] = "aperture_fit_unresolved"
                continue
            # These values always describe the last executed solve, not a new
            # opening whose shifted pinch center has not yet been solved.
            if separations[jaw_index] < width + 0.002:
                rejected["insufficient_aperture"] += 1
                attempt["status"] = "insufficient_aperture"
                continue
            approach_distance = 0.025
            before = solve(
                local_center,
                target - approach_distance * axes[:, 0],
                axes[:, 0],
                jaw,
                joints,
            )
            if not before.ok:
                rejected["pregrasp_unreachable"] += 1
                attempt.update(status="pregrasp_unreachable", ik=dict(before.diagnostics))
                continue
            check = self.effector.check_path(
                [before.joint_positions, joints],
                check_points,
                opening=jaw,
                finger_contact_mask=permitted,
                margin_m=0.001,
            )
            attempt.update(
                gripper_position=jaw,
                observed_object_width_m=width,
                approach_check=check,
            )
            if not check["path_clear"]:
                rejected["observed_approach_collision"] += 1
                attempt["status"] = "observed_approach_collision"
                if "public_point_index" in check:
                    index = check["public_point_index"]
                    attempt["blocking_sample_kind"] = "target" if permitted[index] else "scene"
                    attempt["blocking_point_m"] = check_points[index].tolist()
                continue
            attempt["status"] = "proposal"
            before_position, before_axes = self.ik.robot.forward(before.joint_positions, jaw)
            pose = self._pose(position, axes, point_cloud.frame)
            # This score ranks numerical proposals; it is not a probability of
            # grasp success or a measure of visible/occluded object completeness.
            displacement = float(np.linalg.norm(joints - current))
            score = float(1.0 / (1.0 + displacement))
            candidates.append(
                GraspCandidate(
                    pose=pose,
                    score=score,
                    width_m=float(separations[jaw_index]),
                    approach_distance_m=approach_distance,
                    metadata={
                        "provider": self.backend,
                        "grasp_verified": False,
                        "score_semantics": "joint-distance heuristic, not success probability",
                        "gripper_position": jaw,
                        "width_semantics": "distance between angular-jaw distal pad centers",
                        "observed_object_width_m": width,
                        "approach_axis": 0,
                        "approach_direction": axes[:, 0].tolist(),
                        "grasp_center_in_tcp_m": local_center.tolist(),
                        "observed_center_m": target.tolist(),
                        "achieved_grasp_center_m": (position + axes @ local_center).tolist(),
                        "joint_target": joints.tolist(),
                        "pregrasp_joints": before.joint_positions.tolist(),
                        "pregrasp_pose": self._pose(
                            before_position, before_axes, point_cloud.frame
                        ),
                        "point_error_m": float(
                            np.linalg.norm(position + axes @ local_center - target)
                        ),
                        "approach_check": check,
                        "robot_commit": self.ik.robot.commit,
                        "scope": diagnostics["scope"],
                    },
                )
            )
        diagnostics["rejections"] = dict(rejected)
        if not candidates:
            return failure(
                ErrorCode.NO_GRASP,
                "No reachable observed-cloud pinch and final approach within the bounded search",
            )
        candidates.sort(key=lambda candidate: -candidate.score)
        return GraspSet(ok=True, grasps=candidates, diagnostics=diagnostics)
