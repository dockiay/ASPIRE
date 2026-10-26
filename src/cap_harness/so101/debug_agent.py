"""Launch a Codex agent with only the SO-101 iterative-debugging MCP tools."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from cap_harness.so101 import campaign as c
from cap_harness.so101 import codex_backend as backend
from cap_harness.so101.debug_tools import (
    ROOT,
    TOOLS,
    DebugTools,
    build_identity,
    initialize,
    runtime_identity,
)
from cap_harness.so101.harvest_protocol import SUITE as HARVEST_SUITE
from cap_harness.so101.skills import snapshot as skill_snapshot

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "candidate_id": {"type": "string"},
        "analysis": {"type": "string"},
        "task_completed": {"type": "boolean"},
    },
    "required": ["candidate_id", "analysis", "task_completed"],
    "additionalProperties": False,
}
SMOKE = """
This run is an API/MCP integration smoke test, not a harvesting attempt.
1. Call describe_task and explore_scene, and examine both actual images.
2. Submit a tiny initial program that reads get_robot_state() then calls
   get_finger_contacts() as an unqualified function. This deliberate API-name
   fault must be observed through the execution report, without moving the arm.
3. Call inspect_results and diagnose the actual reported error. Submit a corrected
   program using so101.get_finger_contacts(), holding the measured initial joints
   and measured gripper opening for at most 8 control ticks. Use the public
   RobotAction/ArmCommand interface; no absolute joint or object targets.
4. Inspect that program's results and use view_frame for case_index=0,
   camera=agentview, frame_index=0. Call finish_session with the best candidate.
