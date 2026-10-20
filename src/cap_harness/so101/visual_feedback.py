"""Bounded public visual motion evidence from integrity-checked tool outputs."""

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

_OUTPUT_PATH = re.compile(r"trace/calls/call-(\d+)-so101-compare-visual-motion/output\.json")
_MAX_CALLS = 2048
_MAX_HISTORY = 12
_MAX_OUTPUT_BYTES = 262144
_STATUSES = {"estimated", "unknown"}
_EVIDENCE = {
    "co_motion_consistent",
    "relative_motion_detected",
    "motion_too_small",
    "unknown",
}


def _number(value, *, maximum=None):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and value >= 0
        and (maximum is None or value <= maximum)
    )


def _numbers(source, keys):
    if not isinstance(source, dict):
        return {}
    return {key: source[key] for key in keys if _number(source.get(key))}


def _measurement(output, call_index):
    if not isinstance(output, dict) or type(output.get("ok")) is not bool:
        return None
    row = {
        "call_index": call_index,
        "tool": "so101.compare_visual_motion",
        "ok": output["ok"],
    }
    if isinstance(output.get("status"), str) and output["status"] in _STATUSES:
        row["status"] = output["status"]
    if isinstance(output.get("evidence"), str) and output["evidence"] in _EVIDENCE:
        row["evidence"] = output["evidence"]
    row.update(_numbers(output, ("reference_time_s", "current_time_s")))
    components = output.get("motion_components")
    if isinstance(components, dict):
        row["motion_components"] = {
            key: components[key]
            for key in ("rotation", "translation")
            if isinstance(components.get(key), str) and components[key] in _EVIDENCE
        }
    reasons = output.get("reasons")
    if isinstance(reasons, list):
        row["reasons"] = [reason[:160] for reason in reasons[:4] if isinstance(reason, str)]
    for key in ("fruit_motion", "tool_motion"):
        if key in output:
            row[key] = _numbers(output[key], ("rotation_deg", "displacement_m")) or None
    if "relative_motion" in output:
        row["relative_motion"] = (
            _numbers(
                output["relative_motion"],
                ("rotation_error_deg", "translation_error_m", "point_prediction_rms_m"),
            )
            or None
        )
    quality = output.get("quality")
    if isinstance(quality, dict):
        selected = _numbers(
            quality,
            (
                "residual_rms_m",
                "spatial_spread_m",
                "rotation_uncertainty_deg",
                "translation_uncertainty_m",
                "view_agreement_deg",
            ),
        )
        for key in ("tracks", "inliers"):
            if type(quality.get(key)) is int and quality[key] >= 0:
                selected[key] = quality[key]
        if _number(quality.get("inlier_fraction"), maximum=1):
            selected["inlier_fraction"] = quality["inlier_fraction"]
        row["quality"] = selected
    views = output.get("views")
    if isinstance(views, list):
        row["views"] = []
        for view in views[:4]:
            if not isinstance(view, dict):
                continue
            selected = {}
            if isinstance(view.get("camera"), str) and view["camera"] in {"agentview", "sideview"}:
                selected["camera"] = view["camera"]
            if isinstance(view.get("status"), str) and view["status"] in _STATUSES:
                selected["status"] = view["status"]
            if isinstance(view.get("reason"), str):
                selected["reason"] = view["reason"][:160]
            for key in ("features", "accepted_tracks", "inliers"):
                if type(view.get(key)) is int and view[key] >= 0:
                    selected[key] = view[key]
            if selected:
                row["views"].append(selected)
    error = output.get("error")
    if isinstance(error, dict):
        row["error"] = {
            key: error[key][:maximum]
            for key, maximum in (("code", 64), ("message", 240))
            if isinstance(error.get(key), str)
        }
    return row


def visual_feedback(run):
    """Read only recorded public comparisons; never infer grasp or detachment.

    Coordinates, transforms, correspondences, images, masks, arbitrary metrics,
    thresholds and evaluator artifacts are deliberately excluded. Camera names
    and observation times allow the controller to request nearby recorded RGB
    frames independently through ``view_frame``.
    """
    run = Path(run).resolve()
    manifest = json.loads((run / "manifest.json").read_text())
    indexed = []
    paths = set()
    for entry in manifest["files"]:
        match = _OUTPUT_PATH.fullmatch(entry["path"])
        if not match:
            continue
        if entry["path"] in paths:
            raise ValueError("Duplicate public visual motion record in manifest")
        paths.add(entry["path"])
        indexed.append((int(match.group(1)), entry))
    indexed.sort(key=lambda item: item[0])
    rows = []
    invalid = 0
    for call_index, entry in indexed[-_MAX_CALLS:]:
        path = (run / entry["path"]).resolve()
        if not path.is_relative_to(run):
            raise ValueError("Public visual motion record escapes the episode")
        if path.stat().st_size > _MAX_OUTPUT_BYTES:
            raise ValueError("Public visual motion record exceeds the bounded output size")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError("Public visual motion record differs from its manifest")
        row = _measurement(json.loads(data), call_index)
        if row is None:
            invalid += 1
        else:
            rows.append(row)
    return {
        "scope": "recorded public RGB-D visual motion estimates; not grasp, detachment or task success evidence",
        "indexed_comparison_calls": len(indexed),
        "summarized_comparison_calls": len(rows),
        "earlier_calls_omitted": max(0, len(indexed) - _MAX_CALLS),
        "invalid_outputs_omitted": invalid,
        "status_counts": dict(Counter(row["status"] for row in rows if "status" in row)),
        "evidence_counts": dict(Counter(row["evidence"] for row in rows if "evidence" in row)),
        "earlier_measurements_omitted": max(0, len(rows) - _MAX_HISTORY),
        "recent_measurements": rows[-_MAX_HISTORY:],
    }
