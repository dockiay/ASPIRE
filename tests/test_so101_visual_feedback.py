"""Recorded RGB-D motion diagnostics remain useful without native state leakage."""

import hashlib
import json

import pytest

from cap_harness.so101.visual_feedback import visual_feedback


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


def measurement(**overrides):
    return {
        "ok": True,
        "status": "estimated",
        "evidence": "relative_motion_detected",
        "reference_time_s": 4.0,
        "current_time_s": 5.0,
        "reasons": ["relative rotation exceeds the visual uncertainty"],
        "fruit_motion": {"rotation_deg": 2.0, "displacement_m": 0.001},
        "tool_motion": {"rotation_deg": 12.0, "displacement_m": 0.004},
        "relative_motion": {
            "rotation_error_deg": 10.0,
            "translation_error_m": 0.003,
            "point_prediction_rms_m": 0.004,
        },
        "quality": {
            "tracks": 22,
            "inliers": 20,
            "inlier_fraction": 20 / 22,
            "residual_rms_m": 0.0005,
            "spatial_spread_m": 0.01,
            "rotation_uncertainty_deg": 2.0,
            "view_agreement_deg": 1.0,
        },
        "views": [
            {
                "camera": "sideview",
                "status": "estimated",
                "features": 25,
                "accepted_tracks": 22,
                "inliers": 20,
            }
        ],
        **overrides,
    }


def test_visual_evidence_and_uncertainty_are_available_without_program_self_report(tmp_path):
    recorded(tmp_path, [("so101-compare-visual-motion", measurement())])
    result = visual_feedback(tmp_path)
    assert result["indexed_comparison_calls"] == 1
    assert result["status_counts"] == {"estimated": 1}
    assert result["evidence_counts"] == {"relative_motion_detected": 1}
    row = result["recent_measurements"][0]
    assert row["tool"] == "so101.compare_visual_motion"
    assert row["fruit_motion"]["rotation_deg"] == 2.0
    assert row["tool_motion"]["rotation_deg"] == 12.0
    assert row["fruit_motion"]["displacement_m"] == 0.001
    assert row["tool_motion"]["displacement_m"] == 0.004
    assert row["relative_motion"]["rotation_error_deg"] == 10.0
    assert row["quality"]["rotation_uncertainty_deg"] == 2.0
    assert row["reference_time_s"] == 4.0 and row["current_time_s"] == 5.0
    assert row["views"][0]["camera"] == "sideview"


def test_no_images_coordinates_native_state_or_arbitrary_fields_are_exposed(tmp_path):
    output = measurement()
    for key in ("fruit_motion", "tool_motion", "relative_motion", "quality"):
        output[key].update(
            rotation_matrix="DO_NOT_EXPOSE_TRANSFORM",
            translation_m="DO_NOT_EXPOSE_POSITION",
            native_state="DO_NOT_EXPOSE_NATIVE",
        )
    output["views"][0].update(correspondences="DO_NOT_EXPOSE_PIXELS", mask="DO_NOT_EXPOSE_MASK")
    output.update(
        images="DO_NOT_EXPOSE_IMAGES",
        thresholds={"private": "DO_NOT_EXPOSE_THRESHOLD"},
        grasp_success=True,
        detached=True,
        task_success=True,
    )
    recorded(tmp_path, [("so101-compare-visual-motion", output)])
    encoded = json.dumps(visual_feedback(tmp_path))
    assert "DO_NOT_EXPOSE" not in encoded
    for key in ("rotation_matrix", "translation_m", "grasp_success", "detached", "task_success"):
        assert key not in encoded


def test_occlusion_unknown_remains_unknown_despite_known_tool_motion(tmp_path):
    output = measurement(
        status="unknown",
        evidence="unknown",
        fruit_motion=None,
        relative_motion=None,
        reasons=["insufficient visible matched features"],
        quality={"tracks": 2, "inliers": 0},
        views=[{"camera": "agentview", "status": "unknown", "reason": "occluded"}],
    )
    recorded(tmp_path, [("so101-compare-visual-motion", output)])
    result = visual_feedback(tmp_path)
    row = result["recent_measurements"][0]
    assert row["status"] == row["evidence"] == "unknown"
    assert row["fruit_motion"] is None and row["relative_motion"] is None
    assert row["tool_motion"]["rotation_deg"] == 12.0
    assert result["evidence_counts"] == {"unknown": 1}


def test_only_allowlisted_comparison_outputs_are_read(tmp_path):
    files = recorded(
        tmp_path,
        [("so101-get-native-state", {"secret": "DO_NOT_EXPOSE"}), ("move-to-joints", {"ok": True})],
    )
    for entry in files:
        (tmp_path / entry["path"]).write_text("not JSON and not visual evidence")
    native = tmp_path / "evaluation/so101-task.json"
    native.parent.mkdir()
    native.write_text("not JSON and not public evidence")
    result = visual_feedback(tmp_path)
    assert result["indexed_comparison_calls"] == 0
    assert result["recent_measurements"] == []


