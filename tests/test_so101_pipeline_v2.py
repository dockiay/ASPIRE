"""Independent transport/protocol tests; synthetic runners never claim real harvest."""

import base64
import functools
import itertools
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from test_so101_campaign import rebuild_manifest

from cap_harness.so101 import api_backend, debug_agent, pipeline, skills
from cap_harness.so101 import campaign as c
from cap_harness.so101 import debug_tools as d
from cap_harness.so101.harvest import SO101FruitGymHarvestEnvironment
from cap_harness.so101.harvest_feedback import diagnostics
from cap_harness.so101.harvest_protocol import SUITE, case_for, protocol

LIMITS = {"max_steps": 24, "timeout_s": 60.0, "max_attempts": 1, "width": 64, "height": 64}
RUNTIME = {"environment": {"MUJOCO_GL": "glfw"}}


def empty_report(library):
    return {
        "skill_library_sha": library["sha256"],
        "consulted": [],
        "proposed_edits": [],
        "proposed_new": [],
    }


def test_large_public_reports_preserve_errors_and_typed_failures():
    from cap_harness.so101.public_feedback import program_feedback

    document = {
        "result": {
            "logs": [
                [
                    "move",
                    {
                        "ok": False,
                        "final_observation": {
                            "cameras": {"rgb": "pixels" * 20000},
                            "robot_state": {"joints": [1, 2, 3, 4, 5]},
                        },
                        "error": {"code": "timeout", "message": "cannot reach target"},
                    },
                ],
                ["error", "Bilateral grasp absent"],
            ]
        },
        "calls": [
            {
                "index": 5,
                "tool": "move_to_pose",
                "ok": True,
                "failure_code": "timeout",
                "outputs_summary": {"ok": False, "steps_executed": 60},
            }
        ],
        "error": {"message": "large observation repr " * 3000 + "FINAL_ACTION_CAUSE"},
        "stdout": "public output",
    }
    feedback = program_feedback(document)
    assert len(json.dumps(feedback["result"]).encode()) <= 12000
    assert "Bilateral grasp absent" in str(feedback["result"])
    assert "cannot reach target" in str(feedback["result"])
    assert "robot_state" in str(feedback["result"]) and "pixels" not in str(feedback)
    assert feedback["failed_public_calls"][0]["failure_code"] == "timeout"
    assert feedback["execution_error_tail"].endswith("FINAL_ACTION_CAUSE")


def test_missing_api_key_does_not_create_an_indeterminate_paid_receipt(tmp_path, monkeypatch):
    monkeypatch.delenv("ASPIRE_MISSING_FIXTURE_KEY", raising=False)
    spec = api_backend.provider_spec(
        {"type": "api", "model": "fixture", "api_key_env": "ASPIRE_MISSING_FIXTURE_KEY"}
    )
    with pytest.raises(ValueError, match="Missing API credential"):
        api_backend.run(
            tmp_path,
            spec,
            "test",
            debug_agent.RESPONSE_SCHEMA,
            service=SimpleNamespace(identity={"max_calls": 4}),
        )
    assert not (tmp_path / "model/request.json").exists()


def test_partition_variations_are_disjoint_reproducible_and_reserved():
    groups = pipeline.partitions()
    assert groups == {
        "development": [0, 1001, 1002],
        "validation": [2001, 2002],
        "evaluation": [3001, 3002, 3003],
    }
    assert len({tuple(row["plant_offset_m"]) for row in protocol()["cases"]}) == 8
    with pytest.raises(ValueError, match="partition"):
        d.build_identity([2001], LIMITS, RUNTIME, suite=SUITE)
    for seed in itertools.chain.from_iterable(groups.values()):
        assert case_for(seed) == case_for(seed)
    with pytest.raises(ValueError, match="Unknown"):
        case_for(123456)


@pytest.mark.parametrize("center", [(0.245, -0.16), (0.22, -0.17), (0.28, -0.13)])
@pytest.mark.parametrize("height", [0.055, 0.105, 0.19])
def test_destination_accepts_usable_volume_without_old_waypoint(center, height):
    low = np.array([center[0] - 0.018, center[1] - 0.017, height - 0.024])
    high = low + [0.036, 0.034, 0.048]
    env = SimpleNamespace(container_center=(0.245, -0.16), fruit_bounds=lambda: (low, high))
    assert SO101FruitGymHarvestEnvironment.over_destination(env)


