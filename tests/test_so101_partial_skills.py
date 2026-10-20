"""Partial skill acceptance and independent promotion; fixtures are explicitly synthetic."""

import functools
import json
from pathlib import Path

import numpy as np
import pytest
from test_so101_campaign import rebuild_manifest

from cap_harness.so101 import api_backend, pipeline, skills
from cap_harness.so101 import campaign as c
from cap_harness.so101 import debug_tools as d
from cap_harness.so101.harvest_protocol import case_for, protocol
from cap_harness.so101.skill_contracts import LOCALIZE, enrich, score

LIMITS = {"max_steps": 24, "timeout_s": 60.0, "max_attempts": 1, "width": 64, "height": 64}
RUNTIME = {"environment": {"MUJOCO_GL": "glfw"}}


def episode(run, point=None, target=None, **changes):
    target = target or [0, 0, 0.24]
    point = point or target
    evidence = {
        "case": case_for(0),
        "task_success": False,
        "final_fruit_position_m": target,
        "skill_evaluation_reference": {
            "fruit_position_m": target,
            "frame": "so101_base",
            "timestamp_s": 0,
        },
        "forbidden_contact_pairs": [],
        "limit_violations": [],
        **changes.pop("evidence", {}),
    }
    c.write_json(run / "evaluation/so101-task.json", evidence)
    c.write_json(
        run / "outcome.json",
        {
            "program_ok": True,
            "task_success": False,
            "steps_executed": changes.pop("steps", 0),
            "termination_reason": "program_completed",
            "finalization_errors": [],
            "error": None,
        },
    )
    c.write_json(
        run / "source/program-result.json",
        {
            "result": {
                "skill_results": {
                    LOCALIZE: {
                        "point_m": point,
                        "frame": changes.pop("frame", "so101_base"),
                        "timestamp_s": changes.pop("timestamp", 0),
                        "camera_names": ["agentview"],
                    }
                }
            },
            "calls": changes.pop(
                "calls",
                [{"tool": "segment_text", "ok": True}, {"tool": "mask_to_point_cloud", "ok": True}],
            ),
        },
    )


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({}, True),
        ({"point": [0.1, 0, 0.24]}, False),
        ({"steps": 1}, False),
        ({"frame": "world"}, False),
        ({"timestamp": 1}, False),
        ({"calls": []}, False),
        ({"evidence": {"forbidden_contact_pairs": ["robot/plant"]}}, False),
    ],
)
def test_localization_criterion_is_independent_of_harvest_but_rejects_invalid_evidence(
    tmp_path, changes, expected
):
    episode(tmp_path, **changes)
    measured = score(tmp_path, LOCALIZE)
    assert measured["passed"] is expected and measured["task_success"] is False
    assert "fruit_position_m" not in json.dumps(measured)


def test_grasp_can_pass_before_detachment_and_scene_violation_still_fails(tmp_path):
    episode(tmp_path, evidence={"grasp_verified_time_s": 0.8, "longest_bilateral_contact_s": 0.6})
    assert score(tmp_path, "grasp_ripe_fruit_v1")["passed"]
    assert not score(tmp_path, "detach_ripe_fruit_v1")["passed"]
    evidence = c.read_json(tmp_path / "evaluation/so101-task.json")
    evidence["limit_violations"] = ["excessive_model_finger_force"]
    c.write_json(tmp_path / "evaluation/so101-task.json", evidence)
    assert not score(tmp_path, "grasp_ripe_fruit_v1")["passed"]


def test_fixed_coordinate_inside_absolute_tolerance_fails_cross_scene_tracking(tmp_path):
    rows = []
    for i, target in enumerate(([0, 0, 0.24], [0.012, 0.012, 0.24])):
        run = tmp_path / str(i) / "run"
        episode(run, point=[0, 0, 0.24], target=target)
        assert score(run, LOCALIZE)["passed"]  # Both are within 20 mm, alone.
        rows.append(
            {"program": "candidate", "attempts": [{"directory": str(i)}], "episode": {"run": "run"}}
        )
    measured = enrich(
        tmp_path,
        {"cases": rows, "comparison": {"candidate": {"planned": 2, "task_success": 0}}},
        LOCALIZE,
    )
    assert measured["comparison"]["candidate"]["skill_success"] == 0
    assert all(
        "cross_case_tracking_inconsistent" in row["skill_evaluation"]["failures"]
        for row in measured["cases"]
    )


@pytest.mark.parametrize(
    "name,removed",
    [
        ("detach_ripe_fruit_v1", {"fixture_active": True}),
        ("retain_ripe_fruit_v1", {"free_hold_verified_time_s": None}),
        ("carry_ripe_fruit_v1", {"maximum_carried_distance_m": 0.149}),
        ("deposit_ripe_fruit_v1", {"placement_hold_s": 0.999}),
    ],
)
def test_each_physical_partial_contract_preserves_its_own_predicate(tmp_path, name, removed):
    evidence = {
        "grasp_verified_time_s": 0.5,
        "longest_bilateral_contact_s": 0.6,
        "release_event": {"synthetic": True},
        "fruit_detached": True,
        "fixture_active": False,
        "free_hold_verified_time_s": 3.0,
        "maximum_carried_distance_m": 0.15,
        "final_placement_predicate": True,
        "placement_hold_s": 1.0,
    }
    episode(tmp_path, evidence=evidence)
    assert score(tmp_path, name)["passed"]
    assert not score(tmp_path, "harvest_complete_v1")["passed"]
    episode(tmp_path, evidence={**evidence, **removed})
    assert not score(tmp_path, name)["passed"]


