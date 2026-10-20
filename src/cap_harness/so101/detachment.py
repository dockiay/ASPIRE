"""Evidence-informed release proxy, NOT an identified biological fracture law.

A native point constraint at the calyx allows rotation under gravity/contact.
It supplies measured reaction forces and is removed without changing qpos/qvel.
Unknown tissue stiffness, angular threshold and rate effects remain explicit.
"""

from __future__ import annotations

import numpy as np

from cap_harness.so101.diagnostics import DetachmentDiagnostics
from cap_harness.so101.retention import SO101StrawberryRetentionTorsionEnvironment
from cap_harness.so101.strawberry import add_strawberry_plant

# Dimeas et al., DOI 10.1017/S0263574714001155, Table 1, unpaired samples.
BENT_FORCE_SAMPLES_N = (2.78, 3.76, 2.31, 1.57, 5.10, 3.53)
STRAIGHT_FORCE_SAMPLES_N = (22.0, 10.0, 9.81)
BEND_TRIAL_DEG = 70.0  # Yamamoto 2014 robot manoeuvre, NOT a fracture angle.
MIN_EXTENSION_M = 0.0001  # Numerical tensile-direction gate, NOT tissue strain.


def release_regime(
    angle_deg: float,
    load_n: float,
    extension_m: float,
    outward_work_j: float,
    *,
    bent_force_n: float,
    straight_force_n: float,
    bend_trial_deg: float,
) -> str | None:
    """Two explicit benchmark regimes; no fitted interpolation between them."""
    if not np.isfinite([angle_deg, load_n, extension_m, outward_work_j]).all():
        return None
    if extension_m < MIN_EXTENSION_M or outward_work_j <= 0:
        return None
    if angle_deg >= bend_trial_deg and load_n >= bent_force_n:
        return "bend_and_pull_proxy"
    if angle_deg <= 15 and load_n >= straight_force_n:
        return "straight_pull_proxy"
    return None