@pytest.mark.parametrize(
    "low,high",
    [
        ([0.10, -0.17, 0.1], [0.14, -0.13, 0.15]),
        ([0.23, -0.17, -0.01], [0.26, -0.13, 0.04]),
        ([0.23, -0.17, 0.3], [0.26, -0.13, 0.35]),
    ],
)
def test_destination_rejects_outside_floor_or_excessive_height(low, high):
    env = SimpleNamespace(
        container_center=(0.245, -0.16), fruit_bounds=lambda: (np.array(low), np.array(high))
    )
    assert not SO101FruitGymHarvestEnvironment.over_destination(env)


def test_temporal_feedback_preserves_first_force_event_and_action(monkeypatch):
    from cap_harness.so101.diagnostics import DetachmentDiagnostics

    monkeypatch.setattr(DetachmentDiagnostics, "snapshot", lambda env: {})
    event = {
        "code": "finger_force_limit_exceeded",
        "time_s": 0.182,
        "phase": "approach_and_grasp",
        "active_command": {"kind": "gripper"},
        "evidence": {"peak_finger_forces_n": {"fixed": 14}},
        "detail": None,
    }
    env = SimpleNamespace(
        sim=SimpleNamespace(data=SimpleNamespace(time=9)),
        diagnostic_monitor=SimpleNamespace(events=[event]),
        forbidden_contacts=set(),
        limit_violations={"excessive_model_finger_force"},
        retention_violations=set(),
        transport_violations=set(),
        early_closure=False,
        support_contacts=set(),
        task_name=SUITE,
        grasp_time=None,
        detached_time=None,
        free_hold_verified_time=None,
        destination_ready_time=None,
        deposit_started_time=None,
        first_base_contact_time=None,
        placement_duration=0,
        has_base_contact=lambda: False,
        ordered_stages_complete=lambda: False,
    )
    report = diagnostics(env, {"stage": "approach_and_grasp", "task_success": False})
    assert report["findings"][0]["time_s"] == 0.182
    assert report["findings"][0]["active_command"] == {"kind": "gripper"}
    assert report["events"][0] == event


def test_skill_report_is_authored_and_promotion_requires_independent_evidence(tmp_path):
    library = skills.snapshot(tmp_path)
    report = empty_report(library)
    candidate = "c-" + "1" * 16
    proposal = {
        "skill": "contact-monitor.md",
        "title": "Read virtual contacts",
        "trigger": "When the virtual contact sensor is available",
        "code": "result = so101.get_finger_contacts()",
        "evidence": "The named development candidate read the sensor successfully; independent verification is still required.",
        "evidence_candidate_ids": [candidate],
    }
    report["proposed_new"] = [proposal]
    skills.validate_report(report, library, {candidate})
    with pytest.raises(ValueError, match="Independent"):
        skills.promote(tmp_path, library, [proposal], {"status": "verified"})
    proposed = skills.proposal_snapshot(library, [proposal])
    verification = {
        "status": "verified",
        "provenance_audit": "PASS",
        "independent": True,
        "no_proposer_code": True,
        "library_sha256": proposed["sha256"],
    }
    promoted = skills.promote(tmp_path, library, [proposal], verification)
    assert skills.snapshot(tmp_path) == promoted
    assert skills.promote(tmp_path, library, [proposal], verification) == promoted
    (tmp_path / "contact-monitor.md").write_text("tampered")
    with pytest.raises(ValueError, match="modified"):
        skills.snapshot(tmp_path)