def test_tampered_public_comparison_is_rejected(tmp_path):
    files = recorded(tmp_path, [("so101-compare-visual-motion", measurement())])
    (tmp_path / files[0]["path"]).write_text('{"ok": true}')
    with pytest.raises(ValueError, match="differs from its manifest"):
        visual_feedback(tmp_path)


def test_symlink_record_cannot_escape_episode(tmp_path):
    files = recorded(tmp_path, [("so101-compare-visual-motion", measurement())])
    record = tmp_path / files[0]["path"]
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside.write_bytes(record.read_bytes())
    record.unlink()
    try:
        record.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")
    with pytest.raises(ValueError, match="escapes the episode"):
        visual_feedback(tmp_path)


def test_malformed_numbers_are_excluded_and_messages_history_bounded(tmp_path):
    output = measurement(
        reasons=["x" * 1000] * 10,
        fruit_motion={"rotation_deg": float("nan")},
        relative_motion={"rotation_error_deg": -1, "translation_error_m": float("inf")},
        quality={"tracks": True, "inliers": -2, "inlier_fraction": 1.5, "residual_rms_m": -1},
        error={"code": "x" * 1000, "message": "y" * 1000, "details": "DO_NOT_EXPOSE"},
    )
    recorded(tmp_path, [("so101-compare-visual-motion", output) for _ in range(20)])
    result = visual_feedback(tmp_path)
    assert result["summarized_comparison_calls"] == 20
    assert result["earlier_measurements_omitted"] == 8
    assert len(result["recent_measurements"]) == 12
    assert result["recent_measurements"][0]["call_index"] == 8
    row = result["recent_measurements"][-1]
    assert row["fruit_motion"] is None and row["relative_motion"] is None
    assert row["quality"] == {}
    assert len(row["reasons"]) == 4 and len(row["reasons"][0]) == 160
    assert len(row["error"]["code"]) == 64 and len(row["error"]["message"]) == 240
    assert "DO_NOT_EXPOSE" not in json.dumps(result, allow_nan=False)


def test_duplicate_manifest_entries_are_rejected(tmp_path):
    files = recorded(tmp_path, [("so101-compare-visual-motion", measurement())])
    (tmp_path / "manifest.json").write_text(json.dumps({"files": files + files}))
    with pytest.raises(ValueError, match="Duplicate"):
        visual_feedback(tmp_path)


def test_oversized_output_is_rejected_before_parsing(tmp_path):
    files = recorded(tmp_path, [("so101-compare-visual-motion", measurement())])
    (tmp_path / files[0]["path"]).write_bytes(b" " * 262145)
    with pytest.raises(ValueError, match="bounded output size"):
        visual_feedback(tmp_path)


def test_invalid_comparison_output_is_counted_without_inventing_evidence(tmp_path):
    recorded(tmp_path, [("so101-compare-visual-motion", {"ok": "true", "status": "estimated"})])
    result = visual_feedback(tmp_path)
    assert result["indexed_comparison_calls"] == 1
    assert result["invalid_outputs_omitted"] == 1
    assert result["status_counts"] == {} and result["recent_measurements"] == []


def test_only_bounded_recent_comparisons_are_loaded(tmp_path, monkeypatch):
    monkeypatch.setattr("cap_harness.so101.visual_feedback._MAX_CALLS", 3)
    files = recorded(tmp_path, [("so101-compare-visual-motion", measurement()) for _ in range(5)])
    for entry in files[:2]:
        (tmp_path / entry["path"]).write_text("earlier records are not loaded")
    result = visual_feedback(tmp_path)
    assert result["indexed_comparison_calls"] == 5
    assert result["summarized_comparison_calls"] == 3
    assert result["earlier_calls_omitted"] == 2
    assert [row["call_index"] for row in result["recent_measurements"]] == [2, 3, 4]


def test_unknown_structured_values_are_not_copied_as_status_or_camera(tmp_path):
    output = measurement(
        status={"private": "DO_NOT_EXPOSE"},
        evidence=["DO_NOT_EXPOSE"],
        views=[{"camera": {"private": "DO_NOT_EXPOSE"}, "status": ["DO_NOT_EXPOSE"]}],
    )
    recorded(tmp_path, [("so101-compare-visual-motion", output)])
    result = visual_feedback(tmp_path)
    assert result["status_counts"] == result["evidence_counts"] == {}
    assert "DO_NOT_EXPOSE" not in json.dumps(result)
