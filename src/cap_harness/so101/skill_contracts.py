"""Versioned skill predicates, evaluated only from audited post-episode evidence."""

import copy
import math

import numpy as np

from cap_harness.so101 import campaign as c

FULL = "harvest_complete_v1"
LOCALIZE = "localize_ripe_fruit_v1"
CONTRACTS = {
    FULL: {"version": 1, "goal": "Complete the unchanged harvest, carry and deposit benchmark."},
    LOCALIZE: {
        "version": 1,
        "goal": "Estimate the ripe fruit center from public RGB-D, without moving the robot.",
        "maximum_error_m": 0.020,
        "maximum_timestamp_error_s": 0.05,
        "maximum_displacement_error_m": 0.010,
        "maximum_control_steps": 0,
        "frame": "so101_base",
        "report": "result = {'skill_results': {'localize_ripe_fruit_v1': {'point_m': [x,y,z], 'frame': 'so101_base', 'timestamp_s': measured_time, 'camera_names': ['agentview']}}}. Coordinates must be computed during execution; use one or both public cameras.",
        "scope": "Synthetic engineering center tolerance; not a physical-camera accuracy claim.",
    },
    "grasp_ripe_fruit_v1": {
        "version": 1,
        "goal": "Sustain a qualified opposing grasp for at least 0.5 seconds, without scene violations.",
    },
    "detach_ripe_fruit_v1": {
        "version": 1,
        "goal": "Verify grasp and mechanically release the fruit without scene violations.",
    },
    "retain_ripe_fruit_v1": {
        "version": 1,
        "goal": "Mechanically detach and verify two seconds of free retention.",
    },
    "carry_ripe_fruit_v1": {
        "version": 1,
        "goal": "Verify free retention and carry the same fruit at least 15 cm.",
    },
    "deposit_ripe_fruit_v1": {
        "version": 1,
        "goal": "Verify stable placement, open gripper and withdrawal under the existing placement predicate.",
    },
}


def contract(name):
    if name not in CONTRACTS:
        raise ValueError("Unknown skill verification contract: " + str(name))
    value = {"id": name, **copy.deepcopy(CONTRACTS[name])}
    return {**value, "sha256": c.canonical_sha256(value)}


def catalog():
    return {name: contract(name) for name in CONTRACTS}


def proposal_contract(proposal):
    return contract(proposal.get("verification_contract", FULL))


def clean(evidence):
    return not any(
        evidence.get(key)
        for key in (
            "forbidden_contact_pairs",
            "limit_violations",
            "retention_violations",
            "transport_violations",
            "non_finger_support_contacts",
        )
    )


def grasp_measurements(evidence):
    """Post-episode scalar feedback only; never copy contacts or reference geometry."""
    measurements = {
        key: evidence[key]
        for key in ("grasp_verified_time_s", "longest_bilateral_contact_s")
        if key in evidence
    }
    measurements["contact_hold_required_s"] = 0.5
    measurements["non_finger_support_recorded"] = bool(
        evidence.get("non_finger_support_contacts")
    )
    final = evidence.get("diagnostics", {}).get("final_state", {})
    contact = {
        key: final[key]
        for key in (
            "bilateral_qualified",
            "normal_dot_product",
            "contact_separation_m",
            "gripper_opening",
        )
        if key in final
    }
    if "finger_forces_n" in final:
        contact["finger_forces_n"] = {
            side: final["finger_forces_n"][side]
            for side in ("fixed", "moving")
            if side in final["finger_forces_n"]
        }
    if contact:
        measurements["final_contact"] = contact
    return measurements