def test_api_uses_same_tools_images_and_never_resubmits_on_resume(tmp_path):
    from PIL import Image

    root = tmp_path / "api"
    root.mkdir()
    image = root / "frame.png"
    Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8)).save(image)
    calls = []
    service = SimpleNamespace(identity={"max_calls": 12})

    def tool_call(name, args):
        calls.append(name)
        if name == "finish_session":
            c.write_json(root / "finish.json", {"candidate_id": "c-" + "1" * 16})
        return {"ok": True}, [image] if name in ("explore_scene", "view_frame") else []

    service.call = tool_call

    def audit_images(action):
        for row in action["images"]:
            assert c.file_sha(root / row["path"]) == row["sha256"]

    service.audit_images = audit_images
    names = list(d.TOOLS)
    args = [
        {},
        {},
        {"code": "result = 0", "hypothesis": "transport fixture", "provenance": "public"},
        {"candidate_id": "c-" + "1" * 16},
        {"candidate_id": "c-" + "1" * 16, "case_index": 0, "camera": "agentview", "frame_index": 0},
        {
            "candidate_id": "c-" + "1" * 16,
            "analysis": "No harvest",
            "skill_report": empty_report(skills.snapshot(tmp_path / "library")),
        },
    ]
    requests = []

    def requester(spec, payload, timeout):
        requests.append(payload)
        index = len(requests) - 1
        assert {tool["name"] for tool in payload["tools"]} == set(d.TOOLS)
        assert timeout > 0
        if index < 6:
            return {
                "status": "completed",
                "output": [
                    {
                        "type": "function_call",
                        "name": names[index],
                        "arguments": json.dumps(args[index]),
                        "call_id": str(index),
                    }
                ],
            }
        return {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "candidate_id": "c-" + "1" * 16,
                                    "analysis": "No harvest",
                                    "task_completed": False,
                                }
                            ),
                        }
                    ],
                }
            ],
        }

    spec = api_backend.provider_spec({"type": "api", "model": "test-model"})
    api_backend.run(
        root,
        spec,
        "transport fixture",
        debug_agent.RESPONSE_SCHEMA,
        requester=requester,
        service=service,
    )
    assert calls == list(d.TOOLS)
    image_outputs = [
        part
        for item in requests[-1]["input"]
        if item.get("type") == "function_call_output"
        for part in item["output"]
        if part["type"] == "input_image"
    ]
    assert (
        len(image_outputs) == 2
        and base64.b64decode(image_outputs[0]["image_url"].split(",")[1]) == image.read_bytes()
    )
    api_backend.run(
        root,
        spec,
        "transport fixture",
        debug_agent.RESPONSE_SCHEMA,
        requester=lambda *args: pytest.fail("resume must not call model"),
        service=service,
    )
    assert calls == list(d.TOOLS)


def test_indeterminate_api_call_is_preserved_without_billing_retry(tmp_path):
    service = SimpleNamespace(identity={"max_calls": 4})
    spec = api_backend.provider_spec({"type": "api", "model": "test-model"})

    def timeout(*args):
        raise ValueError("provider timeout")

    with pytest.raises(ValueError, match="timeout"):
        api_backend.run(
            tmp_path, spec, "test", debug_agent.RESPONSE_SCHEMA, requester=timeout, service=service
        )
    with pytest.raises(ValueError, match="Indeterminate API"):
        api_backend.run(
            tmp_path,
            spec,
            "test",
            debug_agent.RESPONSE_SCHEMA,
            requester=lambda *a: pytest.fail("must not retry"),
            service=service,
        )


