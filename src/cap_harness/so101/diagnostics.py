"""Host-only observations and failure classification; never changes task scoring."""

from __future__ import annotations

import math

import numpy as np

from cap_harness.so101.grasp_contact import (
    CONTACT_HOLD_SECONDS,
    MAX_FINGER_FORCE_N,
    MAX_PENETRATION_M,
    MIN_FINGER_FORCE_N,
)
from cap_harness.so101.retention import MAX_SLIP_M, RETENTION_SECONDS

DIAGNOSTIC_VERSION = "so101-strawberry-diagnostics-v1"
DROP_DESCENT_M = 0.03
DROP_DOWNWARD_SPEED_M_S = 0.05

MESSAGES = {
    "robot_collision": "Contacto prohibido del robot observado.",
    "finger_force_limit_exceeded": "Fuerza de los dedos por encima del límite didáctico.",
    "penetration_limit_exceeded": "Penetración del modelo por encima del límite permitido.",
    "invalid_physics": "Se observó una modificación física no permitida por la tarea.",
    "fruit_dropped": "Fruto descendido sin contacto con los dedos, cayendo o apoyado en la mesa.",
    "unexpected_support": "El fruto libre tuvo un apoyo externo no permitido.",
    "relative_slip_exceeded": "El fruto superó el desplazamiento relativo permitido.",
    "early_closure": "La pinza cerró antes de verificar la aproximación abierta.",
    "released_without_qualified_grasp": "La unión se liberó sin un agarre previamente acreditado.",
    "grasp_not_qualified": "El intento terminó sin acreditar el agarre de ambos dedos.",
    "junction_not_released": "El intento terminó con el fruto todavía unido.",
    "unstable_bilateral_contact": "Al finalizar no se cumplen los contactos opuestos requeridos.",
    "retention_duration_short": "La retención válida actual no alcanza dos segundos continuos.",
    "unresolved_task_predicate": "El evaluador no acredita el éxito; revisar los predicados finales.",
}
HARD_CODES = (
    "robot_collision",
    "finger_force_limit_exceeded",
    "penetration_limit_exceeded",
    "invalid_physics",
    "fruit_dropped",
    "unexpected_support",
    "relative_slip_exceeded",
    "early_closure",
    "released_without_qualified_grasp",
)


def contact_measurements(env) -> dict:
    """Describe geometry; the existing bilateral witness remains authoritative."""
    forces, centers, normals = {}, {}, {}
    for side, contacts in env.current_contacts.items():
        active = [c for c in contacts if c["normal_force_n"] > 0]
        force = sum(c["normal_force_n"] for c in active)
        forces[side] = force
        if force > 0:
            centers[side] = (
                sum(np.asarray(c["position_m"]) * c["normal_force_n"] for c in active) / force
            )
            normal = sum(np.asarray(c["normal_on_fruit"]) * c["normal_force_n"] for c in active)
            if np.linalg.norm(normal) > 1e-9:
                normals[side] = normal / np.linalg.norm(normal)
    geometry = {
        "normal_dot_product": None,
        "contact_separation_m": None,
        "across_fruit_center_dot_m2": None,
    }
    if len(centers) == 2:
        geometry["contact_separation_m"] = float(
            np.linalg.norm(centers["fixed"] - centers["moving"])
        )
        geometry["across_fruit_center_dot_m2"] = float(
            (centers["fixed"] - env.fruit_position()) @ (centers["moving"] - env.fruit_position())
        )
    if len(normals) == 2:
        geometry["normal_dot_product"] = float(normals["fixed"] @ normals["moving"])
    return {
        "bilateral_qualified": env._bilateral_witness() is not None,
        "finger_forces_n": forces,
        **geometry,
    }


