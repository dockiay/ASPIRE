"""Carry a free strawberry, release over a tray, and verify stable placement."""

from __future__ import annotations

import numpy as np

from cap_harness.so101.retention import (
    RETENTION_SECONDS,
    SO101StrawberryRetentionTorsionEnvironment,
)

CONTAINER_CENTER = (0.245, -0.16)
CONTAINER_INNER_HALF_SIZE = (0.070, 0.065)
CONTAINER_FLOOR_Z = 0.016
CONTAINER_RIM_Z = 0.096
RELEASE_HEIGHT_M = 0.13
PLACEMENT_HOLD_S = 1.0


def add_container(scene, center=CONTAINER_CENTER) -> None:
    import mujoco

    body = scene.worldbody.add_body(name="lesson_container", pos=[*center, 0])
    parts = (
        ("base", (0.080, 0.075, 0.008), (0, 0, 0.008)),
        ("left", (0.005, 0.075, 0.040), (-0.075, 0, 0.056)),
        ("right", (0.005, 0.075, 0.040), (0.075, 0, 0.056)),
        ("front", (0.070, 0.005, 0.040), (0, -0.070, 0.056)),
        ("back", (0.070, 0.005, 0.040), (0, 0.070, 0.056)),
    )
    for name, size, position in parts:
        contact = {}
        if name == "base":
            # Explicit tray surface model: activate the existing rolling-friction
            # coefficient only on the base. No free-body damping or pose fixing.
            contact = {
                "priority": 2,
                "condim": 6,
                "solref": [0.004, 1],
                "friction": [1, 0.005, 0.0001],
            }
        body.add_geom(
            name="container_" + name,
            type=mujoco.mjtGeom.mjGEOM_BOX,
            size=size,
            pos=position,
            rgba=[0.10, 0.36, 0.58, 1],
            **contact,
        )


