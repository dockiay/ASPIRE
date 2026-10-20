"""Separate task/protocol routing and bounded full-episode feedback."""

import functools
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from test_so101_campaign import rebuild_manifest

from cap_harness.so101 import campaign as c
from cap_harness.so101 import debug_tools as d
from cap_harness.so101.harvest_feedback import diagnostics
from cap_harness.so101.harvest_protocol import SUITE, cases, protocol

LIMITS = {"max_steps": 24, "timeout_s": 60.0, "max_attempts": 1, "width": 64, "height": 64}
RUNTIME = {"environment": {"MUJOCO_GL": "glfw"}}


def fake_harvest(command, attempt, env, timeout_s):
    assert command[command.index("--suite") + 1] == SUITE
    assert command[command.index("--seed") + 1] == "0"
    run = attempt / "episodes/0/run-fake"
    c.write_json(
        run / "outcome.json",
        {
            "program_ok": True,
            "task_success": False,
            "error": None,
            "termination_reason": "program_completed",
            "steps_executed": 8,
            "finalization_errors": [],
        },
    )
    c.write_json(
        run / "evaluation/so101-task.json",
        {"case": cases()[0], "task": SUITE, "task_success": False},
    )
    c.write_json(run / "evaluation/so101-case-protocol.json", protocol())
    c.write_json(
        run / "evaluation/so101-diagnostics.json",
        {
            "task_success": False,
            "status": "incomplete",
            "primary_finding": {"code": "placement_not_stable"},
            "findings": [
                {
                    "code": "placement_not_stable",
                    "message": "Not stable",
                    "time_s": 9,
                    "phase": "stable_placement_and_withdrawal",
                }
            ],
            "events": [],
            "final_state": {
                "phase": "stable_placement_and_withdrawal",
                "free_hold_verified": True,
                "destination_verified": True,
                "deposit_started": True,
                "placement_hold_s": 0.1,
                "container_base_contact": True,
                "ordered_stages_complete": True,
                "finger_forces_n": {"fixed": 0, "moving": 0},
                "gripper_opening": 1.0,
                "fruit_position_m": [99, 99, 99],
                "junction_load_n": 999,
            },
        },
    )
    program = Path(command[command.index("--program") + 1])
    (run / "source").mkdir()
    (run / "source/program.py").write_bytes(program.read_bytes())
    rebuild_manifest(run)
    return {"status": "exited", "returncode": 0, "wall_s": 0.01}


def service(tmp_path):
    ident = d.build_identity([0], LIMITS, RUNTIME, suite=SUITE)
    root = d.initialize(tmp_path / "session", ident)
    return d.DebugTools(
        root,
        runtime_check=False,
        snapshot=lambda identity: (
            {"task": identity["suite"], "simulation_steps": 0},
            {name: np.zeros((64, 64, 3), dtype=np.uint8) for name in d.CAMERAS},
        ),
        run_campaign=functools.partial(c.run_campaign, runner=fake_harvest),
    )


def execute(tools):
    return tools.call(
        "execute_program",
        {"code": "result = 0\n", "hypothesis": "Probe", "provenance": "public state"},
    )[0]


def test_tasks_have_separate_manifests_cases_and_language(tmp_path):
    harvest = d.build_identity(None, LIMITS, RUNTIME, suite=SUITE)
    previous = d.build_identity([101], LIMITS, RUNTIME)
    assert harvest["seeds"] == [0, 1001, 1002] and previous["seeds"] == [101]
    assert harvest["protocol_sha256"] != previous["protocol_sha256"]
    tools = service(tmp_path)
    task, _ = tools.call("describe_task", {})
    assert (
        task["task"] == SUITE and "container" in task["language"] and "withdraw" in task["language"]
    )
    assert "synthetic benchmark" in task["case_scope"]
    with pytest.raises(ValueError, match="identity changed"):
        d.initialize(tools.root, previous)


@pytest.mark.parametrize(
    "partition,seeds",
    [("development", [101]), ("development", [1]), ("validation", None), ("evaluation", None)],
)
def test_wrong_cases_and_reserved_partitions_are_rejected(partition, seeds):
    with pytest.raises(ValueError):
        c.build_identity(
            {"candidate": b"result = 0"}, partition, seeds, LIMITS, RUNTIME, suite=SUITE
        )


