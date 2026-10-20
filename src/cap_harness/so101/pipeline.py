"""SO-101 adapter for the ASPIRE development/unseen/evaluation/skill protocol.

The acting controller never sees reserved cases or the coordinator's files.
All physical episodes use the existing audited native campaign runner.
"""

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

from cap_harness.so101 import campaign as c
from cap_harness.so101 import debug_agent as agent
from cap_harness.so101 import debug_tools as d
from cap_harness.so101 import provenance, skills
from cap_harness.so101.handoff import export_handoff
from cap_harness.so101.harvest_protocol import SUITE, cases, protocol


def partitions():
    return {
        name: [row["seed"] for row in cases() if row["partition"] == name]
        for name in ("development", "validation", "evaluation")
    }


def state(task, status, **fields):
    path = task / "so101-pipeline.json"
    previous = c.read_json(path) if path.exists() else {"history": []}
    entry = {"status": status, **fields}
    history = previous["history"]
    if not history or history[-1] != entry:
        history.append(entry)
    record = {**entry, "history": history}
    c.write_json(path, record)
    return record


def immutable(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != content:
        raise ValueError("Frozen pipeline artifact changed: " + str(path))
    if not path.exists():
        path.write_bytes(content)


def initialize(root, identity):
    root.mkdir(parents=True, exist_ok=True)
    path = root / "campaign.json"
    if path.exists():
        if c.read_json(path) != identity:
            raise ValueError("Pipeline identity changed; use a new campaign")
    else:
        if any(p.name != ".lock" for p in root.iterdir()):
            raise ValueError("Pipeline output must be empty")
        c.write_json(path, identity)
        c.write_json(
            root / "tasks.json",
            [
                {
                    "benchmark": "so101",
                    "suite": SUITE,
                    "task_id": 0,
                    "task_name": "harvest, carry and deposit one strawberry",
                }
            ],
        )
        (root / "curriculum.md").write_text(
            "Single initial benchmark: full strawberry harvest with SO-101. The worker owns strategy. Start with the frozen applicable library; evaluate reserved cases only after source/provenance freeze.\n",
            encoding="utf-8",
        )
    return root / "so101" / SUITE / "task_0"


def reserved(task, partition, code, selection, identity, env, evaluator):
    manifest = c.build_identity(
        {"candidate": code},
        partition,
        None,
        identity["limits"],
        identity["runtime"],
        selection,
        suite=SUITE,
    )
    return evaluator(
        task / partition,
        manifest,
        {"candidate": code},
        env,
        selection=selection,
        check_runtime=lambda: d.runtime_identity(env, SUITE),
    )


def export_validation(task, summary, identity, code_sha):
    """Publish native audited results in the canonical progress reader's format."""
    results = {
        str(row["seed"]): {**row["episode"], "seed": row["seed"]}
        for row in summary["cases"]
        if row["episode"]
    }
    manifest = {
        "schema_version": 1,
        "run_id": summary["campaign_sha256"][:16],
        "identity": {
            "benchmark": "so101",
            "suite": SUITE,
            "task_id": 0,
            "code_sha256": code_sha,
            "seeds": identity["heldout_seeds"],
            "protocol_sha256": identity["protocol_sha256"],
        },
        "status": "completed" if summary["complete"] else "incomplete",
        "results": results,
        "trials": len(results),
        "passes": sum(bool(r["task_success"]) for r in results.values()),
        "native_campaign_sha256": summary["campaign_sha256"],
    }
    c.write_json(task / "validation/runs" / manifest["run_id"] / "manifest.json", manifest)


def verify_skills(root, identity, report, env, library_dir, worker, auditor):
    proposals = report["proposed_new"] + report["proposed_edits"]
    if any(proposal.get("verification_contract") for proposal in proposals):
        from cap_harness.so101.skill_verification import verify

        return verify(root, identity, report, env, library_dir, worker, auditor)
    directory = root / "verification" / ("so101__" + SUITE + "__task_0")
    path = directory / "verification_report.json"
    if path.exists():
        result = c.read_json(path)
        if result.get("proposals_sha256") != c.canonical_sha256(proposals):
            raise ValueError("Skill proposals changed after verification")
        if proposals and result["verdict"] == "verified":
            skills.promote(library_dir, identity["skill_library"], proposals, result)
        return result
    if not proposals:
        result = {
            "verdict": "none",
            "status": "no_proposals",
            "proposals_sha256": c.canonical_sha256([]),
            "reason": "Acting controller proposed no skill; no synthetic skill created",
        }
    else:
        library = skills.proposal_snapshot(identity["skill_library"], proposals)
        seeds = identity["dev_seeds"][:2]
        worker_identity = d.build_identity(
            seeds, identity["limits"], identity["runtime"], 2, 40, suite=SUITE
        )
        worker_identity.update(
            provider=identity["provider"],
            skill_library=library,
            enforce_debug_sequence=True,
            verifier=True,
            agent_timeout_s=identity["agent_timeout_s"],
        )
        workspace = d.initialize(directory / "worker", worker_identity)
        worker(workspace, identity["provider"], worker_identity, identity["agent_timeout_s"])
        review = auditor(workspace, identity["provider"])
        finish = c.read_json(workspace / "finish.json")
        passed = (
            review["verdict"] == "PASS"
            and finish["comparison"]["task_success"] == len(seeds)
            and finish["comparison"]["program_ok"] == len(seeds)
        )
        result = {
            "verdict": "verified" if passed else "refuted",
            "status": "verified" if passed else "refuted",
            "provenance_audit": review["verdict"],
            "independent": True,
            "no_proposer_code": True,
            "library_sha256": library["sha256"],
            "comparison": finish["comparison"],
            "proposals_sha256": c.canonical_sha256(proposals),
            "worker_session_sha256": c.file_sha(workspace / "session.json"),
        }
        if passed:
            skills.promote(library_dir, identity["skill_library"], proposals, result)
    c.write_json(path, result)
    return result


def run(
    root,
    identity,
    env,
    *,
    library_dir,
    worker=agent.launch,
    auditor=provenance.audit,
    evaluator=c.run_campaign,
):
    root = Path(root).resolve()
    with c.campaign_lock(root):
        task = initialize(root, identity)
        task.mkdir(parents=True, exist_ok=True)
        worker_identity = d.build_identity(
            identity["dev_seeds"],
            identity["limits"],
            identity["runtime"],
            identity["max_programs"],
            identity["max_calls"],
            suite=SUITE,
        )
        worker_identity.update(
            provider=identity["provider"],
            skill_library=identity["skill_library"],
            enforce_debug_sequence=True,
            max_per_failure_mode=3,
            tie_breaker="ast_size",
            agent_timeout_s=identity["agent_timeout_s"],
        )
        if "skill_references" in identity:
            worker_identity["skill_references"] = identity["skill_references"]
        workspace = d.initialize(task / "debug/worker", worker_identity)
        if not (workspace / "finish.json").exists():
            state(task, "pending", active="development")
        # launch() and every native campaign audit their journals on resume.
        worker(workspace, identity["provider"], worker_identity, identity["agent_timeout_s"])
        handoff = export_handoff(workspace)
        review = auditor(workspace, identity["provider"])
        if review["verdict"] != "PASS":
            return state(task, "quarantined", active="provenance", reason=review["reason"])
        finish = c.read_json(workspace / "finish.json")
        candidate = workspace / "candidates" / finish["candidate_id"]
        selection_path = c.freeze_selection(candidate / "campaign", "candidate")
        selection = c.read_json(selection_path)
        code = (candidate / "program.py").read_bytes()
        immutable(task / "fix_code.py", code)
        immutable(task / "skill_report.json", (workspace / "skill-report.json").read_bytes())
        immutable(task / "findings.md", (workspace / "worker-handoff/findings.md").read_bytes())
        immutable(task / "selection.json", selection_path.read_bytes())
        unseen = reserved(task, "validation", code, selection, identity, env, evaluator)
        if not unseen["complete"]:
            return state(task, "infrastructure_incomplete", active="unseen-check")
        stage = {
            "active": "heldout",
            "provenance_audit": "PASS",
            "worker_handoff_sha256": c.canonical_sha256(handoff),
            "selected_program_sha256": c.file_sha(task / "fix_code.py"),
            "development": finish["comparison"],
            "unseen": unseen["comparison"]["candidate"],
        }
        if not (task / "evaluation/summary.json").exists():
            state(task, "stage1-done", **stage)
        heldout = reserved(task, "evaluation", code, selection, identity, env, evaluator)
        export_validation(task, heldout, identity, selection["program_sha256"])
        if not heldout["complete"]:
            return state(task, "stage1-done", **stage)
        skill_report = c.read_json(task / "skill_report.json")
        verification = verify_skills(
            root, identity, skill_report, env, library_dir, worker, auditor
        )
        return state(
            task,
            "done",
            **{**stage, "active": "completed"},
            heldout=heldout["comparison"]["candidate"],
            skill_verification=verification,
            full_harvest_solved=heldout["comparison"]["candidate"]["task_success"]
            == len(identity["heldout_seeds"]),
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--controller-config", type=Path, default=c.ROOT / "configs/so101/codex-local.json"
    )
    parser.add_argument("--skills-dir", type=Path, default=c.ROOT / "configs/so101/skills")
    parser.add_argument("--max-programs", type=int, default=8)
    parser.add_argument("--max-calls", type=int, default=96)
    parser.add_argument("--max-steps", type=int, default=1200)
    parser.add_argument("--timeout-s", type=float, default=240)
    parser.add_argument("--agent-timeout-s", type=float, default=7200)
    parser.add_argument("--references-manifest", type=Path, help="Freeze external skill references")
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.agent_timeout_s) or args.agent_timeout_s <= 0:
            raise ValueError("agent-timeout-s must be finite and positive")
        env = c.child_environment("glfw")
        groups = partitions()
        identity = {
            "schema": "so101-aspire-pipeline-v2",
            "protocol_sha256": c.canonical_sha256(protocol()),
            "runtime": d.runtime_identity(env, SUITE),
            "provider": agent.controller_spec(c.read_json(args.controller_config)),
            "limits": {
                "max_steps": args.max_steps,
                "timeout_s": args.timeout_s,
                "max_attempts": 1,
                "width": args.width,
                "height": args.height,
            },
            "dev_seeds": groups["development"],
            "unseen_seeds": groups["validation"],
            "heldout_seeds": groups["evaluation"],
            "heldout_count": len(groups["evaluation"]),
            "max_programs": args.max_programs,
            "max_calls": args.max_calls,
            "agent_timeout_s": args.agent_timeout_s,
            "skill_library_directory": str(args.skills_dir.resolve()),
        }
        previous = args.output / "campaign.json"
        identity["skill_library"] = (
            c.read_json(previous)["skill_library"]
            if previous.exists()
            else skills.snapshot(args.skills_dir)
        )
        if args.references_manifest is not None:
            from cap_harness.so101.skill_references import snapshot as reference_snapshot

            identity["skill_references"] = reference_snapshot(args.references_manifest)
        result = run(args.output, identity, env, library_dir=args.skills_dir)
        subprocess.run(
            [
                sys.executable,
                str(c.ROOT / ".claude/skills/iterative-debugging/scripts/gen_progress.py"),
                "--run-root",
                str(args.output.resolve()),
            ],
            check=True,
        )
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "done" else 2
    except (ValueError, OSError, KeyError) as exc:
        print("ASPIRE SO101 pipeline: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
