"""Versioned skill snapshots and evidence-gated independent promotion."""

import hashlib
from pathlib import Path
import re
import runpy

from cap_harness.so101 import campaign as c
from cap_harness.so101 import skill_contracts as contracts

NEW_SCHEMA = {
    "type": "object",
    "properties": {
        **{name: {"type": "string"} for name in ("skill", "title", "trigger", "code", "evidence")},
        "evidence_candidate_ids": {"type": "array", "items": {"type": "string"}},
        "verification_contract": {"type": "string", "enum": list(contracts.CONTRACTS)},
    },
    "required": ["skill", "title", "trigger", "code", "evidence", "evidence_candidate_ids"],
    "additionalProperties": False,
}
EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        **{name: {"type": "string"} for name in ("skill", "change", "why", "content")},
        "evidence_candidate_ids": {"type": "array", "items": {"type": "string"}},
        "verification_contract": {"type": "string", "enum": list(contracts.CONTRACTS)},
    },
    "required": ["skill", "change", "why", "content", "evidence_candidate_ids"],
    "additionalProperties": False,
}
REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "skill_library_sha": {"type": "string"},
        "consulted": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "skill": {"type": "string"},
                    "verdict": {
                        "type": "string",
                        "enum": ["useful", "misleading", "wrong", "not-applicable"],
                    },
                    "evidence": {"type": "string"},
                },
                "required": ["skill", "verdict", "evidence"],
                "additionalProperties": False,
            },
        },
        "proposed_edits": {"type": "array", "items": EDIT_SCHEMA},
        "proposed_new": {"type": "array", "items": NEW_SCHEMA},
    },
    "required": ["skill_library_sha", "consulted", "proposed_edits", "proposed_new"],
    "additionalProperties": False,
}


def snapshot(directory):
    directory = Path(directory)
    manifest_path = directory / "library.json"
    manifest = (
        c.read_json(manifest_path)
        if manifest_path.exists()
        else {"schema": "so101-skills-v1", "skills": {}}
    )
    skills = {}
    for skill_id, digest in manifest["skills"].items():
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}\.md", skill_id):
            raise ValueError("Invalid skill identity")
        path = directory / skill_id
        if c.file_sha(path) != digest:
            raise ValueError("Skill library was modified without promotion")
        skills[skill_id] = path.read_text(encoding="utf-8")
    return {
        "manifest": manifest,
        "contents": skills,
        "sha256": c.canonical_sha256({"manifest": manifest, "contents": skills}),
    }


def validate_report(report, library, candidates):
    from jsonschema import ValidationError, validate

    try:
        validate(report, REPORT_SCHEMA)
    except ValidationError as exc:
        raise ValueError("Invalid skill report: " + exc.message) from exc
    canonical = runpy.run_path(
        str(c.ROOT / ".claude/skills/iterative-debugging/scripts/campaign.py")
    )
    problems = canonical["validate_skill_report"](report, check_skill_files=False)
    if problems:
        raise ValueError("ASPIRE skill report: " + "; ".join(problems))
    if report["skill_library_sha"] != library["sha256"]:
        raise ValueError("Skill report references a different library")
    for row in report["consulted"]:
        if row["skill"] not in library["contents"]:
            raise ValueError("Unknown consulted skill")
    ids = []
    for group in ("proposed_edits", "proposed_new"):
        for proposal in report[group]:
            contracts.proposal_contract(proposal)
            skill_id = proposal["skill"]
            content = proposal_content(proposal)
            if (
                not re.fullmatch(r"[a-z][a-z0-9-]{0,63}\.md", skill_id)
                or not content.strip()
                or len(content.encode()) > 24000
            ):
                raise ValueError("Invalid proposed skill")
            if (skill_id in library["contents"]) != (group == "proposed_edits"):
                raise ValueError("New/edit skill identity mismatch")
            if not proposal["evidence_candidate_ids"] or not set(
                proposal["evidence_candidate_ids"]
            ).issubset(candidates):
                raise ValueError("Skill proposal lacks audited candidate evidence")
            ids.append(skill_id)
    if len(ids) != len(set(ids)) or len(ids) > 8:
        raise ValueError("Duplicate or excessive skill proposals")
    return report


def proposal_content(proposal):
    scope = (
        "Verification contract: " + contracts.proposal_contract(proposal)["id"] + "\n\n"
        if "verification_contract" in proposal
        else ""
    )
    if "content" in proposal:
        return scope + proposal["content"]
    return f"# {proposal['title']}\n\n{scope}Trigger: {proposal['trigger']}\n\n```python\n{proposal['code']}\n```\n\nEvidence: {proposal['evidence']}\n"


def proposal_snapshot(library, proposals):
    contents = {**library["contents"], **{p["skill"]: proposal_content(p) for p in proposals}}
    manifest = {
        "schema": "so101-skills-v1",
        "skills": {
            name: hashlib.sha256(text.encode()).hexdigest() for name, text in contents.items()
        },
    }
    return {
        "manifest": manifest,
        "contents": contents,
        "sha256": c.canonical_sha256({"manifest": manifest, "contents": contents}),
    }


def promote(directory, previous, proposals, verification):
    directory = Path(directory)
    if (
        verification.get("status") != "verified"
        or verification.get("provenance_audit") != "PASS"
        or not verification.get("independent")
        or not verification.get("no_proposer_code")
    ):
        raise ValueError("Independent verified evidence required for skill promotion")
    candidate = proposal_snapshot(previous, proposals)
    for proposal in proposals:
        spec = contracts.proposal_contract(proposal)
        if spec["id"] != contracts.FULL and (
            verification.get("verification_contract") != spec
            or verification.get("criterion_passed") is not True
            or verification.get("skill_application_verified") is not True
        ):
            raise ValueError(
                "Partial skill requires its exact registered criterion and verified application"
            )
    if verification.get("library_sha256") != candidate["sha256"]:
        raise ValueError("Verifier did not use this proposed library")
    directory.mkdir(parents=True, exist_ok=True)
    with c.campaign_lock(directory):
        current = snapshot(directory)
        if current["sha256"] == candidate["sha256"]:
            return candidate
        if current != previous:
            raise ValueError("Library changed since verification")
        history = directory / "history" / candidate["sha256"]
        c.write_json(history / "previous.json", previous)
        c.write_json(history / "verification.json", verification)
        for proposal in proposals:
            (directory / proposal["skill"]).write_text(proposal_content(proposal), encoding="utf-8")
        c.write_json(directory / "library.json", candidate["manifest"])
        return candidate
