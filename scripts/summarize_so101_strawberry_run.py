"""Combine recorded task diagnosis with execution status without changing the episode."""

import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("run", type=Path)
parser.add_argument("--output", type=Path)
args = parser.parse_args()
outcome = json.loads((args.run / "outcome.json").read_text())
diagnostic_path = args.run / "evaluation/so101-diagnostics.json"
evidence_path = args.run / "evaluation/so101-task.json"
diagnosis = json.loads(diagnostic_path.read_text()) if diagnostic_path.is_file() else None
evidence = json.loads(evidence_path.read_text()) if evidence_path.is_file() else {}
summary = {
    "run": str(args.run.resolve()),
    "case": evidence.get("case"),
    "program_ok": outcome["program_ok"],
    "termination_reason": outcome["termination_reason"],
    "execution_error": outcome["error"],
    "task_success": outcome["task_success"],
    "physical_status": diagnosis["status"] if diagnosis else "unavailable",
    "primary_finding": diagnosis["primary_finding"] if diagnosis else None,
    "findings": diagnosis["findings"] if diagnosis else [],
    "final_state": diagnosis["final_state"] if diagnosis else None,
    "junction_evidence": {
        "last_attached_state": diagnosis.get("last_attached_junction_state") if diagnosis else None,
        "maximum_observed_load_n": evidence.get("maximum_junction_load_n"),
        "maximum_observed_bend_deg": evidence.get("maximum_bend_deg"),
        "note": "Separate maxima need not occur at the same instant.",
    },
    "diagnostic_source": "evaluation/so101-diagnostics.json" if diagnosis else None,
    "diagnostic_error": None
    if diagnosis
    else {
        "code": "diagnostics_unavailable",
        "message": "No physical diagnostic artifact was recorded; do not infer a task failure cause.",
    },
}
if args.output:
    # Finalized episode files belong to its manifest; write summaries outside it.
    if args.output.resolve().is_relative_to(args.run.resolve()):
        parser.error("Write the summary outside the finalized run directory")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2))
