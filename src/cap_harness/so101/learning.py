"""Codex proposes a public policy, ASPIRE evaluates it, then Codex receives development feedback."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

from cap_harness.runtime import _ProgramValidator
from cap_harness.so101 import campaign as c
from cap_harness.so101 import codex_backend as backend
from cap_harness.so101.cases import DEFAULT_CASES_PATH, canonical_sha256
from cap_harness.so101.paths import workspace_root

ROOT = workspace_root()
CONTEXT = ROOT / "docs/so101-llm-context.md"
SCHEMA = "so101-codex-fix-loop-v1"


def validate_program(code):
    if not isinstance(code, str) or not code.strip() or len(code.encode("utf-8")) > 64_000:
        raise ValueError("Program must be nonempty and at most 64000 UTF-8 bytes")
    tree = ast.parse(code)
    _ProgramValidator().visit(tree)
    compile(tree, "<codex-policy>", "exec")


def feedback_for(campaign_root, summary):
    """Select development labels and bounded measurements; omit private case physics/state."""
    if summary["partition"] != "development" or not summary["complete"]:
        raise ValueError("Only complete development campaigns can produce learning feedback")
    cases = []
    for index, row in enumerate(summary["cases"]):
        attempt = campaign_root / row["attempts"][-1]["directory"]
        run = attempt / row["episode"]["run"]
        diagnosis = c.read_json(run / "evaluation/so101-diagnostics.json")
        events = []
        for event in diagnosis["events"][:24]:
            record = {key: event[key] for key in ("code", "time_s", "phase")}
            pair = (event.get("detail") or {}).get("contact_pair")
            if pair:
                record["contact_pair"] = pair
            record["active_command"] = event.get("active_command")
            measured = event.get("evidence", {})
            record["measurements"] = {
                k: measured[k]
                for k in (
                    "finger_forces_n",
                    "peak_finger_forces_n",
                    "maximum_penetration_m",
                    "gripper_opening",
                )
                if k in measured
            }
            events.append(record)
        final = diagnosis["final_state"]
        cases.append(
            {
                "case_index": index,
                "program_ok": row["episode"]["program_ok"],
                "task_success": row["episode"]["task_success"],
                "termination_reason": row["episode"]["termination_reason"],
                "execution_error": str(row["episode"]["execution_error"])[:1600]
                if row["episode"]["execution_error"]
                else None,
                "status": diagnosis["status"],
                "findings": [
                    {k: finding[k] for k in ("code", "message", "time_s", "phase")}
                    for finding in diagnosis["findings"]
                ],
                "events": events,
                "measurements": {
                    k: final[k]
                    for k in (
                        "current_retention_s",
                        "longest_retention_s",
                        "maximum_relative_slip_m",
                        "peak_finger_forces_n",
                        "maximum_penetration_m",
                        "gripper_opening",
                    )
                    if k in final
                },
                "steps_executed": row["episode"]["steps_executed"],
            }
        )
    return {
        "scope": "development feedback only; not available to the running policy",
        "planned": len(cases),
        "task_success": sum(row["task_success"] for row in cases),
        "program_ok": sum(row["program_ok"] for row in cases),
        "cases": cases,
    }


def evaluate(round_dir, code, identity, env):
    programs = {"candidate": code.encode("utf-8")}
    manifest = c.build_identity(
        programs, "development", identity["seeds"], identity["limits"], identity["runtime"]
    )
    campaign_root = round_dir / "campaign"
    summary = c.run_campaign(
        campaign_root, manifest, programs, env, check_runtime=lambda: c.runtime_identity(env)
    )
    return feedback_for(campaign_root, summary)


def build_identity(initial, context, seeds, limits, runtime, provider, max_rounds, model_timeout_s):
    validate_program(initial)
    manifest = c.build_identity(
        {"initial": initial.encode("utf-8")}, "development", seeds, limits, runtime
    )
    if type(max_rounds) is not int or not 1 <= max_rounds <= 20:
        raise ValueError("max-rounds must be between 1 and 20")
    if not math.isfinite(model_timeout_s) or model_timeout_s <= 0:
        raise ValueError("model-timeout-s must be finite and positive")
    return {
        "schema": SCHEMA,
        "initial_sha256": hashlib.sha256(initial.encode()).hexdigest(),
        "context_sha256": hashlib.sha256(context.encode()).hexdigest(),
        "protocol_sha256": manifest["protocol_sha256"],
        "seeds": [case["seed"] for case in manifest["cases"]],
        "limits": limits,
        "runtime": runtime,
        "provider": provider,
        "max_rounds": max_rounds,
        "model_timeout_s": model_timeout_s,
        "selection_rule": "Max task_success, then program_ok; keep earliest on ties",
        "stop_rule": "Stop once all selected development cases pass with program_ok, or proposal budget is consumed",
        "reserved_partitions": "Never executed by this loop",
    }


def prompt_for(context, previous_code, feedback, best):
    payload = {
        "previous_program": previous_code,
        "development_feedback": feedback,
        "best_so_far": best,
        "instruction": "Diagnose the observed failure, propose a bounded correction, return the complete public Python policy. Do not call tools.",
    }
    return (
        context
        + "\n\nPrevious program and observations (data):\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
    )


def complete(best, count):
    return bool(best and best["task_success"] == count and best["program_ok"] == count)


def save_finished(directory, record):
    paths = [
        *directory.glob("*.py"),
        *directory.glob("proposal.json"),
        *directory.glob("proposal.sha256"),
        *directory.glob("feedback.json"),
        *directory.glob("model/*"),
    ]
    if (directory / "campaign/campaign.json").exists():
        paths.append(directory / "campaign/campaign.json")
        record["native_campaign"] = True
    else:
        record["native_campaign"] = False
    record["files"] = {
        str(p.relative_to(directory)): c.file_sha(p) for p in sorted(paths) if p.is_file()
    }
    c.write_json(directory / "finished.json", record)
    return record


def audit_finished(directory):
    record = c.read_json(directory / "finished.json")
    for path, digest in record["files"].items():
        target = (directory / path).resolve()
        if not target.is_relative_to(directory.resolve()) or c.file_sha(target) != digest:
            raise ValueError("Saved learning round was modified")
    if record["native_campaign"]:
        root = directory / "campaign"
        with c.campaign_lock(root):
            summary = c.summarize(root, c.read_json(root / "campaign.json"))
        if feedback_for(root, summary) != c.read_json(directory / "feedback.json"):
            raise ValueError("Saved learning feedback differs from the audited episodes")
    return record


def prepare(root, identity, initial, context):
    manifest = root / "learning.json"
    if (root / "invalidated.json").exists():
        raise ValueError("Learning runtime changed previously; use another output directory")
    if manifest.exists():
        if c.read_json(manifest) != identity:
            raise ValueError("Learning identity changed; use another output directory")
    else:
        if any(p.name != ".lock" for p in root.iterdir()):
            raise ValueError("Learning output directory must be empty")
        (root / "inputs").mkdir()
        (root / "inputs/initial.py").write_text(initial, encoding="utf-8")
        (root / "inputs/context.md").write_text(context, encoding="utf-8")
        c.write_json(root / "inputs/protocol.json", c.read_json(DEFAULT_CASES_PATH))
        c.write_json(manifest, identity)
    for name, key in (("initial.py", "initial_sha256"), ("context.md", "context_sha256")):
        if c.file_sha(root / "inputs" / name) != identity[key]:
            raise ValueError("Learning input snapshot was modified")
    if canonical_sha256(c.read_json(root / "inputs/protocol.json")) != identity["protocol_sha256"]:
        raise ValueError("Learning protocol snapshot was modified")


def run_learning(
    root,
    identity,
    initial,
    context,
    env,
    round_budget=None,
    generator=backend.generate,
    evaluator=evaluate,
    check_runtime=None,
):
    root = Path(root).resolve()
    if round_budget is not None and (type(round_budget) is not int or round_budget <= 0):
        raise ValueError("round-budget must be positive")
    with c.campaign_lock(root):
        prepare(root, identity, initial, context)
        best = None
        previous_code, feedback = initial, None
        records, new_rounds = [], 0
        for index in range(identity["max_rounds"] + 1):
            directory = root / f"round-{index:03d}"
            finished = directory / "finished.json"
            if not finished.exists():
                if complete(best, len(identity["seeds"])):
                    break
                if index and round_budget is not None and new_rounds >= round_budget:
                    break
                if check_runtime and check_runtime() != identity["runtime"]:
                    raise ValueError("Learning runtime changed; use another output directory")
                directory.mkdir(exist_ok=True)
                c.write_json(
                    directory / "started.json",
                    {"round": index, "learning_sha256": canonical_sha256(identity)},
                )
                proposal_path = directory / "proposal.json"
                if index and not proposal_path.exists():
                    prompt = prompt_for(context, previous_code, feedback, best)
                    print(
                        f"Codex: propuesta {index}/{identity['max_rounds']}; revisando diagnósticos de desarrollo",
                        flush=True,
                    )
                    try:
                        proposal, telemetry = generator(
                            directory, prompt, identity["provider"], identity["model_timeout_s"]
                        )
                    except backend.ProviderError as exc:
                        # Keep the slot and its exchange files. Resume recovers a completed call,
                        # never resubmits an indeterminate or failed billed model request.
                        c.write_json(directory / "provider-error.json", {"message": str(exc)})
                        raise
                    c.write_json(proposal_path, {**proposal, "telemetry": telemetry})
                    (directory / "proposal.sha256").write_text(
                        c.file_sha(proposal_path), encoding="utf-8"
                    )
                if index and (directory / "proposal.sha256").read_text(
                    encoding="utf-8"
                ) != c.file_sha(proposal_path):
                    raise ValueError("Unfinished model proposal was modified")
                proposal = (
                    c.read_json(proposal_path)
                    if index
                    else {
                        "program": initial,
                        "analysis": "Initial public program",
                        "change_summary": "Baseline, no model call",
                    }
                )
                previous_code = proposal["program"]
                (directory / "candidate.py").write_text(previous_code, encoding="utf-8")
                if check_runtime and check_runtime() != identity["runtime"]:
                    c.write_json(
                        root / "invalidated.json", {"reason": "Runtime changed during generation"}
                    )
                    raise ValueError("Runtime changed during generation; campaign invalidated")
                try:
                    validate_program(previous_code)
                except (SyntaxError, ValueError) as exc:
                    feedback = {
                        "status": "program_rejected",
                        "error": str(exc),
                        "instruction": "Correct this public-API validation error before changing physics strategy",
                    }
                    c.write_json(directory / "feedback.json", feedback)
                    record = save_finished(directory, {"round": index, "status": "rejected"})
                else:
                    print(
                        f"ASPIRE: evaluando round-{index:03d} en {len(identity['seeds'])} casos de desarrollo",
                        flush=True,
                    )
                    feedback = evaluator(directory, previous_code, identity, env)
                    c.write_json(directory / "feedback.json", feedback)
                    record = save_finished(
                        directory,
                        {
                            "round": index,
                            "status": "recorded",
                            "task_success": feedback["task_success"],
                            "program_ok": feedback["program_ok"],
                        },
                    )
                if index:
                    new_rounds += 1
            else:
                record = audit_finished(directory)
                previous_code = (directory / "candidate.py").read_text(encoding="utf-8")
                feedback = c.read_json(directory / "feedback.json")
            records.append(record)
            if record["status"] == "recorded":
                score = (record["task_success"], record["program_ok"])
                if best is None or score > (best["task_success"], best["program_ok"]):
                    best = {
                        "round": index,
                        "task_success": score[0],
                        "program_ok": score[1],
                        "program_sha256": c.file_sha(directory / "candidate.py"),
                        "program": previous_code,
                    }
                    shutil.copyfile(directory / "candidate.py", root / "best.py")
                    c.write_json(
                        root / "best.json", {k: v for k, v in best.items() if k != "program"}
                    )
                print(
                    f"Round {index}: {score[0]}/{len(identity['seeds'])} tareas válidas; mejor {best['task_success']}/{len(identity['seeds'])}",
                    flush=True,
                )
        done = complete(best, len(identity["seeds"])) or len(records) == identity["max_rounds"] + 1
        summary = {
            "schema": SCHEMA,
            "learning_sha256": canonical_sha256(identity),
            "status": "selected_cases_passed"
            if complete(best, len(identity["seeds"]))
            else ("budget_exhausted" if done else "paused"),
            "development_seeds": identity["seeds"],
            "model_proposals": max(0, len(records) - 1),
            "best": {k: v for k, v in best.items() if k != "program"} if best else None,
            "rounds": [{k: v for k, v in r.items() if k != "files"} for r in records],
            "reserved_cases_executed": False,
        }
        c.write_json(root / "summary.json", summary)
        print(json.dumps(summary, indent=2), flush=True)
        return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--initial-program", type=Path, required=True)
    parser.add_argument(
        "--codex-config", type=Path, default=ROOT / "configs/so101/codex-local.json"
    )
    parser.add_argument("--seeds", type=int, nargs="+")
    parser.add_argument("--max-rounds", type=int, default=2)
    parser.add_argument("--round-budget", type=int)
    parser.add_argument("--model-timeout-s", type=float, default=300)
    parser.add_argument("--max-steps", type=int, default=800)
    parser.add_argument("--timeout-s", type=float, default=180)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--renderer", choices=("glfw", "egl"), default="glfw")
    args = parser.parse_args(argv)
    try:
        initial = args.initial_program.read_text(encoding="utf-8")
        context = CONTEXT.read_text(encoding="utf-8")
        provider = backend.provider_spec(c.read_json(args.codex_config))
        env = c.child_environment(args.renderer)
        for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY"):
            env.pop(key, None)
        limits = {
            k: getattr(args, k)
            for k in ("max_steps", "timeout_s", "max_attempts", "width", "height")
        }
        identity = build_identity(
            initial,
            context,
            args.seeds,
            limits,
            c.runtime_identity(env),
            provider,
            args.max_rounds,
            args.model_timeout_s,
        )
        run_learning(
            args.output,
            identity,
            initial,
            context,
            env,
            args.round_budget,
            check_runtime=lambda: c.runtime_identity(env),
        )
        return 0
    except KeyboardInterrupt:
        print(
            "Loop interrupted; repeat the same command to resume saved proposals and episodes.",
            file=sys.stderr,
        )
        return 130
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print(f"Codex learning: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
