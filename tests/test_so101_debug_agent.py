"""Controlled agent boundary tests; synthetic episodes, no reserved physics."""

import asyncio
import functools
import json
import os
import sys

import numpy as np
import pytest
from test_so101_campaign import fake_runner, rebuild_manifest

from cap_harness.so101 import campaign as c
from cap_harness.so101 import codex_backend as backend
from cap_harness.so101 import debug_agent as agent
from cap_harness.so101 import debug_tools as d

LIMITS = {"max_steps": 24, "timeout_s": 60.0, "max_attempts": 1, "width": 64, "height": 64}
RUNTIME = {"environment": {"MUJOCO_GL": "glfw"}}


def runner(command, attempt, env, timeout_s):
    result = fake_runner(command, attempt, env, timeout_s)
    run = next(attempt.glob("episodes/*/run-*"))
    path = run / "evaluation/so101-diagnostics.json"
    diagnosis = c.read_json(path)
    diagnosis.update(
        events=[],
        findings=[],
        final_state={
            "finger_forces_n": {"fixed": 0.0, "moving": 0.0},
            "gripper_opening": 1.0,
            "fruit_position_m": [99, 99, 99],
            "junction_load_n": 999,
        },
    )
    c.write_json(path, diagnosis)
    import cv2

    video = run / "media/videos/agentview.mp4"
    video.parent.mkdir(parents=True)
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 20, (64, 64))
    assert writer.isOpened()
    writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()
    rebuild_manifest(run)
    return result


def service(tmp_path, **kwargs):
    identity = d.build_identity([101, 102], dict(LIMITS), RUNTIME, **kwargs)
    root = d.initialize(tmp_path / "session", identity)
    snapshots = []

    def snapshot(identity):
        snapshots.append(identity)
        return {"simulation_steps": 0}, {
            name: np.zeros((64, 64, 3), dtype=np.uint8) for name in d.CAMERAS
        }

    tools = d.DebugTools(
        root,
        snapshot=snapshot,
        run_campaign=functools.partial(c.run_campaign, runner=runner),
        runtime_check=False,
    )
    return tools, snapshots


def submit(tools, code="result = 0\n"):
    return tools.call(
        "execute_program", {"code": code, "hypothesis": "test", "provenance": "public API only"}
    )[0]


def test_reserved_cases_and_changed_identity_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="partition"):
        d.build_identity([1], LIMITS, RUNTIME)
    tools, _ = service(tmp_path)
    changed = {**tools.identity, "max_programs": 9}
    with pytest.raises(ValueError, match="identity changed"):
        d.initialize(tools.root, changed)


def test_exploration_cached_zero_steps_and_images_audited(tmp_path):
    tools, snapshots = service(tmp_path)
    assert submit(tools)["ok"] is False
    first, images = tools.call("explore_scene", {})
    assert first["public"]["simulation_steps"] == 0 and len(images) == 2
    tools.call("explore_scene", {})
    assert len(snapshots) == 1
    images[0].write_bytes(b"changed")
    assert "modified" in tools.call("explore_scene", {})[0]["error"]


def test_rejection_consumes_budget_and_duplicates_reuse_evidence(tmp_path):
    tools, _ = service(tmp_path, max_programs=2)
    tools.call("explore_scene", {})
    assert submit(tools, "import os\n")["status"] == "rejected"
    good = submit(tools)
    assert good["comparison"]["recorded"] == 2
    attempts = list(tools.root.glob("candidates/*/campaign/attempts/*/*/attempt-*"))
    tools.run_campaign = lambda *args, **kwargs: pytest.fail(
        "Identical candidate must not execute again"
    )
    assert submit(tools)["comparison"] == good["comparison"]
    assert len(attempts) == 2
    assert "budget exhausted" in submit(tools, "result = 1\n")["error"]


def test_autonomous_worker_cannot_use_legacy_approach_strategy(tmp_path):
    tools, _ = service(tmp_path)
    tools.call("explore_scene", {})
    result = submit(tools, "result = so101.plan_open_approach([0.3, 0, 0.2])\n")
    assert result["status"] == "rejected"
    assert "general motion primitives" in result["error"]


def test_feedback_filters_native_state_and_detects_changed_results(tmp_path):
    tools, _ = service(tmp_path)
    tools.call("explore_scene", {})
    result = submit(tools)
    feedback, _ = tools.call("inspect_results", {"candidate_id": result["candidate_id"]})
    assert "finger_forces_n" in json.dumps(feedback)
    assert "fruit_position_m" not in json.dumps(feedback)
    assert "junction_load_n" not in json.dumps(feedback)
    path = tools.root / "candidates" / result["candidate_id"] / "result.json"
    result["comparison"]["task_success"] = 2
    c.write_json(path, result)
    assert (
        "differs"
        in tools.call("inspect_results", {"candidate_id": result["candidate_id"]})[0]["error"]
    )


def test_frames_are_bounded_and_video_hash_is_required(tmp_path):
    tools, _ = service(tmp_path)
    tools.call("explore_scene", {})
    candidate = submit(tools)["candidate_id"]
    args = {"candidate_id": candidate, "case_index": 0, "camera": "agentview", "frame_index": 0}
    assert tools.call("view_frame", {**args, "camera": "../other"})[0]["ok"] is False
    assert tools.call("view_frame", {**args, "frame_index": 99})[0]["ok"] is False
    record, images = tools.call("view_frame", args)
    assert record["frame_count"] == 1 and len(images) == 1
    video = next(
        tools.root.glob(
            "candidates/*/campaign/attempts/*/*/attempt-*/episodes/*/*/media/videos/agentview.mp4"
        )
    )
    video.write_bytes(b"tampered")
    assert tools.call("view_frame", args)[0]["ok"] is False
    assert tools.call("inspect_results", {"candidate_id": "../outside"})[0]["ok"] is False


