"""Verify and promote each explicitly scoped skill independently of full harvest."""

from cap_harness.so101 import campaign as c
from cap_harness.so101 import debug_tools as d
from cap_harness.so101 import skills
from cap_harness.so101.skill_contracts import proposal_contract


def verify(root, identity, report, env, library_dir, worker, auditor):
    proposals = report["proposed_new"] + report["proposed_edits"]
    directory = root / "verification/so101__so101_fruitgym_harvest__task_0"
    aggregate_path = directory / "verification_report.json"
    proposal_sha = c.canonical_sha256(proposals)
    if aggregate_path.exists():
        aggregate = c.read_json(aggregate_path)
        if aggregate.get("proposals_sha256") != proposal_sha:
            raise ValueError("Skill proposals changed after verification")
        for row in aggregate["jobs"]:
            if c.file_sha(directory / row["report"]) != row["sha256"]:
                raise ValueError("Independent skill verification record changed")
            stored = c.read_json(directory / row["report"])
            workspace = (directory / row["report"]).parent / "worker"
            if (
                c.file_sha(workspace / "session.json") != stored["worker_session_sha256"]
                or c.file_sha(workspace / "finish.json") != stored["finish_sha256"]
            ):
                raise ValueError("Independent worker identity or finish changed")
            audited, _ = d.DebugTools(workspace).inspect_results(
                c.read_json(workspace / "finish.json")["candidate_id"], mark=False
            )
            if audited["comparison"] != stored["comparison"]:
                raise ValueError("Independent verification outcomes changed")
        skills.snapshot(library_dir)
        return aggregate
    working = identity["skill_library"]
    jobs, promoted = [], []
    for proposal in proposals:
        spec = proposal_contract(proposal)
        job = (
            directory
            / "scoped"
            / (proposal["skill"][:-3] + "-" + c.canonical_sha256(proposal)[:12])
        )
        path = job / "verification.json"
        library = skills.proposal_snapshot(working, [proposal])
        inputs = {"previous": working, "proposed": library, "proposal": proposal, "contract": spec}
        input_path = job / "inputs.json"
        if input_path.exists() and c.read_json(input_path) != inputs:
            raise ValueError("Scoped verification inputs changed")
        c.write_json(input_path, inputs)
        seeds = identity["dev_seeds"][:2]
        if len(seeds) != 2:
            raise ValueError("Scoped verification requires two registered development cases")
        worker_identity = d.build_identity(
            seeds, identity["limits"], identity["runtime"], 2, 40, suite="so101_fruitgym_harvest"
        )
        worker_identity.update(
            provider=identity["provider"],
            skill_library=library,
            enforce_debug_sequence=True,
            verifier=True,
            verification_skill=proposal["skill"],
            verification_contract=spec,
            tie_breaker="ast_size",
            agent_timeout_s=identity["agent_timeout_s"],
        )
        workspace = d.initialize(job / "worker", worker_identity)
        if path.exists():
            result = c.read_json(path)
            if result["inputs_sha256"] != c.file_sha(input_path):
                raise ValueError("Scoped verification input hash changed")
        else:
            if skills.snapshot(library_dir) != working:
                raise ValueError("Skill library changed while verification was active")
            worker(workspace, identity["provider"], worker_identity, identity["agent_timeout_s"])
            review = auditor(workspace, identity["provider"])
            finish = c.read_json(workspace / "finish.json")
            consulted = c.read_json(workspace / "skill-report.json")["consulted"]
            applied = any(
                row["skill"] == proposal["skill"] and row["verdict"] == "useful"
                for row in consulted
            )
            comparison = finish["comparison"]
            criterion_passed = comparison.get("skill_success") == len(seeds) and comparison[
                "program_ok"
            ] == len(seeds)
            passed = (
                criterion_passed
                and applied
                and review["verdict"] == "PASS"
                and review.get("skill_application_verified") is True
            )
            result = {
                "schema": "so101-scoped-skill-verification-v1",
                "skill": proposal["skill"],
                "status": "verified" if passed else "refuted",
                "verdict": "verified" if passed else "refuted",
                "verification_contract": spec,
                "criterion_passed": criterion_passed,
                "skill_application_verified": applied
                and review.get("skill_application_verified") is True,
                "provenance_audit": review["verdict"],
                "visual_control_status": review.get("visual_control_status", "not_reviewed"),
                "visual_control_assessment": review.get("visual_control_assessment"),
                "independent": True,
                "no_proposer_code": True,
                "library_sha256": library["sha256"],
                "inputs_sha256": c.file_sha(input_path),
                "comparison": comparison,
                "worker_session_sha256": c.file_sha(workspace / "session.json"),
                "finish_sha256": c.file_sha(workspace / "finish.json"),
                "promoted": False,
            }
            c.write_json(path, result)
        if result["status"] == "verified":
            history = library_dir / "history" / library["sha256"] / "verification.json"
            if not history.exists():
                skills.promote(library_dir, working, [proposal], result)
            else:
                saved = c.read_json(history)
                if {k: v for k, v in saved.items() if k != "promoted"} != {
                    k: v for k, v in result.items() if k != "promoted"
                }:
                    raise ValueError("Skill promotion history changed")
            working = library
            promoted.append(proposal["skill"])
            result["promoted"] = True
            c.write_json(path, result)
        jobs.append(
            {
                "skill": proposal["skill"],
                "verdict": result["verdict"],
                "contract": spec["id"],
                "report": str(path.relative_to(directory)),
                "sha256": c.file_sha(path),
            }
        )
    aggregate = {
        "schema": "so101-scoped-skill-verification-v1",
        "verdict": "verified"
        if len(promoted) == len(proposals)
        else "partially_verified"
        if promoted
        else "refuted",
        "status": "completed",
        "proposals_sha256": proposal_sha,
        "promoted_skills": promoted,
        "final_library_sha256": working["sha256"],
        "jobs": jobs,
    }
    c.write_json(aggregate_path, aggregate)
    return aggregate
