"""Action feedback preserves useful failures while excluding targets/native state."""

import hashlib
import json

import pytest

from cap_harness.so101.action_feedback import action_feedback


def recorded(tmp_path, outputs):
    files = []
    for index, (tool, output) in enumerate(outputs):
        relative = f"trace/calls/call-{index:06d}-{tool}/output.json"
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(output).encode()
        path.write_bytes(data)
        files.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest()})
    (tmp_path / "manifest.json").write_text(json.dumps({"files": files}))
    return files


def test_public_guard_results_remain_visible_without_private_or_target_fields(tmp_path):
    recorded(
        tmp_path,
        [
            (
                "so101-command-joints",
                {
                    "ok": True,
                    "steps_executed": 0,
                    "diagnostics": {
                        "stop_reason": "force_limit",
                        "target_reached": False,
                        "peak_finger_forces_n": {
                            "fixed": 6.5,
                            "moving": float("nan"),
                            "native": 999,
                        },
                        "native_position": "DO_NOT_EXPOSE_NATIVE_POSITION",
                        "measured_joints_rad": [99] * 5,
                    },
                    "final_observation": "DO_NOT_EXPOSE_IMAGE",
                    "input": {"target": "DO_NOT_EXPOSE_TARGET"},
                    "error": {
                        "code": "timeout",
                        "message": "public action stop",
                        "details": {"native": "DO_NOT_EXPOSE_DETAILS"},
                    },
                },
            )
        ],
    )
    value = action_feedback(tmp_path)
    assert value["zero_step_calls"] == 1
    assert value["stop_counts"] == {"force_limit": 1}
    row = value["recent_stops"][0]
    assert row["ok"] and not row["target_reached"]
    assert row["peak_finger_forces_n"] == {"fixed": 6.5}
    serialized = json.dumps(value)
    assert "DO_NOT_EXPOSE" not in serialized and "measured_joints_rad" not in serialized


def test_only_allowlisted_action_outputs_are_read(tmp_path):
    recorded(tmp_path, [("so101-get-native-state", {"ok": True, "secret": "DO_NOT_EXPOSE"})])
    # A non-action artifact must not even be parsed.
    path = tmp_path / "evaluation/so101-task.json"
    path.parent.mkdir()
    path.write_text("not JSON and not public action evidence")
    value = action_feedback(tmp_path)
    assert value["indexed_action_calls"] == 0 and value["last_actions"] == []


def test_tampered_trace_is_rejected(tmp_path):
    files = recorded(tmp_path, [("so101-command-gripper", {"ok": False})])
    (tmp_path / files[0]["path"]).write_text('{"ok": true}')
    with pytest.raises(ValueError, match="differs from its manifest"):
        action_feedback(tmp_path)


def test_stop_history_is_bounded_and_messages_are_truncated(tmp_path):
    recorded(
        tmp_path,
        [
            (
                "so101-command-gripper",
                {
                    "ok": False,
                    "steps_executed": 1,
                    "diagnostics": {"stop_reason": "duration_limit"},
                    "error": {"code": "timeout", "message": "x" * 1000},
                },
            )
            for _ in range(10)
        ],
    )
    value = action_feedback(tmp_path)
    assert value["indexed_action_calls"] == 10
    assert len(value["recent_stops"]) == 6 and len(value["last_actions"]) == 2
    assert len(value["recent_stops"][0]["error"]["message"]) == 240


def test_a_numerical_action_success_does_not_become_physical_success(tmp_path):
    recorded(
        tmp_path,
        [
            (
                "so101-command-joints",
                {
                    "ok": True,
                    "steps_executed": 20,
                    "diagnostics": {
                        "stop_reason": "target_reached",
                        "target_reached": True,
                        "task_success": True,
                    },
                },
            )
        ],
    )
    value = action_feedback(tmp_path)
    assert value["recent_stops"] == []
    assert value["stop_counts"] == {"target_reached": 1}
    assert "task_success" not in json.dumps(value)
