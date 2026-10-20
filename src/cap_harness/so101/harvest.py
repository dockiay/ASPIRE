"""One persistent FruitGym fruit: mechanical release, retention, carry and deposit."""

import numpy as np

from cap_harness.so101.detachment import SO101StrawberryDetachmentEnvironment
from cap_harness.so101.fruitgym_plant import add_fruitgym_plant
from cap_harness.so101.transport import (
    CONTAINER_CENTER,
    CONTAINER_FLOOR_Z,
    CONTAINER_INNER_HALF_SIZE,
    CONTAINER_RIM_Z,
    SO101StrawberryTransportEnvironment,
    add_container,
)


class SO101FruitGymHarvestEnvironment(
    SO101StrawberryTransportEnvironment, SO101StrawberryDetachmentEnvironment
):
    task_name = "so101_fruitgym_harvest"
    requires_pregrasp_pose = False
    stationary_free_hold = False
    penalize_opening_command_outside_destination = False

    def __init__(self, *, seed=0, **kwargs):
        from cap_harness.so101.harvest_protocol import case_for, protocol

        self.case = case_for(seed)
        self.case_protocol_snapshot = protocol()
        self.container_center = tuple(np.array(CONTAINER_CENTER) + self.case["container_offset_m"])
        self.bent_force_n *= self.case["release_load_scale"]
        self.straight_force_n *= self.case["release_load_scale"]
        super().__init__(**kwargs)

    def configure_scene(self, scene):
        self.plant_source = add_fruitgym_plant(scene)
        offset = np.asarray(self.case["plant_offset_m"])
        for name in ("lesson_plant", "lesson_fruit"):
            body = scene.body(name)
            body.pos = np.asarray(body.pos) + offset
        scene.geom("plant_fruit").friction = [self.case["fruit_friction"], 0.005, 0.0001]
        add_container(scene, self.container_center)

    @classmethod
    def lesson_metadata(cls):
        metadata = super().lesson_metadata()
        for key in (
            "fruit_center_m",
            "fruit_center_in_tool_m",
            "container_center_xy_m",
            "container_inner_half_size_m",
            "container_floor_z_m",
            "container_rim_z_m",
            "release_fruit_center_z_m",
            "container_base_friction",
            "container_base_contact_dimension",
            "bent_load_threshold_n",
            "straight_load_threshold_n",
            "bend_trial_deg",
        ):
            metadata.pop(key, None)
        return {
            **metadata,
            "target_source": "public cameras; no supplied fruit coordinates",
            "scene_variation": "versioned plant/container offsets and synthetic contact/release variation",
            "protocol": "so101-fruitgym-harvest-v2",
            "release_mechanism": "uncalibrated load and relative motion proxy; never timed",
            "release_model_scope": {
                "modeled": ["bending with outward traction", "straight outward traction"],
                "axial_torsion_fracture_modeled": False,
                "biologically_calibrated": False,
                "interpretation": "Axial rotation alone has no fracture law in this benchmark. FruitGym supplies visual assets; tissue mechanics are a synthetic proxy.",
            },
            "plant_dynamics": "rigid stems/leaves, one releasable free fruit",
            "fruit_replacement_or_teleport": False,
            "grasp_qualification": "opposing distal contacts >=0.1 N each, separation >=20 mm, sustained 0.5 s; no prescribed approach pose",
            "maximum_contact_penetration_m": 0.0015,
            "maximum_relative_slip_m": 0.008,
            "destination_qualification": "whole fruit XY bounds inside tray interior, fruit bottom above floor and at most 0.15 m above rim; settled bilateral hold 0.25 s",
            "free_hold_may_overlap_transport": True,
            "maximum_release_clearance_above_rim_m": 0.15,
        }

    def over_destination(self):
        low, high = self.fruit_bounds()
        center = np.asarray(self.container_center)
        half = np.asarray(CONTAINER_INNER_HALF_SIZE)
        return bool(
            np.all(low[:2] >= center - half - 0.0015)
            and np.all(high[:2] <= center + half + 0.0015)
            and low[2] >= CONTAINER_FLOOR_Z - 0.0015
            and low[2] <= CONTAINER_RIM_Z + 0.15
        )

    def _reset_task_state(self):
        from cap_harness.so101.effector import EffectorGeometry

        self.effector_geometry = EffectorGeometry()
        super()._reset_task_state()

    def fingertip_contact(self, side, world_position, tcp_position):
        geom = self.fingers[side]
        rotation = self.sim.data.geom_xmat[geom].reshape(3, 3)
        local = (world_position - self.sim.data.geom_xpos[geom]) @ rotation
        return self.effector_geometry.pad_contains(side, local)

    def requires_safe_continuation(self):
        if self.forbidden_contacts:
            self.safety_stop = "forbidden_robot_contact"
        elif self.limit_violations:
            self.safety_stop = sorted(self.limit_violations)[0]
        elif self.retention_violations or self.support_contacts or self.transport_violations:
            self.safety_stop = "episode_constraint_violation"
        return self.safety_stop is None

    def release_opening_requested(self, opening_target):
        # Gradual opening must count too. Loss of opposing contacts over the
        # verified tray is physical release even without a particular command.
        return opening_target > self.opening() + 0.0001 or (
            self.destination_ready_time is not None and self._bilateral_witness() is None
        )

    def allowed_support_geoms(self):
        if self.free_hold_verified_time is not None and self.over_destination():
            return self.container_geoms
        return set()

    def _after_physics_step(self):
        super()._after_physics_step()
        if self.first_base_contact_time is None and self.has_base_contact():
            self.first_base_contact_time = float(self.sim.data.time)
            self.diagnostic_monitor.record(
                self, "container_base_contact", once_key="container_base_contact"
            )

    def fruit_bounds(self):
        # Compiled MuJoCo mesh vertices share geom_xpos/geom_xmat's local frame.
        points = []
        for geom in self.all_fruit_geoms:
            mesh = int(self.model.geom_dataid[geom])
            start = int(self.model.mesh_vertadr[mesh])
            count = int(self.model.mesh_vertnum[mesh])
            vertices = self.model.mesh_vert[start : start + count]
            rotation = self.sim.data.geom_xmat[geom].reshape(3, 3)
            points.append(vertices @ rotation.T + self.sim.data.geom_xpos[geom])
        points = np.concatenate(points)
        return points.min(0), points.max(0)

    def ordered_stages_complete(self):
        times = [
            self.grasp_time,
            self.detached_time,
            self.free_hold_verified_time,
            self.destination_ready_time,
            self.deposit_started_time,
        ]
        return (
            self.release_event is not None
            and all(t is not None for t in times)
            and all(before <= after for before, after in zip(times, times[1:]))
            and self.first_base_contact_time is not None
            and self.first_base_contact_time >= self.free_hold_verified_time
        )

    def _check_success(self):
        return bool(
            self.ordered_stages_complete()
            and not self.sim.data._data.eq_active[self.fixture_id]
            and super()._check_success()
        )

    def task_evidence(self):
        evidence = super().task_evidence()
        # The detachment-only diagnostic's final-retention contract does not describe deposit.
        evidence.pop("diagnostics", None)
        if self._check_success():
            stage = "completed"
        elif self.deposit_started_time is not None:
            stage = "stable_placement_and_withdrawal"
        elif self.free_hold_verified_time is not None:
            stage = "transport_and_release"
        elif self.detached_time is not None:
            stage = "free_retention"
        elif self.grasp_time is not None:
            stage = "mechanical_detachment"
        else:
            stage = "approach_and_grasp"
        evidence = {
            **evidence,
            "scope": "FruitGym assets; continuous mechanical harvest, carry and deposit",
            "protocol": "so101-fruitgym-harvest-v2",
            "stage": stage,
            "task_success": self._check_success(),
            "plant_source": self.plant_source,
            "ordered_stages_complete": self.ordered_stages_complete(),
            "persistent_fruit_body_id": int(self.fruit_body_id),
            "fruit_deleted_or_replaced": False,
            "evaluation_partition": self.case["partition"],
            "case": self.case,
        }
        from cap_harness.so101.harvest_feedback import diagnostics

        evidence["diagnostics"] = diagnostics(self, evidence)
        return evidence
