"""Bounded public policy diagnostics without discarding the actual error."""

import json

PAYLOAD_KEYS = {"rgb", "depth_m", "mask", "masks", "cameras", "point_cloud", "points"}


def bounded_result(value, budget=12000):
    """Keep late logs, errors and measured robot state; omit bulk image data."""
    changed = False

    def trim(item, depth, limit):
        nonlocal changed
        if isinstance(item, str):
            if len(item) > 1200:
                changed = True
                return item[:400] + "\n[excerpt]\n" + item[-700:]
            return item
        if isinstance(item, (dict, list)) and depth > 9:
            changed = True
            return "[depth limit]"
        if isinstance(item, dict):
            result = {}
            priority = ("error", "stage", "phase", "status", "diagnostics", "logs", "ok")
            keys = [key for key in priority if key in item]
            keys += [key for key in item if key not in keys]
            for key in keys[:32]:
                if key in PAYLOAD_KEYS:
                    changed = True
                    continue
                data = item[key]
                if key in ("final_observation", "observation") and isinstance(data, dict):
                    data = {k: data[k] for k in ("robot_state", "timestamp_s") if k in data}
                    changed = True
                result[key] = trim(data, depth + 1, limit)
            changed |= len(keys) > 32
            return result
        if isinstance(item, list):
            if len(item) > limit:
                changed = True
            return [trim(part, depth + 1, limit) for part in item[-limit:]]
        return item

    for limit in (24, 12, 6, 3):
        compact = trim(value, 0, limit)
        encoded = json.dumps(compact, ensure_ascii=False)
        if len(encoded.encode()) <= budget:
            return compact, changed
    # A valid excerpt is preferable to silently losing the entire policy report.
    excerpt = encoded.encode()[-(budget // 3) :].decode(errors="ignore")
    return {"excerpt": excerpt, "note": "bounded serialized policy report excerpt"}, True


def program_feedback(document):
    result, clipped = bounded_result(document.get("result"))
    failed = []
    for call in document.get("calls", []):
        summary = call.get("outputs_summary", {})
        if call.get("ok") is False or summary.get("ok") is False:
            failed.append(
                {
                    key: call.get(key)
                    for key in ("index", "tool", "failure_code", "error_message", "outputs_summary")
                }
            )
    error = document.get("error")
    return {
        "scope": "policy self-report and public API traces only; not evaluator evidence",
        "result": result,
        "report_clipped": clipped,
        "failed_public_calls": failed[-8:],
        "execution_error_tail": str(error.get("message", ""))[-1600:]
        if isinstance(error, dict)
        else None,
        "stdout_excerpt": str(document.get("stdout", ""))[-3000:],
    }