def runner(command, attempt, env, timeout_s):
    """Native artifact contract fixture; no simulator and no true learning claim."""
    import cv2

    seed = int(command[command.index("--seed") + 1])
    source = Path(command[command.index("--program") + 1])
    target = [0, 0, 0.24] if seed == 0 else [0.012, 0.012, 0.24]
    point = target if "bad.md" not in source.read_text() else [0.2, 0.2, 0.24]
    run = attempt / "episodes" / str(seed) / "run-fixture"
    episode(run, point=point, target=target)
    evidence = c.read_json(run / "evaluation/so101-task.json")
    c.write_json(run / "evaluation/so101-task.json", {**evidence, "case": case_for(seed)})
    c.write_json(run / "evaluation/so101-case-protocol.json", protocol())
    c.write_json(
        run / "evaluation/so101-diagnostics.json",
        {
            "status": "incomplete",
            "task_success": False,
            "primary_finding": {"code": "grasp_not_qualified"},
            "findings": [],
            "events": [],
            "final_state": {},
        },
    )
    (run / "source/program.py").write_bytes(source.read_bytes())
    video = run / "media/videos/agentview.mp4"
    video.parent.mkdir(parents=True)
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 20, (64, 64))
    writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()
    rebuild_manifest(run)
    return {"status": "exited", "returncode": 0, "wall_s": 0.01}


def proposal(name):
    return {
        "skill": name,
        "title": "Fixture localization",
        "trigger": "Synthetic test context only",
        "code": "result = get_robot_state()",
        "evidence": "Synthetic test evidence; never a real learned pattern",
        "evidence_candidate_ids": ["c-" + "1" * 16],
        "verification_contract": LOCALIZE,
    }


def worker(workspace, provider, identity, timeout):
    tools = d.DebugTools(
        workspace,
        runtime_check=False,
        run_campaign=functools.partial(c.run_campaign, runner=runner),
        snapshot=lambda ident: (
            {"simulation_steps": 0},
            {name: np.zeros((64, 64, 3), dtype=np.uint8) for name in d.CAMERAS},
        ),
    )
    tools.call("describe_task", {})
    tools.call("explore_scene", {})
    result, _ = tools.call(
        "execute_program",
        {
            "code": "result = " + repr(identity["verification_skill"]),
            "hypothesis": "Explicit synthetic fixture",
            "provenance": "No real targets",
        },
    )
    candidate = result["candidate_id"]
    tools.call("inspect_results", {"candidate_id": candidate})
    tools.call(
        "view_frame",
        {"candidate_id": candidate, "case_index": 0, "camera": "agentview", "frame_index": 0},
    )
    tools.call(
        "finish_session",
        {
            "candidate_id": candidate,
            "analysis": "Synthetic fixture; no harvest success",
            "skill_report": {
                "skill_library_sha": identity["skill_library"]["sha256"],
                "consulted": [
                    {
                        "skill": identity["verification_skill"],
                        "verdict": "useful",
                        "evidence": "Synthetic fixture of application review",
                    }
                ],
                "proposed_edits": [],
                "proposed_new": [],
            },
        },
    )


@pytest.mark.parametrize("application_verified,expected", [(True, ["good.md"]), (False, [])])
def test_scoped_promotion_is_per_skill_and_requires_application_review_and_reaudits_on_resume(
    tmp_path, application_verified, expected
):
    directory = tmp_path / "library"
    library = skills.snapshot(directory)
    identity = {
        "skill_library": library,
        "dev_seeds": [0, 1001, 1002],
        "limits": LIMITS,
        "runtime": RUNTIME,
        "provider": {"type": "fixture"},
        "agent_timeout_s": 60,
    }
    report = {"proposed_new": [proposal("good.md"), proposal("bad.md")], "proposed_edits": []}
    calls = []

    def launch(*args):
        calls.append(args[0])
        worker(*args)

    audit = lambda *args: {"verdict": "PASS", "skill_application_verified": application_verified}
    result = pipeline.verify_skills(
        tmp_path / "learning", identity, report, {}, directory, launch, audit
    )
    assert result["promoted_skills"] == expected
    assert list(skills.snapshot(directory)["contents"]) == expected
    assert len(calls) == 2
    for row in result["jobs"]:
        path = (
            tmp_path / "learning/verification/so101__so101_fruitgym_harvest__task_0" / row["report"]
        )
        assert c.read_json(path)["comparison"]["task_success"] == 0
    resumed = pipeline.verify_skills(
        tmp_path / "learning",
        identity,
        report,
        {},
        directory,
        lambda *args: pytest.fail("resume must not launch a model"),
        audit,
    )
    assert resumed == result
    selected_finish = calls[0] / "finish.json"
    c.write_json(selected_finish, {"tampered": True})
    with pytest.raises(ValueError, match="finish changed"):
        pipeline.verify_skills(
            tmp_path / "learning", identity, report, {}, directory, launch, audit
        )


def test_api_strict_schema_preserves_optional_contract_semantics():
    definitions = api_backend.tool_definitions()
    finish = next(item for item in definitions if item["name"] == "finish_session")
    new = finish["parameters"]["properties"]["skill_report"]["properties"]["proposed_new"]["items"]
    assert set(new["required"]) == set(new["properties"])
    assert new["properties"]["verification_contract"]["anyOf"][1] == {"type": "null"}
    assert "verification_contract" not in skills.NEW_SCHEMA["required"]