def test_native_suite_routing_feedback_filtering_and_resume(tmp_path):
    tools = service(tmp_path)
    snapshot, _ = tools.call("explore_scene", {})
    assert snapshot["public"]["task"] == SUITE
    result = execute(tools)
    assert result["comparison"]["recorded"] == 1
    feedback, _ = tools.call("inspect_results", {"candidate_id": result["candidate_id"]})
    row = feedback["feedback"]["cases"][0]
    assert row["harvest_progress"]["phase"] == "stable_placement_and_withdrawal"
    assert row["harvest_progress"]["placement_hold_s"] == 0.1
    assert row["findings"][0]["code"] == "placement_not_stable"
    assert "fruit_position_m" not in str(feedback) and "junction_load_n" not in str(feedback)
    tools.run_campaign = lambda *args, **kwargs: pytest.fail("Identical source must be cached")
    assert execute(tools)["comparison"]["recorded"] == 1
    assert len(list(tools.root.glob("candidates/*/campaign/attempts/*/*/attempt-*"))) == 1


def test_swapping_campaign_to_previous_suite_is_detected(tmp_path):
    tools = service(tmp_path)
    tools.call("explore_scene", {})
    candidate = execute(tools)["candidate_id"]
    path = tools.root / "candidates" / candidate / "campaign/campaign.json"
    value = c.read_json(path)
    value["suite"] = c.SUITE
    c.write_json(path, value)
    assert (
        "differs from the assigned task"
        in tools.call("inspect_results", {"candidate_id": candidate})[0]["error"]
    )


def test_other_protocol_cannot_be_rehashed_into_a_valid_episode(tmp_path):
    tools = service(tmp_path)
    tools.call("explore_scene", {})
    candidate = execute(tools)["candidate_id"]
    run = next(
        (tools.root / "candidates" / candidate).glob(
            "campaign/attempts/*/*/attempt-*/episodes/*/run-*"
        )
    )
    c.write_json(run / "evaluation/so101-case-protocol.json", c.protocol_for(c.SUITE))
    rebuild_manifest(run)
    assert (
        "protocol differs" in tools.call("inspect_results", {"candidate_id": candidate})[0]["error"]
    )


def test_resource_fingerprint_is_checked_during_execution(tmp_path, monkeypatch):
    from cap_harness.so101 import harvest_protocol as hp
    from cap_harness.so101 import perception

    monkeypatch.setattr(perception, "runtime_identity", lambda suite, env: {"backend": "fixture"})
    monkeypatch.setattr(c, "runtime_identity", lambda env: dict(RUNTIME))
    monkeypatch.setattr(hp, "resource_identity", lambda: {"files": {"fruit": "original"}})
    runtime = d.runtime_identity({}, SUITE)
    ident = d.build_identity([0], LIMITS, runtime, suite=SUITE)
    root = d.initialize(tmp_path / "runtime", ident)
    tools = d.DebugTools(root)
    tools.check_runtime()
    monkeypatch.setattr(hp, "resource_identity", lambda: {"files": {"fruit": "changed"}})
    with pytest.raises(ValueError, match="runtime changed"):
        tools.check_runtime()


def test_deposit_feedback_does_not_require_fingers_or_retention_at_end(monkeypatch):
    from cap_harness.so101.diagnostics import DetachmentDiagnostics

    monkeypatch.setattr(
        DetachmentDiagnostics,
        "snapshot",
        lambda env: {"bilateral_qualified": False, "current_retention_s": 0},
    )
    env = SimpleNamespace(
        sim=SimpleNamespace(data=SimpleNamespace(time=9.0)),
        task_name=SUITE,
        forbidden_contacts=set(),
        limit_violations=set(),
        retention_violations=set(),
        transport_violations=set(),
        early_closure=False,
        support_contacts=set(),
        frequency=20,
        grasp_time=1,
        detached_time=2,
        free_hold_verified_time=4,
        destination_ready_time=6,
        deposit_started_time=7,
        first_base_contact_time=8,
        placement_duration=0.1,
        has_base_contact=lambda: True,
        ordered_stages_complete=lambda: True,
        diagnostic_monitor=SimpleNamespace(events=[]),
    )
    report = diagnostics(env, {"stage": "stable_placement_and_withdrawal", "task_success": False})
    assert report["primary_finding"]["code"] == "placement_not_stable"
    assert report["events"][-1]["code"] == "container_base_contact"
    success = diagnostics(env, {"stage": "completed", "task_success": True})
    assert success["status"] == "completed" and not success["findings"]