Report task_completed=false: an API repair and tool test does not harvest a fruit.
Both candidate programs must be your own full Python output via execute_program.
Do not return until you have called finish_session successfully.
"""
APPROACH = """
The current operator stage is ONLY visual localization and open approach.
Do not grasp, close the gripper, detach, twist, carry or deposit the fruit.
Describe the task and explore both images, then generate your own full program
using so101.localize_ripe_fruit() and so101.plan_open_approach() at runtime.
Use 0.065 m standoff (an engineering clearance, not an observed coordinate).
Execute the returned waypoints at gripper_position=1.0 with two step ticks per
waypoint, settle with move_to_joints(tolerance=0.004,max_steps=80), then hold the
final target open for eight ticks. Check every action result. Do not copy any
joint or fruit coordinates from observations, logs or old policies into code.
Store the localization, plan and final measured TCP/opening in result for audit.
Inspect the actual program results, then view the selected candidate's LAST
recorded frame: view_frame first reports frame_count, so use frame_count-1.
View both agentview and sideview at the end to assess clearance and uncertainty.
Correct only execution/localization/approach problems within budget. Expected
full-harvest task_success is false at this stage; do not attempt later stages to
turn it true. Finish with the best approach candidate and task_completed=false.
This is a real approach attempt, not the deliberate-API-error smoke assignment.
"""


def mcp_configuration(root, spec, identity):
    args = [sys.executable, "-m", "cap_harness.so101.debug_mcp", "--workspace", str(root)]
    if spec["windows"]:
        command = "C:\\Windows\\System32\\wsl.exe"
        distro = os.environ["WSL_DISTRO_NAME"]
        args = ["-d", distro, "--", *args]
    else:
        command, args = args[0], args[1:]
    return {
        "command": command,
        "args": args,
        "required": True,
        "startup_timeout_sec": 45,
        "tool_timeout_sec": len(identity["seeds"])
        * identity["limits"]["max_attempts"]
        * identity["limits"]["timeout_s"]
        + 45,
        "enabled_tools": list(TOOLS),
    }


def audit_agent(root, directory):
    result = backend.read_json(directory / "worker-result.json")
    if result["status"] != "ok" or result["request_sha256"] != backend.digest(
        directory / "request.json"
    ):
        raise ValueError("Agent call did not complete successfully with the recorded request")
    if result["response_sha256"] != backend.digest(directory / "response.json"):
        raise ValueError("Agent response was modified")
    response = backend.read_json(directory / "response.json")
    if set(response) != set(RESPONSE_SCHEMA["required"]):
        raise ValueError("Unexpected agent response fields")
    tool_calls, usage = [], None
    for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        item = event.get("item", {})
        if item.get("type") in ("command_execution", "file_change", "web_search", "tool_call"):
            raise ValueError("Agent used an unapproved tool")
        if item.get("type") in ("mcp_tool_call", "function_tool_call"):
            if item.get("server") != "so101" or item.get("tool") not in TOOLS:
                raise ValueError("Agent used an unapproved MCP capability")
            if event["type"] == "item.completed":
                tool_calls.append(item["tool"])
        if event.get("type") == "turn.completed":
            usage = event.get("usage")
    finish = c.read_json(root / "finish.json")
    service = DebugTools(root)
    selected, _ = service.inspect_results(finish["candidate_id"], mark=False)
    if selected["comparison"] != finish["comparison"]:
        raise ValueError("Final conclusion differs from audited episodes")
    for path in (root / "calls").glob("*.json"):
        service.audit_images(c.read_json(path))
    if response["candidate_id"] != finish["candidate_id"]:
        raise ValueError("Agent final candidate differs from the tool-verified candidate")
    count = len(c.read_json(root / "session.json")["seeds"])
    comparison = finish["comparison"]
    expected = comparison["task_success"] == count and comparison["program_ok"] == count
    if type(response["task_completed"]) is not bool or response["task_completed"] != expected:
        raise ValueError("Agent completion claim differs from the physical evaluation")
    required = set(TOOLS) - (
        {"view_frame"} if finish["status"] == "infrastructure_blocked" else set()
    )
    if not required.issubset(tool_calls):
        raise ValueError("Agent did not demonstrate the entire controlled tool workflow")
    report = {
        "schema": "so101-agent-verification-v1",
        "worker": result,
        "tool_transport": "responses-functions" if result.get("provider") == "api" else "mcp-stdio",
        "usage": usage,
        "completed_tool_calls": tool_calls,
        "finish": finish,
        "model_response": response,
        "provenance_audit": "PENDING",
        "reserved_cases_executed": False,
        "canonical_campaign_complete": False,
        "suite": service.identity["suite"],
        "protocol_sha256": service.identity["protocol_sha256"],
    }
    c.write_json(root / "agent-verification.json", report)
    return report


def agent_prompt(root, identity, smoke=False, approach_only=False):
    prompt = (root / "inputs/agent-prompt.md").read_text(encoding="utf-8")
    prompt += "\n\n" + (root / "inputs/SKILL.md").read_text(encoding="utf-8")
    prompt += (
        "\n\nAssigned task: "
        + identity["suite"]
        + ". Tool describe_task is authoritative for task language, cases and success conditions."
    )
    if smoke:
        prompt += "\n\nExplicit operator integration-test assignment:\n" + SMOKE
    elif approach_only:
        prompt += "\n\nExplicit operator stage assignment:\n" + APPROACH
    else:
        prompt += "\nUse only your configured SO101 MCP tools. Start by describe_task and explore_scene. Generate from public observations, inspect evidence, revise within budget, and close with the best experimental candidate. No external baseline policy is supplied beyond the permitted frozen skill library."
    if "skill_library" in identity:
        prompt += (
            "\n\nPermitted frozen skill library (reusable code patterns and sensor-relative procedures may be applied; derive every object target from current public observations, never cached task coordinates/waypoints or private state):\n"
            + json.dumps(identity["skill_library"])
        )
        prompt += "\nfinish_session requires the canonical ASPIRE skill_report: skill_library_sha; consulted (skill/verdict/evidence, verdict useful/misleading/wrong/not-applicable); proposed_new (skill filename.md/title/trigger/code/evidence/evidence_candidate_ids); proposed_edits (skill/change/why/content/evidence_candidate_ids). content is the full proposed edited markdown. Define or explain every snippet input. Use empty arrays when no skill was useful or justified. Propose only patterns supported by inspected results; do not claim verified learning from failed trials."
    if identity.get("skill_references") is not None:
        from cap_harness.so101.skill_references import prompt as references_prompt

        prompt += references_prompt(identity["skill_references"])
    if identity.get("operator_context") is not None:
        context = identity["operator_context"]
        if (
            not isinstance(context, dict)
            or not isinstance(context.get("text"), str)
            or hashlib.sha256(context["text"].encode("utf-8")).hexdigest() != context.get("sha256")
        ):
            raise ValueError("Frozen operator context hash mismatch")
        prompt += (
            "\n\nFrozen operator task context (task observations, never physical success evidence):\n"
            + context["text"]
        )
    if identity.get("verifier"):
        prompt += "\nIndependent skill verifier: you have no proposer source. Re-solve from this library and public observations, within two candidates. Report evidence honestly; the coordinator alone decides promotion."
    if identity.get("verification_contract"):
        prompt += (
            "\nExplicit operator skill-learning/verification assignment overrides the full-harvest stopping rule: "
            + json.dumps(identity["verification_contract"])
            + ". Stop when this registered criterion is achieved or your budget is exhausted. "
            "Selection maximizes skill_success, then program_ok, then simplicity/order. "
            "task_completed in your final response must STILL describe full physical harvest, not the partial skill. "
            "Use public observations and return the contract's report format. Never use hidden target coordinates."
        )
    if identity.get("verification_skill"):
        prompt += (
            "\nYou must actually apply the supplied skill "
            + identity["verification_skill"]
            + " and grade it in skill_report.consulted with evidence from your selected candidate. "
            "You may adapt its inputs from observations, but do not replace it with an unrelated method. "
            "Do not propose further skills in this independent verification session."
        )
    elif identity.get("verification_contract"):
        prompt += (
            "\nWhen the skill criterion passes all assigned cases, propose the demonstrated reusable pattern "
            "in skill_report.proposed_new, with verification_contract set to the assigned contract id. "
            "Provide a self-contained snippet with all inputs defined or explained. "
            "Propose only evidence-supported skills; full-harvest failure does not invalidate successful partial evidence."
        )
    if identity.get("search_protocol"):
        from cap_harness.so101.strategy_search import instructions

        prompt += "\n\n" + instructions(identity["search_protocol"])
    return prompt


def launch(root, spec, identity, timeout_s, smoke=False, approach_only=False):
    root = Path(root).resolve()
    prompt = agent_prompt(root, identity, smoke, approach_only)
    if spec.get("type") == "api":
        from cap_harness.so101.api_backend import run

        run(root, spec, prompt, RESPONSE_SCHEMA, timeout_s=timeout_s)
        return audit_agent(root, root / "model")
    owner = root.name + "-" + hashlib.sha256(str(root).encode()).hexdigest()[:12]
    directory = Path(spec["exchange_dir"]) / owner / "agent"
    directory.mkdir(parents=True, exist_ok=True)
    request = {
        "codex": backend.host_path(spec["codex"], spec["windows"]),
        "directory": backend.host_path(directory, spec["windows"]),
        "prompt": prompt,
        "model": spec["model"],
        "timeout_s": timeout_s,
        "mcp": mcp_configuration(root, spec, identity),
    }
    if spec.get("history_compaction") is not None:
        request["history_compaction"] = spec["history_compaction"]
    request_path = directory / "request.json"
    if request_path.exists() and backend.read_json(request_path) != request:
        raise ValueError("Agent request changed; start another session")
    if not request_path.exists():
        backend.write_json(request_path, request)
        backend.write_json(directory / "schema.json", RESPONSE_SCHEMA)
    terminal = directory / "worker-result.json"
    if not terminal.exists():
        if (directory / "launch-started.json").exists():
            raise ValueError(
                "Agent request is pending; wait for its terminal record before resuming"
            )
        backend.write_json(
            directory / "launch-started.json", {"request_sha256": backend.digest(request_path)}
        )
        with (directory / "launcher.log").open("wb") as log:
            process = subprocess.Popen(
                [
                    spec["host_python"],
                    backend.host_path(backend.__file__, spec["windows"]),
                    "--worker",
                    backend.host_path(request_path, spec["windows"]),
                ],
                stdout=log,
                stderr=log,
            )
            try:
                process.wait(timeout=timeout_s + 30)
            except (KeyboardInterrupt, subprocess.TimeoutExpired):
                (directory / "cancel").touch()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise
    if not terminal.exists():
        raise ValueError("Native agent worker did not return a terminal record")
    import shutil

    target = root / "model"
    target.mkdir(exist_ok=True)
    for path in directory.iterdir():
        if path.is_file():
            shutil.copyfile(path, target / path.name)
    return audit_agent(root, target)


def controller_spec(config, kind=None):
    kind = kind or config.get("type", "codex")
    if kind == "api":
        from cap_harness.so101.api_backend import provider_spec

        return provider_spec({**config, "type": "api"})
    if kind != "codex" or config.get("type", "codex") != "codex":
        raise ValueError("Controller kind and configuration disagree")
    return {
        **backend.provider_spec({k: v for k, v in config.items() if k != "type"}),
        "type": "codex",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--suite",
        choices=[HARVEST_SUITE, c.SUITE],
        default=HARVEST_SUITE,
        help="ASPIRE scene/task; defaults to the plant plus container episode",
    )
    parser.add_argument(
        "--controller-config",
        "--codex-config",
        dest="codex_config",
        type=Path,
        default=ROOT / "configs/so101/codex-local.json",
    )
    parser.add_argument("--controller", choices=["codex", "api"])
    parser.add_argument("--skills-dir", type=Path, default=ROOT / "configs/so101/skills")
    parser.add_argument("--seeds", type=int, nargs="+")
    parser.add_argument("--max-programs", type=int, default=8)
    parser.add_argument("--max-calls", type=int, default=96)
    parser.add_argument("--max-steps", type=int, default=800)
    parser.add_argument("--timeout-s", type=float, default=180)
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--agent-timeout-s", type=float, default=7200)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--smoke", action="store_true")
    mode.add_argument(
        "--approach-only",
        action="store_true",
        help="Localize and approach open; do not attempt later harvest stages",
    )
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.agent_timeout_s) or args.agent_timeout_s <= 0:
            raise ValueError("agent-timeout-s must be finite and positive")
        env = c.child_environment("glfw")
        spec = controller_spec(c.read_json(args.codex_config), args.controller)
        limits = {
            k: getattr(args, k)
            for k in ("max_steps", "timeout_s", "max_attempts", "width", "height")
        }
        identity = build_identity(
            args.seeds,
            limits,
            runtime_identity(env, args.suite),
            args.max_programs,
            args.max_calls,
            suite=args.suite,
        )
        if args.approach_only and args.suite != HARVEST_SUITE:
            raise ValueError(
                "The visual approach assignment currently supports only the full plant scene"
            )
        identity.update(
            provider=spec,
            smoke_test=args.smoke,
            approach_only=args.approach_only,
            agent_timeout_s=args.agent_timeout_s,
            skill_library=skill_snapshot(args.skills_dir),
            enforce_debug_sequence=True,
            tie_breaker="ast_size",
        )
        root = initialize(args.output, identity)
        print(
            f"ASPIRE agente ({spec.get('type', 'codex')}): {args.suite}; herramientas SO101 habilitadas; desarrollo; procedencia PENDING",
            flush=True,
        )
        with c.campaign_lock(root / "launcher"):
            report = launch(
                root, spec, identity, args.agent_timeout_s, args.smoke, args.approach_only
            )
            if not args.smoke and not args.approach_only:
                from cap_harness.so101.handoff import export_handoff

                report["worker_handoff"] = export_handoff(root)
        print(
            json.dumps(
                {
                    "status": "agent_workflow_verified",
                    "tool_calls": report["completed_tool_calls"],
                    "finish": report["finish"],
                    "worker_handoff": report.get("worker_handoff"),
                },
                indent=2,
            ),
            flush=True,
        )
        return 0
    except KeyboardInterrupt:
        print("Agent interrupted; recorded requests and episodes are preserved.", file=sys.stderr)
        return 130
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print(f"SO101 agent: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
