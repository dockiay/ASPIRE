"""Stage evidence and visual-call ordering, never a private runtime sensor."""


def experiment_feedback(case):
    evaluations = case.get("skill_evaluations", {})
    grasp = evaluations.get("grasp_ripe_fruit_v1", {})
    measured = grasp.get("measurements", {})
    grasp_time = measured.get("grasp_verified_time_s")
    # A later constraint failure can invalidate a score after a grasp occurred.
    # Report both observations; never promote a failed score to success.
    verified = [name for name, value in evaluations.items() if value.get("passed") is True]
    actions = case.get("public_action_results", {})
    vision = case.get("public_visual_motion", {})
    recent = actions.get("recent_actions", [])
    moving = [row for row in recent if row.get("steps_executed", 0) > 0]
    arm = [row for row in moving if row.get("tool") == "so101.command_joints"]
    post_grasp = [
        row
        for row in arm
        if isinstance(grasp_time, (int, float)) and row.get("start_time_s", -1) >= grasp_time
    ]
    comparisons = vision.get("recent_measurements", [])
    followed = [
        row["call_index"]
        for row in comparisons
        if any(action.get("call_index", -1) > row["call_index"] for action in moving)
    ]
    return {
        "scope": "post-episode stage evidence; call order does not prove feedback-dependent decisions",
        "passed_contracts": verified,
        "qualified_grasp_observed": grasp_time is not None,
        "post_grasp_guarded_motion_observed": bool(post_grasp),
        "motion_history_complete": actions.get("summarized_action_calls", 0) <= len(recent)
        and actions.get("earlier_calls_omitted", 0) == 0,
        "visual_comparisons_followed_by_motion": followed,
        "visual_control_verified": False,
        "visual_control_review_required": bool(comparisons),
        "prerequisite_diagnosis": (
            "grasp_not_observed; detachment maneuver prerequisites unresolved"
            if grasp_time is None
            else "grasp_observed; inspect actual motion, coupling and stop reasons"
        ),
        "coupling_counts": dict(vision.get("evidence_counts", {})),
    }
