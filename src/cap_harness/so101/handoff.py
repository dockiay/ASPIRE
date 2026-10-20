"""Export the ASPIRE worker's actual selected code and development evidence."""

import json

from cap_harness.so101 import campaign as c
from cap_harness.so101.debug_tools import DebugTools


def export_handoff(root):
    service = DebugTools(root)
    finish = c.read_json(root / "finish.json")
    selected, submission = service.candidate(finish["candidate_id"])
    # Re-audit every result; a summary or a model statement is not the evidence.
    ledger = []
    for path in sorted((root / "candidates").glob("*/submission.json")):
        item = c.read_json(path)
        result, _ = service.inspect_results(item["candidate_id"], mark=False)
        ledger.append({"submission": item, "evidence": result})
    ledger.sort(key=lambda row: row["submission"]["order"])
    target = root / "worker-handoff"
    artifacts = {
        "fix_code.py": (selected / "program.py").read_bytes(),
        "findings.md": (
            "# SO-101 ASPIRE development findings\n\n"
            + finish["analysis"]
            + "\n\nScope: assigned development cases only. Provenance PENDING. "
            "No unseen/held-out evaluation or verified skill promotion.\n"
        ).encode(),
        "skill_report.json": (
            json.dumps(
                {
                    "schema_version": 1,
                    "benchmark": "so101",
                    "suite": service.identity["suite"],
                    "task_id": 0,
                    "library_scope": "No verified SO-101 harvesting skills supplied to this worker",
                    "consulted": [],
                    "proposed_edits": [],
                    "proposed_new": [],
                },
                indent=2,
            )
            + "\n"
        ).encode(),
        "development-evidence.json": (json.dumps(ledger, indent=2) + "\n").encode(),
    }
    if (root / "skill-report.json").exists():
        artifacts["skill_report.json"] = (root / "skill-report.json").read_bytes()
    target.mkdir(exist_ok=True)
    for name, content in artifacts.items():
        path = target / name
        if path.exists() and path.read_bytes() != content:
            raise ValueError("Worker handoff was modified: " + name)
        if not path.exists():
            path.write_bytes(content)
    record = {
        "schema": "so101-aspire-worker-handoff-v1",
        "candidate_id": finish["candidate_id"],
        "program_sha256": submission["program_sha256"],
        "session_sha256": c.file_sha(root / "session.json"),
        "finish_sha256": c.file_sha(root / "finish.json"),
        "cases": service.identity["seeds"],
        "comparison": finish["comparison"],
        "candidate_count": len(ledger),
        "files": {name: c.file_sha(target / name) for name in artifacts},
        "canonical_stage1_complete": False,
        "provenance_audit": "PENDING",
        "reserved_cases_executed": False,
        "verified_skill_promoted": False,
    }
    path = target / "handoff.json"
    if path.exists() and c.read_json(path) != record:
        raise ValueError("Worker handoff manifest was modified")
    c.write_json(path, record)
    return record
