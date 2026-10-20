"""Inspect case identities and partitions without executing reserved evaluation cases."""

import argparse
import json
from pathlib import Path

from cap_harness.so101.cases import PARTITIONS, PROTOCOL_VERSION, load_detachment_cases

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path)
args = parser.parse_args()
cases = load_detachment_cases()
report = {
    "protocol_version": PROTOCOL_VERSION,
    "protocol_sha256": cases[0].protocol_sha256,
    "partitions": {name: [c.seed for c in cases if c.partition == name] for name in PARTITIONS},
    "development_cases": [c.to_record() for c in cases if c.partition == "development"],
    "reserved_outcomes_evaluated": False,
    "biological_fracture_calibrated": False,
}
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
