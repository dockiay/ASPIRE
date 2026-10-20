"""Bounded public action diagnostics from integrity-checked recorded outputs."""

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

ACTION_NAMES = {
    "so101-command-gripper": "so101.command_gripper",
    "so101-command-joints": "so101.command_joints",
    "move-to-joints": "move_to_joints",
    "move-to-pose": "move_to_pose",
    "execute-trajectory": "execute_trajectory",
    "set-gripper": "set_gripper",
}


def action_feedback(run):
    """No inputs, targets, images or evaluator state are read or returned."""
    run = Path(run).resolve()
    manifest = json.loads((run / "manifest.json").read_text())
    indexed = []
    for entry in manifest["files"]:
        match = re.fullmatch(r"trace/calls/call-\d+-(.*)/output\.json", entry["path"])
        if match and match.group(1) in ACTION_NAMES:
            indexed.append((entry, ACTION_NAMES[match.group(1)]))
    indexed.sort(key=lambda item: item[0]["path"])
    rows = []
    for entry, name in indexed[-2048:]:
        path = (run / entry["path"]).resolve()
        if not path.is_relative_to(run):
            raise ValueError("Public action record escapes the episode")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError("Public action record differs from its manifest")
        output = json.loads(data)
        if not isinstance(output, dict) or not isinstance(output.get("ok"), bool):
            continue
        row = {
            "tool": name,
            "ok": output["ok"],
            "call_index": int(re.search(r"call-(\d+)-", entry["path"]).group(1)),
        }
        steps = output.get("steps_executed")
        if type(steps) is int and steps >= 0:
            row["steps_executed"] = steps
        diagnostics = output.get("diagnostics", {})
        if not isinstance(diagnostics, dict):
            diagnostics = {}
        if isinstance(diagnostics.get("stop_reason"), str):
            row["stop_reason"] = diagnostics["stop_reason"][:80]
        if isinstance(diagnostics.get("target_reached"), bool):
            row["target_reached"] = diagnostics["target_reached"]
        for key in ("completed", "gripper_setpoint_preserved"):
            if isinstance(diagnostics.get(key), bool):
                row[key] = diagnostics[key]
        if diagnostics.get("gripper_mode") in {"explicit_position", "measured_aperture"}:
            row["gripper_mode"] = diagnostics["gripper_mode"]
        for key in ("start_time_s", "end_time_s"):
            value = diagnostics.get(key)
            if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                row[key] = value
        forces = diagnostics.get("peak_finger_forces_n", {})
        if not isinstance(forces, dict):
            forces = {}
        values = {
            side: forces[side]
            for side in ("fixed", "moving")
            if type(forces.get(side)) in (int, float) and math.isfinite(forces[side])
        }
        if values:
            row["peak_finger_forces_n"] = values
        error = output.get("error")
        if isinstance(error, dict):
            row["error"] = {
                key: error[key][:maximum]
                for key, maximum in (("code", 64), ("message", 240))
                if isinstance(error.get(key), str)
            }
        rows.append(row)
    stops = [
        row
        for row in rows
        if not row["ok"]
        or row.get("stop_reason") in {"force_limit", "contact_lost", "contact", "duration_limit"}
    ]
    return {
        "scope": "recorded public action results, not object-relation or task success evidence",
        "indexed_action_calls": len(indexed),
        "summarized_action_calls": len(rows),
        "earlier_calls_omitted": max(0, len(indexed) - 2048),
        "zero_step_calls": sum(row.get("steps_executed") == 0 for row in rows),
        "stop_counts": dict(Counter(row["stop_reason"] for row in rows if "stop_reason" in row)),
        "recent_stops": stops[-6:],
        "recent_actions": rows[-12:],
        "last_actions": rows[-2:],
    }