class DetachmentDiagnostics:
    def __init__(self) -> None:
        self.events = []
        self.seen = set()
        self.previous_bilateral = None
        self.previous_retention_start = None
        self.previous_success = False

    @staticmethod
    def phase(env) -> str:
        if getattr(env, "deposit_started_time", None) is not None:
            return "stable_placement_and_withdrawal"
        if getattr(env, "free_hold_verified_time", None) is not None:
            return "transport_and_release"
        if env.grasp_time is None:
            return "approach_and_grasp"
        if env.detached_time is None:
            return "detachment"
        return "free_retention"

    @staticmethod
    def snapshot(env) -> dict:
        return {
            "time_s": float(env.sim.data.time),
            "phase": DetachmentDiagnostics.phase(env),
            "fruit_position_m": env.fruit_position().tolist(),
            "fruit_velocity_m_s": env.sim.data.qvel[env.fruit_dof : env.fruit_dof + 3].tolist(),
            "fruit_relative_to_tool_m": env.fruit_relative_position().tolist(),
            "fixture_active": bool(env.sim.data._data.eq_active[env.fixture_id]),
            "grasp_time_s": env.grasp_time,
            "gripper_opening": env.opening(),
            "approach_ready_step": env.ready_step,
            "release_time_s": env.detached_time,
            "current_retention_s": env.current_retention_duration,
            "longest_retention_s": env.longest_retention_duration,
            "maximum_relative_slip_m": env.maximum_relative_slip,
            "peak_finger_forces_n": dict(env.peak_finger_force),
            "maximum_penetration_m": env.max_penetration,
            **contact_measurements(env),
        }

    @staticmethod
    def visual_reference(env, time_s: float) -> dict:
        frame_time = time_s * env.frequency
        return {
            "videos": ["media/videos/agentview.mp4", "media/videos/sideview.mp4"],
            "time_s": time_s,
            "frame_rate_hz": env.frequency,
            "frame_before": max(0, math.floor(frame_time + 1e-9)),
            "frame_after": max(0, math.ceil(frame_time - 1e-9)),
            "note": "Numerical event between recorded frames; images alone may be occluded.",
        }

    def record(self, env, code: str, *, detail=None, once_key=None) -> None:
        if once_key is not None:
            if once_key in self.seen:
                return
            self.seen.add(once_key)
        state = self.snapshot(env)
        if detail is not None and "contact_pair" in detail:
            pair = tuple(detail["contact_pair"])
            measured = [
                {"distance_m": float(c.dist), "position_m": c.pos.tolist()}
                for c in env.sim.data.contact
                if c.dist <= 0
                and tuple(sorted((env._label(int(c.geom1)), env._label(int(c.geom2))))) == pair
            ]
            detail = {**detail, "measured_contacts": measured}
        self.events.append(
            {
                "event_id": len(self.events) + 1,
                "code": code,
                "time_s": state["time_s"],
                "phase": state["phase"],
                "evidence": state,
                "detail": detail,
                "visual_reference": self.visual_reference(env, state["time_s"]),
                "active_command": getattr(env, "active_command", None),
            }
        )

    def sample(self, env) -> None:
        if env.ready_step is not None:
            self.record(env, "approach_verified", once_key="approach_verified")
        if env.grasp_time is not None:
            self.record(env, "grasp_qualified", once_key="grasp_qualified")
        for violation in sorted(getattr(env, "transport_violations", set())):
            self.record(
                env, violation, detail={"violation": violation}, once_key=("transport", violation)
            )
        if env.detached_time is not None and env.retention_monitor_active():
            self.record(
                env, "junction_released", detail=env.release_event, once_key="junction_released"
            )
        bilateral = env._bilateral_witness() is not None
        if (
            env.grasp_time is not None
            and self.previous_bilateral is not None
            and bilateral != self.previous_bilateral
        ):
            self.record(
                env, "bilateral_contact_restored" if bilateral else "bilateral_contact_lost"
            )
        self.previous_bilateral = bilateral
        if env.retention_start is not None and env.retention_start != self.previous_retention_start:
            self.record(env, "retention_started")
        self.previous_retention_start = env.retention_start
        for pair in sorted(env.forbidden_contacts):
            self.record(
                env, "robot_collision", detail={"contact_pair": pair}, once_key=("collision", pair)
            )
        for violation in sorted(env.limit_violations):
            code = {
                "excessive_model_finger_force": "finger_force_limit_exceeded",
                "excessive_model_penetration": "penetration_limit_exceeded",
            }.get(violation, "invalid_physics")
            self.record(env, code, detail={"violation": violation}, once_key=("limit", violation))
        if env.early_closure:
            self.record(env, "early_closure", once_key="early_closure")
        for pair in sorted(env.support_contacts):
            self.record(
                env, "unexpected_support", detail={"contact_pair": pair}, once_key=("support", pair)
            )
        for violation in sorted(env.retention_violations):
            code = {
                "fruit_slipped_or_dropped": "relative_slip_exceeded",
                "fixture_released_without_qualified_grasp": "released_without_qualified_grasp",
            }.get(violation, "invalid_physics")
            self.record(
                env, code, detail={"violation": violation}, once_key=("retention", violation)
            )
        if env.detached_time is not None:
            no_fingers = not any(env.current_contacts.values())
            descent = float(env.release_world_position[2] - env.fruit_position()[2])
            downward = float(env.sim.data.qvel[env.fruit_dof + 2]) < -DROP_DOWNWARD_SPEED_M_S
            floor_id = env.model.geom("work_surface").id
            floor_contact = any(
                c.dist <= 0
                and (
                    (int(c.geom1) in env.all_fruit_geoms and int(c.geom2) == floor_id)
                    or (int(c.geom2) in env.all_fruit_geoms and int(c.geom1) == floor_id)
                )
                for c in env.sim.data.contact
            )
            if no_fingers and descent >= DROP_DESCENT_M and (downward or floor_contact):
                self.record(
                    env,
                    "fruit_dropped",
                    detail={
                        "descent_since_release_m": descent,
                        "downward_motion": downward,
                        "floor_contact_observed": floor_contact,
                    },
                    once_key="fruit_dropped",
                )
        success = env._check_success()
        if success and not self.previous_success:
            self.record(env, "retention_verified")
        elif self.previous_success and not success:
            self.record(env, "previous_success_no_longer_valid")
        self.previous_success = success

    def report(self, env) -> dict:
        final = self.snapshot(env)
        success = bool(env._check_success())
        findings = []
        if not success:
            for code in HARD_CODES:
                # A descriptive drop event must not add a new permanent rule:
                # the existing evaluator must also have latched slip or support.
                if code == "fruit_dropped" and not (
                    "fruit_slipped_or_dropped" in env.retention_violations or env.support_contacts
                ):
                    continue
                matches = [e for e in self.events if e["code"] == code]
                if matches:
                    event = matches[0]
                    findings.append(
                        {
                            "code": code,
                            "message": MESSAGES[code],
                            "basis": "latched_observed_violation",
                            "time_s": event["time_s"],
                            "phase": event["phase"],
                            "event_ids": [e["event_id"] for e in matches],
                        }
                    )
            if not findings:
                if env.grasp_time is None:
                    code = "grasp_not_qualified"
                elif env.detached_time is None:
                    code = "junction_not_released"
                elif not final["bilateral_qualified"]:
                    code = "unstable_bilateral_contact"
                elif env.current_retention_duration + 1e-9 < RETENTION_SECONDS:
                    code = "retention_duration_short"
                else:
                    code = "unresolved_task_predicate"
                findings.append(
                    {
                        "code": code,
                        "message": MESSAGES[code],
                        "basis": "unmet_predicate_at_finalization",
                        "time_s": final["time_s"],
                        "phase": final["phase"],
                        "event_ids": [],
                    }
                )
        return {
            "schema_version": DIAGNOSTIC_VERSION,
            "task": env.task_name,
            "status": "completed"
            if success
            else (
                "failed"
                if any(f["basis"] == "latched_observed_violation" for f in findings)
                else "incomplete"
            ),
            "task_success": success,
            "primary_finding": findings[0] if findings else None,
            "findings": findings,
            "final_state": final,
            "events": list(self.events),
            "final_visual_reference": self.visual_reference(env, final["time_s"]),
            "last_attached_junction_state": env.last_attached_junction_state,
            "release_event": env.release_event,
            "contract": {
                "version": "so101-detach-retain-v1",
                "required_current_retention_s": RETENTION_SECONDS,
                "grasp_contact_hold_s": CONTACT_HOLD_SECONDS,
                "maximum_relative_slip_m": MAX_SLIP_M,
                "maximum_finger_force_n": MAX_FINGER_FORCE_N,
                "maximum_penetration_m": MAX_PENETRATION_M,
                "minimum_finger_force_n": MIN_FINGER_FORCE_N,
                "maximum_contact_normal_dot_product": -0.5,
                "minimum_contact_separation_m": 0.02,
                "requires_opposite_sides_of_fruit_center": True,
                "requires_current_bilateral_contact": True,
                "requires_no_other_support": True,
                "requires_no_latched_violations": True,
            },
            "drop_label_thresholds": {
                "descent_m": DROP_DESCENT_M,
                "downward_speed_m_s": DROP_DOWNWARD_SPEED_M_S,
                "changes_task_scoring": False,
            },
            "interpretation": "Primary finding is a prioritized observed blocker, not proof of root cause. Program errors belong to outcome.json. No claim of biological damage assessment.",
        }
