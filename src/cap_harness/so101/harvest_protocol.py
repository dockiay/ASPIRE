"""Separate development identity for the fixed full-episode scene."""

import hashlib
import json

from cap_harness.so101.cases import canonical_sha256
from cap_harness.so101.paths import workspace_root

ROOT = workspace_root()
SUITE = "so101_fruitgym_harvest"
PATH = ROOT / "configs/so101/fruitgym-harvest-v2.json"


def protocol():
    value = json.loads(PATH.read_text(encoding="utf-8"))
    assets = json.loads((ROOT / value["asset_manifest"]).read_text(encoding="utf-8"))
    return {
        **value,
        "asset_manifest_sha256": canonical_sha256(assets),
        "asset_files": assets["files"],
    }


def cases():
    value = protocol()
    digest = canonical_sha256(value)
    return [{**row, "suite": SUITE, "protocol_sha256": digest} for row in value["cases"]]


def case_for(seed):
    if type(seed) is not int:
        raise ValueError("Harvest seed must be an integer")
    for row in cases():
        if row["seed"] == seed:
            return row
    raise ValueError("Unknown harvest case; use a registered v2 seed")


def resource_identity():
    from cap_harness.so101.fruitgym_plant import resources

    root, config = resources()
    checkout = ROOT / config["checkout"]
    return {
        "manifest_sha256": canonical_sha256(config),
        "files": {
            name: hashlib.sha256((checkout / name).read_bytes()).hexdigest()
            for name in config["files"]
        },
    }
