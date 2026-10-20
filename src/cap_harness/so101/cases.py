"""Versioned, explicit synthetic cases; selection never depends on RNG state."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

from cap_harness.so101.paths import workspace_root

DEFAULT_CASES_PATH = (
    workspace_root() / "configs/so101/strawberry-detachment-cases-v1.json"
)
PROTOCOL_VERSION = "so101-strawberry-detachment-v1"
PARTITIONS = ("development", "validation", "evaluation")


def canonical_sha256(value: object) -> str:
    """Hash content independently of JSON whitespace and OS line endings."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class StrawberryDetachmentCase:
    case_id: str
    seed: int
    partition: str
    bent_force_n: float
    junction_time_constant_s: float
    protocol_sha256: str

    def to_record(self) -> dict:
        record = {
            "protocol_version": PROTOCOL_VERSION,
            "protocol_sha256": self.protocol_sha256,
            "case_id": self.case_id,
            "seed": self.seed,
            "partition": self.partition,
            "parameters": {
                "bent_force_n": self.bent_force_n,
                "junction_time_constant_s": self.junction_time_constant_s,
            },
        }
        return {**record, "case_sha256": canonical_sha256(record)}


def load_detachment_cases(path: Path = DEFAULT_CASES_PATH) -> tuple[StrawberryDetachmentCase, ...]:
    """Validate the entire protocol before any simulator is constructed."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Case protocol must be a JSON object")
    if (
        type(payload.get("schema_version")) is not int
        or payload.get("schema_version") != 1
        or payload.get("protocol_version") != PROTOCOL_VERSION
    ):
        raise ValueError("Unsupported strawberry case protocol version")
    if payload.get("task_name") != "so101_strawberry_detachment_cases":
        raise ValueError("Unexpected strawberry case task")
    if payload.get("biological_fracture_calibrated") is not False:
        raise ValueError("The v1 case protocol is not biologically calibrated")
    partitions = payload.get("partitions", {})
    if not isinstance(partitions, dict) or set(partitions) != set(PARTITIONS):
        raise ValueError("Protocol needs development, validation and evaluation partitions")
    declared = {}
    for partition, seeds in partitions.items():
        if not isinstance(seeds, list) or not seeds:
            raise ValueError("Case partitions must be nonempty seed lists")
        for seed in seeds:
            if type(seed) is not int or seed < 0 or seed in declared:
                raise ValueError("Case partition seeds must be unique nonnegative integers")
            declared[seed] = partition
    digest = canonical_sha256(payload)
    result = []
    used_seeds, used_ids, used_conditions = set(), set(), set()
    fields = {"case_id", "seed", "partition", "bent_force_n", "junction_time_constant_s"}
    rows = payload.get("cases")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Case protocol needs a nonempty case list")
    for row in rows:
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError("Unexpected or missing strawberry case fields")
        seed, case_id, partition = row["seed"], row["case_id"], row["partition"]
        if type(seed) is not int or seed not in declared or declared[seed] != partition:
            raise ValueError("Case does not match its declared partition")
        if not isinstance(case_id, str) or not case_id or case_id in used_ids or seed in used_seeds:
            raise ValueError("Duplicate or invalid case identity")
        force, timeconst = row["bent_force_n"], row["junction_time_constant_s"]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (force, timeconst)):
            raise ValueError("Case physics must use finite numbers")
        if not 1.57 <= force <= 5.10 or not 0.008 <= timeconst <= 0.012:
            raise ValueError("Case physics outside the declared v1 envelope")
        conditions = (force, timeconst)
        if conditions in used_conditions:
            raise ValueError("Repeated physical conditions across case partitions")
        used_seeds.add(seed)
        used_ids.add(case_id)
        used_conditions.add(conditions)
        result.append(StrawberryDetachmentCase(case_id, seed, partition, force, timeconst, digest))
    if used_seeds != set(declared):
        raise ValueError("Declared case seeds are missing from the protocol")
    return tuple(result)


def detachment_case_for_seed(
    seed: int, path: Path = DEFAULT_CASES_PATH
) -> StrawberryDetachmentCase:
    if type(seed) is not int or seed < 0:
        raise ValueError("Case seed must be a nonnegative integer")
    for case in load_detachment_cases(path):
        if case.seed == seed:
            return case
    raise ValueError(f"Unknown strawberry case seed {seed}; use a seed declared in the v1 protocol")
