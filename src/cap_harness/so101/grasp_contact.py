"""Two-finger contact qualification while the rigid strawberry remains attached."""

from __future__ import annotations

import math

import numpy as np

from cap_harness.so101.environment import SO101ControlEnvironment
from cap_harness.so101.sensing import finger_geom_ids, fingertip_region, read_finger_contacts
from cap_harness.so101.strawberry import FRUIT_POSITION, add_strawberry_plant

CONTACT_HOLD_SECONDS = 0.5
MAX_FINGER_FORCE_N = 12.0
MAX_PENETRATION_M = 0.0015
MIN_FINGER_FORCE_N = 0.1
GRASP_OFFSET_M = (0.0, 0.0, 0.021)

__all__ = [
    "SO101StrawberryGraspContactEnvironment",
    "finger_geom_ids",
    "fingertip_region",
    "read_finger_contacts",
]


class SO101StrawberryGraspContactEnvironment(SO101ControlEnvironment):
    requires_pregrasp_pose = True
    grasp_offset = GRASP_OFFSET_M
    camera_target = (0.29, 0.01, 0.18)
    camera_positions = (("agentview", (0.68, -0.67, 0.52)), ("sideview", (0.27, 0.78, 0.46)))
    initial_joints = (0.65, -1.219625, 0.744906, 0.474719, math.pi / 2)

    def configure_scene(self, scene) -> None:
        add_strawberry_plant(scene)

    @staticmethod
    def lesson_metadata() -> dict:
        return {
            "target_source": "declared_fixed_lesson_coordinates",
            "fruit_center_m": FRUIT_POSITION,
            "fruit_center_in_tool_m": GRASP_OFFSET_M,
            "tool_site": "so101_gripperframe",
            "frame": "so101_base",
            "contact_hold_seconds": CONTACT_HOLD_SECONDS,
            "maximum_finger_force_n": MAX_FINGER_FORCE_N,
            "force_limit_meaning": "simulation exercise bound; not a fruit damage threshold",
            "sensor_source": "virtual simulation fingertip sensors; not stock hardware",
            "scene_variation": "none; fixed rigid fruit attached to plant",
        }

    def _reset_task_state(self) -> None:
        self.fingers = finger_geom_ids(self.model)
        self.fruit_geoms = {self.model.geom(name).id for name in ("plant_fruit", "plant_fruit_tip")}
        self.robot_geoms = {
            i
            for i in range(self.model.ngeom)
            if self.model.body(int(self.model.geom_bodyid[i])).name.startswith("so101_")
        }
        self.obstacles = {
            i
            for i in range(self.model.ngeom)
            if self.model.geom(i).name.startswith("plant_")
            or self.model.geom(i).name == "work_surface"
        }
        self.initial_tool_position = self.sim.data.get_site_xpos("so101_gripperframe").copy()
        self.ready_streak = self.retreat_streak = 0
        self.ready_step = self.retreat_step = None
        self.grasp_time = self.release_time = None
        self.contact_start_time = None
        self.longest_contact_duration_s = 0.0
        self.forbidden_contacts: set[tuple[str, str]] = set()
        self.limit_violations: set[str] = set()
        self.early_closure = False
        self.peak_finger_force = dict.fromkeys(self.fingers, 0.0)
        self.max_penetration = 0.0
        self.grasp_witness = None
        self.current_contacts = {side: [] for side in self.fingers}
        self.required_pose_ticks = math.ceil(0.25 * self.frequency) + 1
        self._after_physics_step()

    def _label(self, geom: int) -> str:
        return self.model.geom(geom).name or (
            self.model.body(int(self.model.geom_bodyid[geom])).name + f":geom_{geom}"
        )

    def fingertip_contact(self, side, world_position, tcp_position):
        return fingertip_region(tcp_position)

    def _after_physics_step(self) -> None:
        import mujoco

        self.sim.forward()
        self.current_contacts = {side: [] for side in self.fingers}
        finger_forces = dict.fromkeys(self.fingers, 0.0)
        tcp = self.sim.data.get_site_xpos("so101_gripperframe")
        rotation = self.sim.data.get_site_xmat("so101_gripperframe")
        for index, contact in enumerate(self.sim.data.contact):
            if contact.dist > 0:
                continue
            a, b = int(contact.geom1), int(contact.geom2)
            if not ({a, b} & self.robot_geoms):
                continue
            side = next(
                (
                    s
                    for s, geom in self.fingers.items()
                    if (a == geom and b in self.fruit_geoms)
                    or (b == geom and a in self.fruit_geoms)
                ),
                None,
            )
            local = (contact.pos - tcp) @ rotation
            if side is not None and self.fingertip_contact(side, contact.pos, local):
                wrench = np.zeros(6)
                mujoco.mj_contactForce(self.model, self.sim.data._data, index, wrench)
                force = max(0.0, float(wrench[0]))
                finger_forces[side] += force
                penetration = max(0.0, float(-contact.dist))
                self.max_penetration = max(self.max_penetration, penetration)
                if penetration > MAX_PENETRATION_M:
                    self.limit_violations.add("excessive_model_penetration")
                # MuJoCo normals point from geom1 toward geom2. Orient onto the fruit.
                normal = np.asarray(contact.frame[:3]) * (-1 if a in self.fruit_geoms else 1)
                self.current_contacts[side].append(
                    {
                        "normal_force_n": force,
                        "contact_dimension": int(contact.dim),
                        "friction_coefficients": contact.friction.tolist(),
                        "normal_torque_magnitude_nm": abs(float(wrench[3])),
                        "normal_on_fruit": normal.tolist(),
                        "position_m": contact.pos.tolist(),
                        "local_position_m": local.tolist(),
                    }
                )
            elif (
                (a in self.robot_geoms and b in self.obstacles)
                or (b in self.robot_geoms and a in self.obstacles)
                or (a in self.robot_geoms and b in self.robot_geoms)
            ):
                self.forbidden_contacts.add(tuple(sorted((self._label(a), self._label(b)))))
        for side, force in finger_forces.items():
            self.peak_finger_force[side] = max(self.peak_finger_force[side], force)
            if force > MAX_FINGER_FORCE_N:
                self.limit_violations.add("excessive_model_finger_force")
        self.early_closure |= (
            self.requires_pregrasp_pose and self.ready_step is None and self.opening() < 0.90
        )
        witness = self._bilateral_witness()
        now = float(self.sim.data.time)
        eligible = (
            (not self.requires_pregrasp_pose or self.ready_step is not None)
            and self.clean()
            and witness is not None
        )
        if eligible:
            if self.contact_start_time is None:
                self.contact_start_time = now
            duration = now - self.contact_start_time
            self.longest_contact_duration_s = max(self.longest_contact_duration_s, duration)
            if self.grasp_time is None and duration + 1e-9 >= CONTACT_HOLD_SECONDS:
                self.grasp_time = now
                self.grasp_witness = witness
        else:
            self.contact_start_time = None
        if (
            self.grasp_time is not None
            and self.release_time is None
            and self.clean()
            and self.opening() > 0.97
            and not any(self.current_contacts.values())
        ):
            self.release_time = now

    def clean(self) -> bool:
        return not self.forbidden_contacts and not self.limit_violations and not self.early_closure

    def fruit_position(self) -> np.ndarray:
        return np.asarray(FRUIT_POSITION)

    def _bilateral_witness(self) -> dict | None:
        centers, normals, forces = {}, {}, {}
        for side, contacts in self.current_contacts.items():
            active = [c for c in contacts if c["normal_force_n"] > 0]
            force = sum(c["normal_force_n"] for c in active)
            if force < MIN_FINGER_FORCE_N:
                return None
            forces[side] = force
            centers[side] = (
                sum(np.array(c["position_m"]) * c["normal_force_n"] for c in active) / force
            )
            normal = sum(np.array(c["normal_on_fruit"]) * c["normal_force_n"] for c in active)
            norm = np.linalg.norm(normal)
            if norm < 1e-9:
                return None
            normals[side] = normal / norm
        opposition = float(normals["fixed"] @ normals["moving"])
        offsets = {side: centers[side] - self.fruit_position() for side in centers}
        across = float(offsets["fixed"] @ offsets["moving"])
        separation = float(np.linalg.norm(centers["fixed"] - centers["moving"]))
        if opposition > -0.5 or across >= 0 or separation < 0.02:
            return None
        return {
            "finger_forces_n": forces,
            "normal_dot_product": opposition,
            "contact_separation_m": separation,
            "contacts": self.current_contacts,
        }

    def _after_control_step(self) -> None:
        tcp = self.sim.data.get_site_xpos("so101_gripperframe")
        rotation = self.sim.data.get_site_xmat("so101_gripperframe")
        relative = (self.fruit_position() - tcp) @ rotation
        settled = np.max(np.abs(self.sim.data.qvel[self.qvel_indexes[:5]])) < 0.08
        ready = (
            self.clean()
            and settled
            and self.opening() > 0.97
            and np.linalg.norm(relative - self.grasp_offset) <= 0.008
        )
        self.ready_streak = self.ready_streak + 1 if ready else 0
        if self.ready_step is None and self.ready_streak >= self.required_pose_ticks:
            self.ready_step = self.elapsed
        returned = (
            np.linalg.norm(tcp - self.initial_tool_position) <= 0.008
            and np.max(np.abs(self.sim.data.qpos[self.qpos_indexes[:5]] - self.home)) <= 0.01
        )
        completed = (
            self.clean()
            and settled
            and returned
            and self.release_time is not None
            and self.opening() > 0.97
            and not any(self.current_contacts.values())
        )
        self.retreat_streak = self.retreat_streak + 1 if completed else 0
        if self.retreat_step is None and self.retreat_streak >= self.required_pose_ticks:
            self.retreat_step = self.elapsed

    def _check_success(self) -> bool:
        return bool(
            self.clean()
            and self.grasp_time is not None
            and self.release_time is not None
            and self.retreat_streak >= self.required_pose_ticks
        )

    def task_evidence(self) -> dict:
        return {
            "task": "so101_strawberry_grasp_contact",
            "task_success": self._check_success(),
            "scope": "attached rigid fruit; bilateral contact, reopen and retreat; no detached retention",
            "ready_step": self.ready_step,
            "grasp_verified_time_s": self.grasp_time,
            "release_verified_time_s": self.release_time,
            "retreat_verified_step": self.retreat_step,
            "contact_hold_required_s": CONTACT_HOLD_SECONDS,
            "longest_bilateral_contact_s": self.longest_contact_duration_s,
            "grasp_witness": self.grasp_witness,
            "peak_finger_forces_n": self.peak_finger_force,
            "force_limit_n": MAX_FINGER_FORCE_N,
            "force_limit_calibrated_for_real_fruit": False,
            "maximum_contact_penetration_m": self.max_penetration,
            "penetration_limit_m": MAX_PENETRATION_M,
            "forbidden_contact_pairs": sorted(self.forbidden_contacts),
            "limit_violations": sorted(self.limit_violations),
            "early_closure": self.early_closure,
            "final_gripper_opening": self.opening(),
            "final_retreat_error_m": float(
                np.linalg.norm(
                    self.sim.data.get_site_xpos("so101_gripperframe") - self.initial_tool_position
                )
            ),
            "physics_monitor_period_s": float(self.model.opt.timestep),
            "robot_model_modified": False,
            "fruit_detached": False,
        }
