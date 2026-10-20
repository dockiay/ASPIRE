"""Task-independent finger surfaces derived from the pinned robot mesh and FK."""

import numpy as np

from cap_harness.so101.kinematics import RobotKinematics
from cap_harness.so101.sensing import finger_geom_ids


class EffectorGeometry:
    def __init__(self):
        self.robot = RobotKinematics()
        robot = self.robot
        tcp, axes = robot.forward(np.zeros(5), 0)
        self.fingers = finger_geom_ids(robot.model)
        self.pads = {}
        self.hulls = {}
        for side, geom in self.fingers.items():
            mesh = robot.model.geom_dataid[geom]
            start = robot.model.mesh_vertadr[mesh]
            count = robot.model.mesh_vertnum[mesh]
            vertices = robot.model.mesh_vert[start : start + count].copy()
            rotation = robot.data.geom_xmat[geom].reshape(3, 3)
            local = (vertices @ rotation.T + robot.data.geom_xpos[geom] - tcp) @ axes
            distal = (local[:, 0] >= -0.02) & (np.abs(local[:, 1]) <= 0.01)
            face = local[distal, 2].max() if side == "fixed" else local[distal, 2].min()
            selected = distal & (np.abs(local[:, 2] - face) <= 0.002)
            self.pads[side] = vertices[selected]

    def describe(self, joints, opening):
        robot = self.robot
        tcp, axes = robot.forward(joints, opening)
        pads = {}
        for side, geom in self.fingers.items():
            points = self.pads[side] @ robot.data.geom_xmat[geom].reshape(3, 3).T
            points = (points + robot.data.geom_xpos[geom] - tcp) @ axes
            pads[side] = {
                "surface_center_m": points.mean(0).tolist(),
                "surface_bounds_m": [points.min(0).tolist(), points.max(0).tolist()],
            }
        fixed = np.asarray(pads["fixed"]["surface_center_m"])
        moving = np.asarray(pads["moving"]["surface_center_m"])
        span = moving - fixed
        return {
            "frame": "so101_gripperframe",
            "opening": float(opening),
            "tcp_location": "near distal fixed finger, not aperture center",
            "pads": pads,
            "grasp_center_in_tcp_m": ((fixed + moving) / 2).tolist(),
            "pad_center_separation_m": float(np.linalg.norm(span)),
            "closing_direction_in_tcp": (span / np.linalg.norm(span)).tolist(),
            "scope": "approximate opposing distal mesh surfaces; angular jaw, not parallel fingers; center separation is not guaranteed object clearance",
            "robot_commit": robot.commit,
        }

    def pad_contains(self, side, point_in_geom):
        points = self.pads[side]
        return bool(
            np.all(point_in_geom >= points.min(0) - 0.004)
            and np.all(point_in_geom <= points.max(0) + 0.004)
        )

    def check_path(
        self,
        waypoints,
        obstacle_points_m,
        *,
        opening=1.0,
        openings=None,
        finger_contact_mask=None,
        margin_m=0.003,
    ):
        """Sample robot convex hulls against public points; no hidden scene access."""
        path = np.asarray(waypoints, dtype=float)
        points = np.asarray(obstacle_points_m, dtype=float)
        if (
            path.ndim != 2
            or path.shape[1] != 5
            or not 1 <= len(path) <= 128
            or not np.isfinite(path).all()
        ):
            raise ValueError("Provide 1..128 five-axis joint waypoints")
        if points.size == 0:
            points = np.empty((0, 3))
        if (
            points.ndim != 2
            or points.shape[1] != 3
            or len(points) > 8192
            or not np.isfinite(points).all()
            or not 0 <= margin_m <= 0.02
        ):
            raise ValueError("Provide at most 8192 finite base-frame points and margin 0..20 mm")
        permitted = (
            np.zeros(len(points), dtype=bool)
            if finger_contact_mask is None
            else np.asarray(finger_contact_mask, dtype=bool)
        )
        if permitted.shape != (len(points),):
            raise ValueError("Finger contact mask must match public points")
        jaw_path = (
            np.full(len(path), opening) if openings is None else np.asarray(openings, dtype=float)
        )
        if (
            jaw_path.shape != (len(path),)
            or not np.isfinite(jaw_path).all()
            or np.any(jaw_path < 0)
            or np.any(jaw_path > 1)
        ):
            raise ValueError("Provide one finite gripper opening [0,1] per waypoint")
        robot = self.robot
        if np.any(path < robot.low[:5]) or np.any(path > robot.high[:5]):
            return {"ok": True, "path_clear": False, "reason": "joint_limits"}
        samples = [(path[0], jaw_path[0])]
        for i, (start, end) in enumerate(zip(path, path[1:])):
            count = (
                int(
                    np.ceil(
                        max(np.max(np.abs(end - start)), abs(jaw_path[i + 1] - jaw_path[i])) / 0.02
                    )
                )
                + 1
            )
            samples.extend(
                zip(
                    np.linspace(start, end, count)[1:],
                    np.linspace(jaw_path[i], jaw_path[i + 1], count)[1:],
                )
            )
        if len(samples) > 4096:
            raise ValueError("Path requires too many samples")
        model, data = robot.model, robot.data
        for index, (joints, jaw) in enumerate(samples):
            robot.forward(joints, jaw)
            if any(contact.dist <= -0.0001 for contact in data.contact):
                return {
                    "ok": True,
                    "path_clear": False,
                    "reason": "robot_or_work_plane",
                    "sample_index": index,
                }
            for geom in range(model.ngeom):
                name = model.body(int(model.geom_bodyid[geom])).name
                if not name.startswith("so101_") or not (
                    model.geom_contype[geom] or model.geom_conaffinity[geom]
                ):
                    continue
                mesh = int(model.geom_dataid[geom])
                if mesh < 0:
                    continue
                start, count = int(model.mesh_vertadr[mesh]), int(model.mesh_vertnum[mesh])
                vertices = model.mesh_vert[start : start + count]
                local = (points - data.geom_xpos[geom]) @ data.geom_xmat[geom].reshape(3, 3)
                inside = np.all(local >= vertices.min(0) - margin_m, axis=1) & np.all(
                    local <= vertices.max(0) + margin_m, axis=1
                )
                if geom in self.fingers.values():
                    side = next(side for side, value in self.fingers.items() if value == geom)
                    pad = self.pads[side]
                    on_pad = np.all(local >= pad.min(0) - 0.004, axis=1) & np.all(
                        local <= pad.max(0) + 0.004, axis=1
                    )
                    # Intended target contact allows the distal pad only, not
                    # every surface of the moving jaw/fixed-finger mesh.
                    inside &= ~(permitted & on_pad)
                if inside.any():
                    # A bounding box is only a broad phase: treating its empty
                    # corners as occupied rejects valid approaches to thin jaws.
                    # Refine against the robot mesh's convex hull, with the same
                    # distance margin. Only public robot geometry is consulted.
                    if geom not in self.hulls:
                        from scipy.spatial import ConvexHull

                        self.hulls[geom] = ConvexHull(vertices).equations
                    planes = self.hulls[geom]
                    candidates = np.flatnonzero(inside)
                    inside[candidates] = np.all(
                        local[candidates] @ planes[:, :3].T + planes[:, 3] <= margin_m,
                        axis=1,
                    )
                if inside.any():
                    return {
                        "ok": True,
                        "path_clear": False,
                        "reason": (
                            "observed_clearance"
                            if float(
                                np.max(
                                    local[int(np.flatnonzero(inside)[0])] @ planes[:, :3].T
                                    + planes[:, 3]
                                )
                            )
                            > 0
                            else "observed_obstacle"
                        ),
                        "sample_index": index,
                        "robot_link": name,
                        "public_point_index": int(np.flatnonzero(inside)[0]),
                        "gripper_opening": float(jaw),
                        "scope": "sampled convex-hull proximity; observed_clearance is a margin violation, not proof of physical contact",
                    }
        return {
            "ok": True,
            "path_clear": True,
            "sample_count": len(samples),
            "scope": "robot mesh convex hulls and joint/jaw samples against supplied public points; occluded geometry and space between samples remain uncertified",
        }