def test_finish_requires_inspection_and_frame_preserves_best_and_pending(tmp_path):
    tools, _ = service(tmp_path)
    tools.call("explore_scene", {})
    first = submit(tools)["candidate_id"]
    second = submit(tools, "result = 1\n")["candidate_id"]
    finish = {"candidate_id": first, "analysis": "No physical success"}
    assert "Inspect" in tools.call("finish_session", finish)[0]["error"]
    for candidate in (first, second):
        tools.call("inspect_results", {"candidate_id": candidate})
        tools.call(
            "view_frame",
            {"candidate_id": candidate, "case_index": 0, "camera": "agentview", "frame_index": 0},
        )
    assert (
        "highest scoring"
        in tools.call("finish_session", {**finish, "candidate_id": second})[0]["error"]
    )
    result = tools.call("finish_session", finish)[0]
    assert result["provenance_audit"] == "PENDING"
    assert result["reserved_cases_executed"] is result["verified_skill_promoted"] is False
    assert submit(tools, "result = 2\n")["ok"] is False

    from cap_harness.so101.handoff import export_handoff

    handoff = export_handoff(tools.root)
    assert handoff["candidate_count"] == 2
    assert handoff["canonical_stage1_complete"] is False
    assert (tools.root / "worker-handoff/fix_code.py").read_text() == "result = 0\n"
    assert export_handoff(tools.root) == handoff
    (tools.root / "worker-handoff/fix_code.py").write_text("tampered\n")
    with pytest.raises(ValueError, match="modified"):
        export_handoff(tools.root)


def test_call_budget_survives_new_service_instance(tmp_path):
    tools, _ = service(tmp_path, max_calls=1)
    tools.call("describe_task", {})
    resumed = d.DebugTools(tools.root, runtime_check=False)
    with pytest.raises(ValueError, match="budget exhausted"):
        resumed.call("describe_task", {})


def test_infrastructure_block_can_close_without_inventing_a_frame(tmp_path):
    tools, _ = service(tmp_path)
    tools.run_campaign = functools.partial(
        c.run_campaign,
        runner=lambda *args: {"status": "timeout", "returncode": -9, "wall_s": 60},
    )
    tools.call("explore_scene", {})
    candidate = submit(tools)["candidate_id"]
    tools.call("inspect_results", {"candidate_id": candidate})
    finish, images = tools.call(
        "finish_session",
        {"candidate_id": candidate, "analysis": "Infrastructure exhausted; no physical evidence"},
    )
    assert finish["status"] == "infrastructure_blocked" and not images
    assert finish["comparison"]["recorded"] == 0
    assert finish["canonical_stage1_complete"] is False


def test_codex_mcp_is_explicit_opt_in():
    request = {"directory": "/tmp/agent", "codex": "codex"}
    assert not any("mcp_servers" in arg for arg in backend.codex_command(request))
    command = backend.codex_command(
        {**request, "mcp": {"command": "python", "enabled_tools": list(d.TOOLS)}}
    )
    assert 'mcp_servers.so101.command="python"' in command
    assert "shell_tool" in command and "multi_agent" in command


@pytest.mark.parametrize(
    "claim,extra,error",
    [
        (False, None, None),
        (True, None, "completion claim"),
        (False, {"type": "command_execution"}, "unapproved tool"),
        (
            False,
            {"type": "mcp_tool_call", "server": "other", "tool": "describe_task"},
            "unapproved MCP",
        ),
    ],
)
def test_agent_trace_and_completion_are_checked_against_episodes(tmp_path, claim, extra, error):
    tools, _ = service(tmp_path)
    tools.call("explore_scene", {})
    candidate = submit(tools)["candidate_id"]
    tools.call("inspect_results", {"candidate_id": candidate})
    tools.call(
        "view_frame",
        {"candidate_id": candidate, "case_index": 0, "camera": "agentview", "frame_index": 0},
    )
    tools.call("finish_session", {"candidate_id": candidate, "analysis": "No harvest"})
    model = tools.root / "model"
    c.write_json(model / "request.json", {"test": "fake model, real evidence audit"})
    c.write_json(
        model / "response.json",
        {"candidate_id": candidate, "analysis": "No harvest", "task_completed": claim},
    )
    c.write_json(
        model / "worker-result.json",
        {
            "status": "ok",
            "request_sha256": c.file_sha(model / "request.json"),
            "response_sha256": c.file_sha(model / "response.json"),
        },
    )
    events = [
        {
            "type": "item.completed",
            "item": {"type": "mcp_tool_call", "server": "so101", "tool": name},
        }
        for name in d.TOOLS
    ]
    if extra:
        events.append({"type": "item.completed", "item": extra})
    (model / "events.jsonl").write_text("\n".join(json.dumps(row) for row in events))
    if error:
        with pytest.raises(ValueError, match=error):
            agent.audit_agent(tools.root, model)
    else:
        assert agent.audit_agent(tools.root, model)["completed_tool_calls"] == list(d.TOOLS)


def test_actual_stdio_mcp_lists_only_six_tools_and_validates_schema(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    tools, _ = service(tmp_path)

    async def check():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "cap_harness.so101.debug_mcp", "--workspace", str(tools.root)],
            env=dict(os.environ),
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
            await client.initialize()
            listed = await client.list_tools()
            assert {t.name for t in listed.tools} == set(d.TOOLS)
            result = await client.call_tool("describe_task", {})
            assert (
                not result.isError
                and json.loads(result.content[0].text)["partition"] == "development"
            )
            rejected = await client.call_tool("describe_task", {"seed": 1})
            assert rejected.isError

    asyncio.run(check())
