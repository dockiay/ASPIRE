"""Phase-aware post-episode reports for harvest, carry and placement."""

from cap_harness.so101.diagnostics import DetachmentDiagnostics

STAGES = (
    ("grasp_time", "grasp_verified"),
    ("detached_time", "junction_released"),
    ("free_hold_verified_time", "free_retention_verified"),
    ("destination_ready_time", "destination_verified"),
    ("deposit_started_time", "deposit_started"),
    ("first_base_contact_time", "container_base_contact"),
)


def diagnostics(env, evidence):
    phase = evidence["stage"]
    now = float(env.sim.data.time)
    findings = []
    native_events = list(env.diagnostic_monitor.events)

    def finding(code, message, basis="latched_observed_violation"):
        aliases = {
            "excessive_model_finger_force": "finger_force_limit_exceeded",
            "excessive_model_penetration": "penetration_limit_exceeded",
            "fruit_slipped_or_dropped": "relative_slip_exceeded",
            "fixture_released_without_qualified_grasp": "released_without_qualified_grasp",
        }
        event = next((e for e in native_events if e["code"] == aliases.get(code, code)), None)
        findings.append(
            {
                "code": code,
                "message": message,
                "time_s": event["time_s"] if event else now,
                "phase": event["phase"] if event else phase,
                "basis": basis,
                "active_command": event.get("active_command") if event else None,
                "detail": event.get("detail") if event else None,
            }
        )

    if not evidence["task_success"]:
        if env.forbidden_contacts:
            finding("robot_collision", "Robot contact with an obstacle or itself was recorded.")
        for code in sorted(
            env.limit_violations | env.retention_violations | env.transport_violations
        ):
            finding(code, "Recorded task constraint violation: " + code)
        if env.early_closure:
            finding("early_closure", "Gripper closed before open approach was verified.")
        if env.support_contacts:
            finding(
                "unexpected_support", "Fruit support outside the allowed fingers/container phase."
            )
        if not findings:
            code, message = {
                "approach_and_grasp": (
                    "grasp_not_qualified",
                    "A sustained bilateral grasp has not been verified.",
                ),
                "mechanical_detachment": ("junction_not_released", "The fruit remains attached."),
                "free_retention": (
                    "retention_duration_short",
                    "Two seconds of free retention have not been verified.",
                ),
                "transport_and_release": (
                    "destination_not_verified",
                    "Transport and release above the container remain incomplete.",
                ),
                "stable_placement_and_withdrawal": (
                    "placement_not_stable",
                    "Stable containment and gripper withdrawal remain incomplete.",
                ),
            }[phase]
            finding(code, message, "unmet_predicate_at_finalization")
    events = native_events
    for field, code in STAGES:
        time = getattr(env, field)
        if time is not None:
            events.append(
                {
                    "code": code,
                    "time_s": time,
                    "phase": code,
                    "visual_reference": DetachmentDiagnostics.visual_reference(env, time),
                }
            )
    final = DetachmentDiagnostics.snapshot(env)
    final.update(
        phase=phase,
        free_hold_verified=env.free_hold_verified_time is not None,
        destination_verified=env.destination_ready_time is not None,
        deposit_started=env.deposit_started_time is not None,
        placement_hold_s=env.placement_duration,
        container_base_contact=env.has_base_contact(),
        ordered_stages_complete=env.ordered_stages_complete(),
    )
    return {
        "schema_version": "so101-harvest-diagnostics-v2",
        "task": env.task_name,
        "task_success": evidence["task_success"],
        "stage": phase,
        "status": "completed"
        if evidence["task_success"]
        else (
            "failed"
            if any(f["basis"] == "latched_observed_violation" for f in findings)
            else "incomplete"
        ),
        "primary_finding": findings[0] if findings else None,
        "findings": findings,
        "events": sorted(events, key=lambda event: event["time_s"]),
        "final_state": final,
        "contract": "so101-fruitgym-harvest-v2",
    }
