"""Timed fixture release and gravity retention; no stem fracture or hand attachment."""

from __future__ import annotations

import numpy as np

from cap_harness.so101.grasp_contact import SO101StrawberryGraspContactEnvironment
from cap_harness.so101.strawberry import add_strawberry_plant

FIXTURE_RELEASE_S = 8.0
RETENTION_SECONDS = 2.0
MAX_SLIP_M = 0.008


class SO101StrawberryRetentionEnvironment(SO101StrawberryGraspContactEnvironment):
    contact_dimension = 3
    task_name = "so101_strawberry_retention"

    def configure_scene(self, scene) -> None:
        add_strawberry_plant(scene, dynamic_fruit=True, contact_dimension=self.contact_dimension)

    @classmethod
    def lesson_metadata(cls) -> dict:
        return {
            **SO101StrawberryGraspContactEnvironment.lesson_metadata(),
            "scene_variation": "fixed lesson; 20 g rigid fruit with timed plant fixture",
            "fixture_release_time_s": FIXTURE_RELEASE_S,
            "retention_seconds": RETENTION_SECONDS,
            "maximum_relative_slip_m": MAX_SLIP_M,
            "release_mechanism": "automatic test fixture; not a model of stem fracture",
            "contact_dimension": cls.contact_dimension,
            "torsional_contact_friction": cls.contact_dimension == 4,
            "contact_parameters_calibrated": False,
        }

    def fruit_position(self) -> np.ndarray:
        return self.sim.data.body_xpos[self.fruit_body_id].copy()

    def fruit_relative_position(self) -> np.ndarray:
        tcp = self.sim.data.get_site_xpos("so101_gripperframe")
        rotation = self.sim.data.get_site_xmat("so101_gripperframe")
        return (self.fruit_position() - tcp) @ rotation

    def retention_monitor_active(self) -> bool:
        return True

    def allowed_support_geoms(self) -> set[int]:
        return set()

    def _reset_task_state(self) -> None:
        self.fruit_body_id = self.model.body("lesson_fruit").id
        self.fixture_id = self.model.equality("fruit_fixture").id
        self.fruit_joint_id = self.model.joint("fruit_free").id
        self.fruit_dof = int(self.model.jnt_dofadr[self.fruit_joint_id])
        self.all_fruit_geoms = set(np.flatnonzero(self.model.geom_bodyid == self.fruit_body_id))
        self.detached_time = None
        self.release_relative_position = None
        self.release_world_position = None
        self.retention_start = None
        self.current_retention_duration = 0.0
        self.longest_retention_duration = 0.0
        self.maximum_relative_slip = 0.0
        self.support_contacts: set[tuple[str, str]] = set()
        self.retention_violations: set[str] = set()
        self.first_slip_time = None
        self.retention_samples = 0
        self.trace = []
        super()._reset_task_state()

    def _after_physics_step(self) -> None:
        now = float(self.sim.data.time)
        # Environment release policy is independent of the program and its success.
        # qpos/qvel are untouched: motion after this point is governed by physics.
        if self.detached_time is None and self._release_due():
            self.sim.forward()
            self.sim.data._data.eq_active[self.fixture_id] = False
            self.detached_time = now
            self.release_relative_position = self.fruit_relative_position()
            self.release_world_position = self.fruit_position()
            if self.grasp_time is None:
                self.retention_violations.add("fixture_released_without_qualified_grasp")
        # Refresh forces AFTER disabling the fixture, so the first retention
        # sample cannot reuse contacts/loads from the attached state.
        super()._after_physics_step()
        if self.detached_time is None:
            return
        if self.sim.data._data.eq_active[self.fixture_id]:
            self.retention_violations.add("fixture_reactivated")
        # Any non-finger support of any fruit part is disallowed, including the calyx.
        for contact in self.sim.data.contact:
            if contact.dist > 0:
                continue
            a, b = int(contact.geom1), int(contact.geom2)
            if (a in self.all_fruit_geoms) == (b in self.all_fruit_geoms):
                continue
            other = b if a in self.all_fruit_geoms else a
            if other not in self.fingers.values() and other not in self.allowed_support_geoms():
                self.support_contacts.add(tuple(sorted((self._label(a), self._label(b)))))
        slip = float(
            np.linalg.norm(self.fruit_relative_position() - self.release_relative_position)
        )
        if self.retention_monitor_active():
            self.maximum_relative_slip = max(self.maximum_relative_slip, slip)
        if self.retention_monitor_active() and slip > MAX_SLIP_M:
            self.retention_violations.add("fruit_slipped_or_dropped")
            if self.first_slip_time is None:
                self.first_slip_time = now
        if np.any(self.sim.data._data.xfrc_applied[self.fruit_body_id]):
            self.retention_violations.add("external_force_on_fruit")
        if np.any(self.sim.data.qfrc_applied[self.fruit_dof : self.fruit_dof + 6]):
            self.retention_violations.add("external_generalized_force_on_fruit")
        if not np.allclose(self.model.opt.gravity, [0, 0, -9.81]):
            self.retention_violations.add("gravity_changed")
        eligible = (
            self.retention_monitor_active()
            and self.clean()
            and not self.support_contacts
            and not self.retention_violations
            and not self.sim.data._data.eq_active[self.fixture_id]
            and self._bilateral_witness() is not None
        )
        if eligible:
            self.retention_samples += 1
            if self.retention_start is None:
                self.retention_start = now
            self.current_retention_duration = now - self.retention_start
            self.longest_retention_duration = max(
                self.longest_retention_duration, self.current_retention_duration
            )
        else:
            self.retention_start = None
            self.current_retention_duration = 0.0

    def _release_due(self) -> bool:
        """Override for other attachment experiments; the original stays timed."""
        return float(self.sim.data.time) + 1e-9 >= FIXTURE_RELEASE_S

    def _after_control_step(self) -> None:
        super()._after_control_step()
        self.trace.append(
            {
                "time_s": float(self.sim.data.time),
                "fruit_position_m": self.fruit_position().tolist(),
                "fruit_relative_to_tool_m": self.fruit_relative_position().tolist(),
                "fixture_active": bool(self.sim.data._data.eq_active[self.fixture_id]),
                "bilateral_contacts": self._bilateral_witness() is not None,
                "finger_forces_n": {
                    side: sum(c["normal_force_n"] for c in contacts)
                    for side, contacts in self.current_contacts.items()
                },
                "current_retention_s": self.current_retention_duration,
            }
        )

    def _check_success(self) -> bool:
        return bool(
            self.detached_time is not None
            and not self.sim.data._data.eq_active[self.fixture_id]
            and self.clean()
            and not self.support_contacts
            and not self.retention_violations
            and self.current_retention_duration + 1e-9 >= RETENTION_SECONDS
            and self._bilateral_witness() is not None
        )

    def task_evidence(self) -> dict:
        parent = super().task_evidence()
        return {
            **{
                k: v
                for k, v in parent.items()
                if k
                not in {"release_verified_time_s", "retreat_verified_step", "final_retreat_error_m"}
            },
            "task": self.task_name,
            "scope": "timed fixture release and gravity retention; no stem fracture or transport",
            "fruit_detached": self.detached_time is not None,
            "fixture_active": bool(self.sim.data._data.eq_active[self.fixture_id]),
            "fixture_release_time_s": self.detached_time,
            "required_retention_s": RETENTION_SECONDS,
            "current_retention_s": self.current_retention_duration,
            "longest_retention_s": self.longest_retention_duration,
            "maximum_relative_slip_m": self.maximum_relative_slip,
            "first_slip_time_s": self.first_slip_time,
            "relative_slip_limit_m": MAX_SLIP_M,
            "unsupported_contact_samples": self.retention_samples,
            "non_finger_support_contacts": sorted(self.support_contacts),
            "retention_violations": sorted(self.retention_violations),
            "fruit_mass_kg": float(self.model.body_mass[self.fruit_body_id]),
            "gravity_m_s2": self.model.opt.gravity.tolist(),
            "fruit_collision_friction": self.model.geom_friction[sorted(self.fruit_geoms)].tolist(),
            "fruit_contact_dimension": self.model.geom_condim[sorted(self.fruit_geoms)].tolist(),
            "contact_parameters_calibrated": False,
            "robot_geometry_and_actuators_modified": False,
            "torsional_contact_friction": self.contact_dimension == 4,
            "release_fruit_position_m": (
                None
                if self.release_world_position is None
                else self.release_world_position.tolist()
            ),
            "release_fruit_relative_to_tool_m": (
                None
                if self.release_relative_position is None
                else self.release_relative_position.tolist()
            ),
            "final_fruit_position_m": self.fruit_position().tolist(),
            "final_fruit_velocity": self.sim.data.qvel[
                self.fruit_dof : self.fruit_dof + 6
            ].tolist(),
            "final_fruit_relative_to_tool_m": self.fruit_relative_position().tolist(),
            "final_contact_witness": self._bilateral_witness(),
            "fixture_body_ids": self.model.eq_obj1id.tolist() + self.model.eq_obj2id.tolist(),
            "trace": self.trace,
        }


class SO101StrawberryRetentionTorsionEnvironment(SO101StrawberryRetentionEnvironment):
    """Same experiment with uncalibrated finite-patch torsional contact friction."""

    contact_dimension = 4
    task_name = "so101_strawberry_retention_torsion"