class SO101StrawberryDetachmentEnvironment(SO101StrawberryRetentionTorsionEnvironment):
    task_name = "so101_strawberry_detachment"
    camera_target = (0.31, 0, 0.20)
    camera_positions = (("agentview", (0.68, -0.67, 0.52)), ("sideview", (0.28, 0.48, 0.36)))
    bent_force_n = float(np.mean(BENT_FORCE_SAMPLES_N))
    straight_force_n = float(np.mean(STRAIGHT_FORCE_SAMPLES_N))
    bend_trial_deg = BEND_TRIAL_DEG

    def configure_scene(self, scene) -> None:
        add_strawberry_plant(
            scene, dynamic_fruit=True, contact_dimension=4, releasable_junction=True
        )

    @classmethod
    def lesson_metadata(cls) -> dict:
        parent = super().lesson_metadata()
        parent.pop("fixture_release_time_s")
        return {
            **parent,
            "scene_variation": "single fruit; load-released point junction",
            "release_mechanism": "uncalibrated bend/pull benchmark proxy",
            "bend_trial_deg": cls.bend_trial_deg,
            "bent_load_threshold_n": cls.bent_force_n,
            "straight_load_threshold_n": cls.straight_force_n,
            "biological_fracture_calibrated": False,
        }

    def _reset_task_state(self) -> None:
        self.junction_anchor = self.model.body_pos[self.model.body("lesson_fruit").id].copy() + [
            0,
            0,
            0.024,
        ]
        self.release_event = None
        self.junction_samples = []
        self.last_attached_junction_state = None
        self.maximum_bend_deg = 0.0
        self.maximum_load_n = 0.0
        self.minimum_joint_limit_margin_rad = float("inf")
        self.maximum_arm_speed_rad_s = 0.0
        self.motion_samples = []
        self.diagnostic_monitor = DetachmentDiagnostics()
        super()._reset_task_state()

    def _after_physics_step(self) -> None:
        super()._after_physics_step()
        positions = self.sim.data.qpos[self.qpos_indexes[:5]]
        limits = self.model.jnt_range[self.joint_ids[:5]]
        margin = float(np.min(np.minimum(positions - limits[:, 0], limits[:, 1] - positions)))
        self.minimum_joint_limit_margin_rad = min(self.minimum_joint_limit_margin_rad, margin)
        self.maximum_arm_speed_rad_s = max(
            self.maximum_arm_speed_rad_s,
            float(np.max(np.abs(self.sim.data.qvel[self.qvel_indexes[:5]]))),
        )
        self.diagnostic_monitor.sample(self)

    def junction_state(self) -> dict:
        import mujoco

        data = self.sim.data._data
        rotation = data.xmat[self.fruit_body_id].reshape(3, 3)
        point = self.fruit_position() + rotation @ np.array([0, 0, 0.024])
        displacement = point - self.junction_anchor
        mask = (data.efc_type == mujoco.mjtConstraint.mjCNSTR_EQUALITY) & (
            data.efc_id == self.fixture_id
        )
        force = np.zeros(data.nefc)
        force[mask] = data.efc_force[mask]
        generalized = np.zeros(self.model.nv)
        mujoco.mj_mulJacTVec(self.model, data, generalized, force)
        reaction = generalized[self.fruit_dof : self.fruit_dof + 3]
        # Match weight-compensated force-gauge experiments. This does not remove
        # inertial force: speed sensitivity is an unresolved modelling limitation.
        weight_support = np.array([0, 0, self.model.body_mass[self.fruit_body_id] * 9.81])
        pull = -(reaction - weight_support)
        return {
            "time_s": float(data.time),
            "bend_deg": float(np.degrees(np.arccos(np.clip(rotation[2, 2], -1, 1)))),
            "load_n": float(np.linalg.norm(pull)),
            "reaction_on_fruit_n": reaction.tolist(),
            "junction_displacement_m": displacement.tolist(),
            "junction_displacement_norm_m": float(np.linalg.norm(displacement)),
            "extension_m": float(displacement @ -rotation[:, 2]),
            "outward_work_j": float(pull @ displacement),
        }

    def _release_due(self) -> bool:
        self.sim.forward()
        state = self.junction_state()
        self.last_attached_junction_state = state
        self.maximum_bend_deg = max(self.maximum_bend_deg, state["bend_deg"])
        self.maximum_load_n = max(self.maximum_load_n, state["load_n"])
        regime = release_regime(
            state["bend_deg"],
            state["load_n"],
            state["extension_m"],
            state["outward_work_j"],
            bent_force_n=self.bent_force_n,
            straight_force_n=self.straight_force_n,
            bend_trial_deg=self.bend_trial_deg,
        )
        if regime:
            self.release_event = {**state, "regime": regime}
        return regime is not None

    def _after_control_step(self) -> None:
        super()._after_control_step()
        self.diagnostic_monitor.sample(self)
        self.motion_samples.append(
            {
                "time_s": float(self.sim.data.time),
                "joint_positions_rad": self.sim.data.qpos[self.qpos_indexes[:5]].tolist(),
                "tool_position_m": self.sim.data.get_site_xpos("so101_gripperframe").tolist(),
            }
        )
        if self.detached_time is None:
            self.junction_samples.append(self.junction_state())

    def task_evidence(self) -> dict:
        parent = super().task_evidence()
        parent.pop("fixture_release_time_s")
        return {
            **parent,
            "scope": "load-released mechanical proxy and 2 s free retention",
            "release_time_s": self.detached_time,
            "release_event": self.release_event,
            "maximum_bend_deg": self.maximum_bend_deg,
            "maximum_junction_load_n": self.maximum_load_n,
            "junction_samples": self.junction_samples,
            "bent_force_samples_n": BENT_FORCE_SAMPLES_N,
            "straight_force_samples_n": STRAIGHT_FORCE_SAMPLES_N,
            "bent_force_threshold_n": self.bent_force_n,
            "straight_force_threshold_n": self.straight_force_n,
            "bend_trial_deg": self.bend_trial_deg,
            "minimum_numerical_extension_m": MIN_EXTENSION_M,
            "junction_solref": self.model.eq_solref[self.fixture_id].tolist(),
            "junction_solimp": self.model.eq_solimp[self.fixture_id].tolist(),
            "junction_bending_stiffness_calibrated": False,
            "biological_fracture_calibrated": False,
            "minimum_arm_joint_limit_margin_rad": self.minimum_joint_limit_margin_rad,
            "maximum_arm_speed_rad_s": self.maximum_arm_speed_rad_s,
            "motion_samples": self.motion_samples,
            "release_doi": "10.1017/S0263574714001155",
            "diagnostics": self.diagnostic_monitor.report(self),
        }