def score(run, name):
    """Caller must first audit the native manifest. Never return reference coordinates."""
    spec = contract(name)
    outcome = c.read_json(run / "outcome.json")
    evidence = c.read_json(run / "evaluation/so101-task.json")
    document_path = run / "source/program-result.json"
    document = c.read_json(document_path) if document_path.exists() else {}
    reasons, measurements = [], {}
    if not outcome.get("program_ok"):
        reasons.append("program_failed")
    if not clean(evidence):
        reasons.append("scene_constraint_violation")
    if name == FULL:
        passed = bool(outcome.get("task_success"))
    elif name == LOCALIZE:
        passed = True
        reference = evidence.get("skill_evaluation_reference", {})
        result = document.get("result")
        reports = result.get("skill_results", {}) if isinstance(result, dict) else {}
        claim = reports.get(name, {}) if isinstance(reports, dict) else {}
        if not isinstance(claim, dict):
            claim = {}
        if outcome.get("steps_executed") != 0:
            reasons.append("localization_must_not_move_robot")
        successful_calls = {
            row.get("tool") for row in document.get("calls", []) if row.get("ok") is True
        }
        if not (
            "localize_object" in successful_calls
            or {"segment_text", "mask_to_point_cloud"} <= successful_calls
        ):
            reasons.append("no_successful_public_rgbd_localization")
        try:
            point = np.asarray(claim["point_m"], dtype=float)
            target = np.asarray(reference["fruit_position_m"], dtype=float)
            if (
                point.shape != (3,)
                or target.shape != (3,)
                or not np.isfinite(point).all()
                or not np.isfinite(target).all()
            ):
                raise ValueError("Invalid center")
            if claim["frame"] != spec["frame"] or reference["frame"] != spec["frame"]:
                reasons.append("wrong_frame")
            timestamp_error = abs(float(claim["timestamp_s"]) - float(reference["timestamp_s"]))
            if (
                not math.isfinite(timestamp_error)
                or timestamp_error > spec["maximum_timestamp_error_s"]
            ):
                reasons.append("stale_estimate")
            views = claim["camera_names"]
            if (
                not isinstance(views, list)
                or not views
                or not set(views) <= {"agentview", "sideview"}
            ):
                reasons.append("invalid_camera_evidence")
            distance = float(np.linalg.norm(point - target))
            measurements.update(center_error_m=distance, timestamp_error_s=timestamp_error)
            if distance > spec["maximum_error_m"]:
                reasons.append("center_error_exceeds_tolerance")
        except (KeyError, TypeError, ValueError, OverflowError):
            reasons.append("missing_or_invalid_localization_report")
    else:
        measurements.update(grasp_measurements(evidence))
        grasp = (
            evidence.get("grasp_verified_time_s") is not None
            # Match the native witness rounding tolerance; keep the 0.5 s threshold.
            and evidence.get("longest_bilateral_contact_s", 0) + 1e-9 >= 0.5
        )
        detached = (
            grasp
            and evidence.get("release_event") is not None
            and evidence.get("fruit_detached") is True
            and evidence.get("fixture_active") is False
        )
        retained = detached and evidence.get("free_hold_verified_time_s") is not None
        passed = {
            "grasp_ripe_fruit_v1": grasp,
            "detach_ripe_fruit_v1": detached,
            "retain_ripe_fruit_v1": retained,
            "carry_ripe_fruit_v1": retained
            and evidence.get("maximum_carried_distance_m", 0) >= 0.15,
            "deposit_ripe_fruit_v1": bool(evidence.get("final_placement_predicate"))
            and evidence.get("placement_hold_s", 0) >= 1.0,
        }[name]
    if not passed:
        reasons.append("skill_predicate_unmet")
    return {
        "contract": spec,
        "passed": passed and not reasons,
        "failures": reasons,
        "measurements": measurements,
        "task_success": bool(outcome.get("task_success")),
        "scope": "post-episode skill score; no reference geometry is exposed to the policy",
    }


def enrich(root, summary, name):
    value = copy.deepcopy(summary)
    results = []
    for row in value["cases"]:
        if row["episode"]:
            run = root / row["attempts"][-1]["directory"] / row["episode"]["run"]
            result = score(run, name)
            row["skill_evaluation"] = result
            results.append(result)
    for label, comparison in value["comparison"].items():
        selected = [
            row for row in value["cases"] if row["program"] == label and "skill_evaluation" in row
        ]
        if (
            name == LOCALIZE
            and len(selected) >= 2
            and all(row["skill_evaluation"]["passed"] for row in selected)
        ):
            samples = []
            for row in selected:
                run = root / row["attempts"][-1]["directory"] / row["episode"]["run"]
                claim = c.read_json(run / "source/program-result.json")["result"]["skill_results"][
                    name
                ]
                reference = c.read_json(run / "evaluation/so101-task.json")[
                    "skill_evaluation_reference"
                ]
                samples.append(
                    (np.array(claim["point_m"]), np.array(reference["fruit_position_m"]))
                )
            for row, (point, target) in zip(selected[1:], samples[1:]):
                error = float(np.linalg.norm((point - samples[0][0]) - (target - samples[0][1])))
                row["skill_evaluation"]["measurements"]["displacement_error_m"] = error
                if error > contract(name)["maximum_displacement_error_m"]:
                    for item in selected:
                        item["skill_evaluation"]["passed"] = False
                        item["skill_evaluation"]["failures"].append(
                            "cross_case_tracking_inconsistent"
                        )
        subset = [
            row["skill_evaluation"]
            for row in value["cases"]
            if row["program"] == label and "skill_evaluation" in row
        ]
        comparison["skill_success"] = sum(row["passed"] for row in subset)
        comparison["skill_success_rate"] = (
            comparison["skill_success"] / comparison["planned"]
            if len(subset) == comparison["planned"]
            else None
        )
        comparison["verification_contract"] = contract(name)
    return value