class SO101StrawberryTransportEnvironment(SO101StrawberryRetentionTorsionEnvironment):
    task_name = "so101_strawberry_transport"
    container_center = CONTAINER_CENTER
    stationary_free_hold = True
    penalize_opening_command_outside_destination = True
    camera_target = (0.25, -0.035, 0.16)
    camera_positions = (("agentview", (0.65, -0.75, 0.54)), ("sideview", (0.26, 0.80, 0.48)))

    def configure_scene(self, scene) -> None:
        super().configure_scene(scene)
        add_container(scene)

    @classmethod
    def lesson_metadata(cls) -> dict:
        return {
            **super().lesson_metadata(),
            "container_center_xy_m": CONTAINER_CENTER,
            "container_inner_half_size_m": CONTAINER_INNER_HALF_SIZE,
            "container_floor_z_m": CONTAINER_FLOOR_Z,
            "container_rim_z_m": CONTAINER_RIM_Z,
            "release_fruit_center_z_m": RELEASE_HEIGHT_M,
            "placement_hold_seconds": PLACEMENT_HOLD_S,
            "transport_minimum_distance_m": 0.15,
            "container_base_contact_dimension": 6,
            "container_base_friction": (1.0, 0.005, 0.0001),
            "scene_variation": "fixed lesson; timed fruit release, carry and tray placement",
        }

    def retention_monitor_active(self) -> bool:
        return self.deposit_started_time is None

    def allowed_support_geoms(self) -> set[int]:
        return self.container_geoms if self.deposit_started_time is not None else set()

    def release_opening_requested(self, opening_target: float) -> bool:
        return opening_target > 0.29

    def _reset_task_state(self) -> None:
        self.container_geoms = {
            self.model.geom("container_" + name).id
            for name in ("base", "left", "right", "front", "back")
        }
        self.container_base_geom = self.model.geom("container_base").id
        self.free_hold_verified_time = None
        self.destination_ready_time = None
        self.destination_hold_start = None
        self.deposit_started_time = None
        self.placement_start = None
        self.placement_duration = 0.0
        self.first_base_contact_time = None
        self.transport_violations: set[str] = set()
        self.maximum_transport_distance = 0.0
        self.transport_witness = None
        super()._reset_task_state()

    def task_clean(self) -> bool:
        return (
            self.clean()
            and not self.support_contacts
            and not self.retention_violations
            and not self.transport_violations
        )

    def over_destination(self) -> bool:
        return bool(
            np.linalg.norm(self.fruit_position()[:2] - CONTAINER_CENTER) <= 0.012
            and abs(self.fruit_position()[2] - RELEASE_HEIGHT_M) <= 0.008
        )

    def fruit_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        # Every moving fruit geom is an ellipsoid or sphere. Include calyx/seeds,
        # not just the free body's origin, when checking containment.
        lows, highs = [], []
        for geom in self.all_fruit_geoms:
            rotation = self.sim.data.geom_xmat[geom].reshape(3, 3)
            size = self.model.geom_size[geom].copy()
            if self.model.geom(geom).name.startswith("plant_seed_"):
                size[:] = size[0]
            extent = np.sqrt((rotation * size) ** 2 @ np.ones(3))
            center = self.sim.data.geom_xpos[geom]
            lows.append(center - extent)
            highs.append(center + extent)
        return np.min(lows, axis=0), np.max(highs, axis=0)

    def base_support_force_n(self) -> float:
        import mujoco

        force = 0.0
        for index, contact in enumerate(self.sim.data.contact):
            pair = (int(contact.geom1), int(contact.geom2))
            if (
                contact.dist <= 0
                and self.container_base_geom in pair
                and (set(pair) & self.all_fruit_geoms)
            ):
                wrench = np.zeros(6)
                mujoco.mj_contactForce(self.model, self.sim.data._data, index, wrench)
                force += max(0.0, float(wrench[0]))
        return force

    def has_base_contact(self) -> bool:
        return self.base_support_force_n() >= 0.05

    def placement_predicate(self) -> bool:
        if self.deposit_started_time is None or not self.task_clean():
            return False
        low, high = self.fruit_bounds()
        inner_low = np.array(self.container_center) - CONTAINER_INNER_HALF_SIZE
        inner_high = np.array(self.container_center) + CONTAINER_INNER_HALF_SIZE
        velocity = self.sim.data.qvel[self.fruit_dof : self.fruit_dof + 6]
        tcp = self.sim.data.get_site_xpos("so101_gripperframe")
        return bool(
            np.all(low[:2] >= inner_low - 0.0015)
            and np.all(high[:2] <= inner_high + 0.0015)
            and low[2] >= CONTAINER_FLOOR_Z - 0.0015
            and high[2] <= CONTAINER_RIM_Z + 0.0015
            and self.has_base_contact()
            and np.linalg.norm(velocity[:3]) <= 0.02
            and np.linalg.norm(velocity[3:]) <= 0.15
            and self.opening() > 0.97
            and not any(self.current_contacts.values())
            and np.linalg.norm(tcp - self.fruit_position()) >= 0.08
        )

    def _after_physics_step(self) -> None:
        self.sim.forward()
        self.obstacles.update(self.container_geoms)
        now = float(self.sim.data.time)
        low, high = self.action_spec
        opening_target = (self.sim.data.ctrl[self.actuator_ids[5]] - low[5]) / (high[5] - low[5])
        # Recognize the actual opening command at the verified destination before
        # contacts disappear. Opening elsewhere remains a failed transport.
        if self.detached_time is not None and self.deposit_started_time is None:
            if self.release_opening_requested(opening_target):
                if (
                    self.destination_ready_time is not None
                    and self.over_destination()
                    and self.task_clean()
                ):
                    self.deposit_started_time = now
                elif self.penalize_opening_command_outside_destination:
                    self.transport_violations.add("opened_before_verified_destination")
        super()._after_physics_step()
        if self.detached_time is None:
            return
        distance = float(np.linalg.norm(self.fruit_position() - self.release_world_position))
        if self.deposit_started_time is None:
            self.maximum_transport_distance = max(self.maximum_transport_distance, distance)
            if self.task_clean() and self.current_retention_duration + 1e-9 >= RETENTION_SECONDS:
                if self.free_hold_verified_time is None:
                    self.free_hold_verified_time = now
            if (
                self.stationary_free_hold
                and self.free_hold_verified_time is None
                and distance > 0.020
            ):
                self.transport_violations.add("transport_before_verified_free_hold")
            settled = np.max(np.abs(self.sim.data.qvel[self.qvel_indexes[:5]])) < 0.08
            at_destination = (
                self.task_clean()
                and self.free_hold_verified_time is not None
                and distance >= 0.15
                and self.over_destination()
                and settled
                and self._bilateral_witness() is not None
            )
            if at_destination:
                if self.destination_hold_start is None:
                    self.destination_hold_start = now
                if (
                    self.destination_ready_time is None
                    and now - self.destination_hold_start >= 0.25
                ):
                    self.destination_ready_time = now
                    self.transport_witness = self._bilateral_witness()
            else:
                self.destination_hold_start = None
        if self.deposit_started_time is not None and self.has_base_contact():
            if self.first_base_contact_time is None:
                self.first_base_contact_time = now
        if self.placement_predicate():
            if self.placement_start is None:
                self.placement_start = now
            self.placement_duration = now - self.placement_start
        else:
            self.placement_start = None
            self.placement_duration = 0.0

    def _after_control_step(self) -> None:
        super()._after_control_step()
        self.trace[-1].update(
            deposit_started=self.deposit_started_time is not None,
            placement_hold_s=self.placement_duration,
            container_base_contact=self.has_base_contact(),
        )

    def _check_success(self) -> bool:
        return bool(
            self.destination_ready_time is not None
            and self.placement_duration + 1e-9 >= PLACEMENT_HOLD_S
            and self.placement_predicate()
        )

    def task_evidence(self) -> dict:
        low, high = self.fruit_bounds()
        base_contacts = [
            c
            for c in self.sim.data.contact
            if c.dist <= 0
            and self.container_base_geom in (int(c.geom1), int(c.geom2))
            and bool({int(c.geom1), int(c.geom2)} & self.all_fruit_geoms)
        ]
        return {
            **super().task_evidence(),
            "scope": "timed release, free carry and stable tray placement; uncalibrated torsional contact",
            "free_hold_verified_time_s": self.free_hold_verified_time,
            "destination_ready_time_s": self.destination_ready_time,
            "deposit_started_time_s": self.deposit_started_time,
            "first_container_base_contact_time_s": self.first_base_contact_time,
            "placement_hold_s": self.placement_duration,
            "placement_hold_required_s": PLACEMENT_HOLD_S,
            "maximum_carried_distance_m": self.maximum_transport_distance,
            "transport_violations": sorted(self.transport_violations),
            "transport_contact_witness": self.transport_witness,
            "container_center_xy_m": self.container_center,
            "container_inner_half_size_m": CONTAINER_INNER_HALF_SIZE,
            "container_floor_z_m": CONTAINER_FLOOR_Z,
            "container_rim_z_m": CONTAINER_RIM_Z,
            "final_fruit_bounds_m": [low.tolist(), high.tolist()],
            "final_container_base_contact": self.has_base_contact(),
            "final_container_base_support_force_n": self.base_support_force_n(),
            "final_container_contact_dimensions": [int(c.dim) for c in base_contacts],
            "final_container_contact_friction": [c.friction.tolist() for c in base_contacts],
            "container_base_contact_dimension": int(
                self.model.geom_condim[self.container_base_geom]
            ),
            "container_base_friction": self.model.geom_friction[self.container_base_geom].tolist(),
            "final_tool_to_fruit_distance_m": float(
                np.linalg.norm(
                    self.sim.data.get_site_xpos("so101_gripperframe") - self.fruit_position()
                )
            ),
            "final_placement_predicate": self.placement_predicate(),
        }
