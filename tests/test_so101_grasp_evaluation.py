"""Regressions for native grasp evidence; fixtures are synthetic, not robot trials."""

import copy
import json

import pytest

from cap_harness.so101 import campaign as c
from cap_harness.so101.skill_contracts import score

GRASP = "grasp_ripe_fruit_v1"


def record(run, *, duration=0.5, verified_time=2.0, **extra):
    evidence = {
        "grasp_verified_time_s": verified_time,
        "longest_bilateral_contact_s": duration,
        "forbidden_contact_pairs": [],
        "limit_violations": [],
        "retention_violations": [],
        "transport_violations": [],
        "non_finger_support_contacts": [],
        **extra,
    }
    c.write_json(run / "evaluation/so101-task.json", evidence)
    c.write_json(run / "outcome.json", {"program_ok": True, "task_success": False})
    return evidence


@pytest.mark.parametrize(
    "duration,verified_time,expected",
    [
        (0.5, 2.0, True),
        (0.4999999999999, 2.0, True),
        (0.5 - 2e-9, 2.0, False),
        (0.499, 2.0, False),
        (0.6, None, False),
    ],
)
def test_grasp_uses_native_rounding_tolerance_and_still_requires_native_witness(
    tmp_path, duration, verified_time, expected
):
    record(tmp_path, duration=duration, verified_time=verified_time)
    result = score(tmp_path, GRASP)
    assert result["passed"] is expected
    assert result["task_success"] is False
    assert result["measurements"]["longest_bilateral_contact_s"] == duration
    assert result["measurements"]["contact_hold_required_s"] == 0.5


@pytest.mark.parametrize(
    "contract",
    [
        "grasp_ripe_fruit_v1",
        "detach_ripe_fruit_v1",
        "retain_ripe_fruit_v1",
        "carry_ripe_fruit_v1",
        "deposit_ripe_fruit_v1",
    ],
)
def test_external_support_invalidates_otherwise_completed_physical_skill(tmp_path, contract):
    extra = {
        "release_event": {"synthetic": True},
        "fruit_detached": True,
        "fixture_active": False,
        "free_hold_verified_time_s": 5.0,
        "maximum_carried_distance_m": 0.2,
        "final_placement_predicate": True,
        "placement_hold_s": 1.1,
    }
    record(tmp_path, **extra)
    assert score(tmp_path, contract)["passed"]
    record(tmp_path, **extra, non_finger_support_contacts=[["plant_fruit", "work_surface"]])
    result = score(tmp_path, contract)
    assert not result["passed"]
    assert result["failures"] == ["scene_constraint_violation"]
    assert result["measurements"]["non_finger_support_recorded"] is True


def test_failed_grasp_feedback_exposes_only_scalar_post_episode_diagnostics(tmp_path):
    final = {
        "bilateral_qualified": False,
        "normal_dot_product": -0.25,
        "contact_separation_m": 0.019,
        "finger_forces_n": {"fixed": 0.3, "moving": 0.0, "private_extra": [9876, 9876, 9876]},
        "gripper_opening": 0.4,
        "fruit_position_m": [9876, 9876, 9876],
        "fruit_relative_to_tool_m": [9876, 9876, 9876],
        "across_fruit_center_dot_m2": 9876,
        "contacts": [{"position_m": [9876, 9876, 9876]}],
    }
    evidence = record(
        tmp_path,
        duration=0.15,
        verified_time=None,
        contact_hold_required_s=0.1,
        diagnostics={"final_state": final},
        skill_evaluation_reference={"fruit_position_m": [9876, 9876, 9876]},
    )
    original = copy.deepcopy(evidence)
    result = score(tmp_path, GRASP)
    assert not result["passed"]
    assert result["measurements"] == {
        "grasp_verified_time_s": None,
        "longest_bilateral_contact_s": 0.15,
        "contact_hold_required_s": 0.5,
        "non_finger_support_recorded": False,
        "final_contact": {
            "bilateral_qualified": False,
            "normal_dot_product": -0.25,
            "contact_separation_m": 0.019,
            "gripper_opening": 0.4,
            "finger_forces_n": {"fixed": 0.3, "moving": 0.0},
        },
    }
    assert "9876" not in json.dumps(result)
    assert c.read_json(tmp_path / "evaluation/so101-task.json") == original


def test_missing_diagnostics_are_not_reported_as_zero_forces_or_valid_final_grasp(tmp_path):
    record(tmp_path)
    result = score(tmp_path, GRASP)
    assert result["passed"]
    assert "final_contact" not in result["measurements"]


def test_historic_grasp_and_current_contact_remain_distinct(tmp_path):
    record(tmp_path, diagnostics={"final_state": {"bilateral_qualified": False}})
    result = score(tmp_path, GRASP)
    assert result["passed"]
    assert result["measurements"]["grasp_verified_time_s"] == 2.0
    assert result["measurements"]["final_contact"]["bilateral_qualified"] is False