def test_api_http_transport_uses_environment_credential_without_persisting_it(monkeypatch):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading

    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(
                (
                    self.path,
                    self.headers.get("Authorization"),
                    json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                )
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"completed","output":[]}')

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("ASPIRE_FIXTURE_KEY", "synthetic-test-token")
    spec = api_backend.provider_spec(
        {
            "type": "api",
            "model": "fixture",
            "base_url": f"http://127.0.0.1:{server.server_port}/v1",
            "api_key_env": "ASPIRE_FIXTURE_KEY",
        }
    )
    try:
        assert (
            api_backend.post(spec, {"model": "fixture", "input": "test"}, 5)["status"]
            == "completed"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert received == [
        ("/v1/responses", "Bearer synthetic-test-token", {"model": "fixture", "input": "test"})
    ]
    assert "synthetic-test-token" not in json.dumps(spec)


@pytest.mark.parametrize(
    "audit_verdict,expected", [("PASS", "verified"), ("QUARANTINED", "refuted")]
)
def test_verifier_is_isolated_and_promotion_depends_on_its_evidence(
    tmp_path, audit_verdict, expected
):
    root = tmp_path / "campaign"
    proposer = root / "so101" / SUITE / "task_0"
    proposer.mkdir(parents=True)
    (proposer / "fix_code.py").write_text("PROPOSER_CODE_MUST_NOT_REACH_VERIFIER")
    directory = tmp_path / "library"
    library = skills.snapshot(directory)
    proposal = {
        "skill": "contacts.md",
        "title": "Read contacts",
        "trigger": "When virtual contact sensing is available",
        "code": "result = so101.get_finger_contacts()",
        "evidence": "Synthetic fixture evidence only",
        "evidence_candidate_ids": ["c-" + "1" * 16],
    }
    report = {**empty_report(library), "proposed_new": [proposal]}
    identity = {
        "skill_library": library,
        "dev_seeds": [0, 1001, 1002],
        "limits": LIMITS,
        "runtime": RUNTIME,
        "provider": {"type": "fixture"},
        "agent_timeout_s": 60,
    }
    calls = []

    def worker(workspace, spec, worker_identity, timeout):
        calls.append(workspace)
        assert not workspace.is_relative_to(proposer)
        prompt = debug_agent.agent_prompt(workspace, worker_identity)
        assert "PROPOSER_CODE_MUST_NOT_REACH_VERIFIER" not in prompt
        assert worker_identity["verifier"] and worker_identity["max_programs"] == 2
        assert worker_identity["seeds"] == [0, 1001]
        # Explicit synthetic fixture, never a real physical verification claim.
        c.write_json(
            workspace / "finish.json", {"comparison": {"task_success": 2, "program_ok": 2}}
        )

    auditor = lambda workspace, spec: {"verdict": audit_verdict}
    result = pipeline.verify_skills(root, identity, report, {}, directory, worker, auditor)
    assert result["verdict"] == expected
    assert bool(skills.snapshot(directory)["contents"]) == (expected == "verified")
    assert pipeline.verify_skills(root, identity, report, {}, directory, worker, auditor) == result
    assert len(calls) == 1


def test_native_campaign_coordinator_adapter_and_resume(tmp_path, monkeypatch):
    """Synthetic native artifact fixture, including failed physical outcomes."""
    executed = []
    monkeypatch.setattr(d, "runtime_identity", lambda env, suite: RUNTIME)

    def runner(command, attempt, env, timeout_s):
        import cv2

        seed = int(command[command.index("--seed") + 1])
        executed.append(seed)
        run = attempt / "episodes" / str(seed) / "run-fixture"
        c.write_json(
            run / "outcome.json",
            {
                "program_ok": True,
                "task_success": False,
                "error": None,
                "termination_reason": "program_completed",
                "steps_executed": 1,
                "finalization_errors": [],
            },
        )
        c.write_json(
            run / "evaluation/so101-task.json",
            {"case": case_for(seed), "task": SUITE, "task_success": False},
        )
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
        program = Path(command[command.index("--program") + 1])
        (run / "source").mkdir()
        (run / "source/program.py").write_bytes(program.read_bytes())
        video = run / "media/videos/agentview.mp4"
        video.parent.mkdir(parents=True)
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 20, (64, 64))
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
        writer.release()
        rebuild_manifest(run)
        return {"status": "exited", "returncode": 0, "wall_s": 0.01}

    evaluator = functools.partial(c.run_campaign, runner=runner)

    def worker(root, spec, identity, timeout):
        if (root / "finish.json").exists():
            return
        tools = d.DebugTools(
            root,
            runtime_check=False,
            run_campaign=evaluator,
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
                "code": "result = 0\n",
                "hypothesis": "synthetic fixture",
                "provenance": "no object targets",
            },
        )
        candidate = result["candidate_id"]
        tools.call("inspect_results", {"candidate_id": candidate})
        tools.call(
            "view_frame",
            {"candidate_id": candidate, "case_index": 0, "camera": "agentview", "frame_index": 0},
        )
        finish, _ = tools.call(
            "finish_session",
            {
                "candidate_id": candidate,
                "analysis": "Fixture, no physical success",
                "skill_report": empty_report(identity["skill_library"]),
            },
        )
        assert finish["comparison"]["task_success"] == 0

    library_dir = tmp_path / "library"
    groups = pipeline.partitions()
    identity = {
        "schema": "test-fixture",
        "dev_seeds": groups["development"],
        "unseen_seeds": groups["validation"],
        "heldout_seeds": groups["evaluation"],
        "heldout_count": 3,
        "limits": LIMITS,
        "runtime": RUNTIME,
        "provider": {"type": "fixture"},
        "max_programs": 2,
        "max_calls": 32,
        "agent_timeout_s": 60,
        "skill_library": skills.snapshot(library_dir),
        "protocol_sha256": c.canonical_sha256(protocol()),
    }
    root = tmp_path / "pipeline"
    auditor = lambda root, spec: {
        "verdict": "PASS",
        "reason": "Synthetic fixture reviewer; not a real policy audit",
    }
    result = pipeline.run(
        root,
        identity,
        {},
        library_dir=library_dir,
        worker=worker,
        auditor=auditor,
        evaluator=evaluator,
    )
    assert result["status"] == "done" and not result["full_harvest_solved"]
    assert [r["status"] for r in result["history"]] == ["pending", "stage1-done", "done"]
    assert len(executed) == 8
    repeated = pipeline.run(
        root,
        identity,
        {},
        library_dir=library_dir,
        worker=worker,
        auditor=auditor,
        evaluator=evaluator,
    )
    assert repeated == result and len(executed) == 8
    manifest = next(root.glob("so101/*/task_0/validation/runs/*/manifest.json"))
    assert set(c.read_json(manifest)["results"]) == {"3001", "3002", "3003"}
