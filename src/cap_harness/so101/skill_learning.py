"""Bounded learning and independent reuse of one registered partial skill."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from cap_harness.so101 import campaign as c
from cap_harness.so101 import debug_agent as agent
from cap_harness.so101 import debug_tools as d
from cap_harness.so101 import provenance, skill_references, skills, strategy_search
from cap_harness.so101.harvest_protocol import SUITE, cases
from cap_harness.so101.pipeline import verify_skills
from cap_harness.so101.skill_contracts import CONTRACTS, contract


def load_operator_context(path):
    if path is None:
        return None
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("Operator context must not be empty")
    return {"text": text, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract", choices=list(CONTRACTS), required=True)
    parser.add_argument(
        "--controller-config", type=Path, default=c.ROOT / "configs/so101/codex-local.json"
    )
    parser.add_argument("--skills-dir", type=Path, default=c.ROOT / "configs/so101/skills")
    parser.add_argument("--context-file", type=Path, help="Freeze additional operator task context")
    parser.add_argument("--references-manifest", type=Path, help="Freeze external skill references")
    parser.add_argument("--max-programs", type=int, default=3)
    parser.add_argument("--search-mode", choices=("fix-loop", "diverse"), default="fix-loop")
    parser.add_argument("--max-calls", type=int, default=40)
    parser.add_argument("--agent-timeout-s", type=float, default=1800)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    args = parser.parse_args(argv)
    try:
        search = strategy_search.configuration(args.search_mode, args.max_programs)
        if not math.isfinite(args.agent_timeout_s) or args.agent_timeout_s <= 0:
            raise ValueError("agent-timeout-s must be finite and positive")
        if not 64 <= args.width <= 2048 or not 64 <= args.height <= 2048:
            raise ValueError("Camera width/height must each be between 64 and 2048 pixels")
        env = c.child_environment("glfw")
        spec = agent.controller_spec(c.read_json(args.controller_config))
        previous = args.output / "learning.json"
        library = (
            c.read_json(previous)["skill_library"]
            if previous.exists()
            else skills.snapshot(args.skills_dir)
        )
        identity = {
            "schema": "so101-partial-skill-learning-v1",
            "contract": contract(args.contract),
            "runtime": d.runtime_identity(env, SUITE),
            "provider": spec,
            "dev_seeds": [row["seed"] for row in cases() if row["partition"] == "development"][:2],
            "limits": {
                "max_steps": 1200,
                "timeout_s": 240.0,
                "max_attempts": 1,
                "width": args.width,
                "height": args.height,
            },
            "skill_library": library,
            "max_programs": args.max_programs,
            "max_calls": args.max_calls,
            "agent_timeout_s": args.agent_timeout_s,
            "library_directory": str(args.skills_dir.resolve()),
        }
        if args.references_manifest is not None:
            identity["skill_references"] = skill_references.snapshot(args.references_manifest)
        context = load_operator_context(args.context_file)
        if context is not None:
            identity["operator_context"] = context
        if search is not None:
            identity["search_protocol"] = search
        args.output.mkdir(parents=True, exist_ok=True)
        with c.campaign_lock(args.output):
            if previous.exists() and c.read_json(previous) != identity:
                raise ValueError("Learning identity changed; use a new output directory")
            c.write_json(previous, identity)
            worker_identity = d.build_identity(
                identity["dev_seeds"],
                identity["limits"],
                identity["runtime"],
                args.max_programs,
                args.max_calls,
                suite=SUITE,
            )
            worker_identity.update(
                provider=spec,
                skill_library=library,
                verification_contract=identity["contract"],
                enforce_debug_sequence=True,
                tie_breaker="ast_size",
                agent_timeout_s=args.agent_timeout_s,
            )
            if "skill_references" in identity:
                worker_identity["skill_references"] = identity["skill_references"]
            if context is not None:
                worker_identity["operator_context"] = context
            if search is not None:
                worker_identity.update(search_protocol=search, tie_breaker="evidence_choice")
            workspace = d.initialize(args.output / "learner", worker_identity)
            agent.launch(workspace, spec, worker_identity, args.agent_timeout_s)
            review = provenance.audit(workspace, spec)
            if review["verdict"] != "PASS":
                raise ValueError("Learner provenance was quarantined: " + review["reason"])
            report = c.read_json(workspace / "skill-report.json")
            proposals = report["proposed_new"] + report["proposed_edits"]
            if any(
                proposal.get("verification_contract") != args.contract for proposal in proposals
            ):
                raise ValueError("Learning proposals must name the assigned registered contract")
            result = verify_skills(
                args.output, identity, report, env, args.skills_dir, agent.launch, provenance.audit
            )
            c.write_json(args.output / "result.json", result)
            print(json.dumps(result, indent=2))
            return 0 if result["verdict"] == "verified" else 2
    except (ValueError, OSError, KeyError) as exc:
        print("Partial skill learning: " + str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
