"""Fetch only pinned FruitGym plant resources, without installing its environment."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/so101/fruitgym-assets-v1.json"


def prepare(source=None):
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    target = ROOT / config["checkout"]
    if source:
        commit = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if commit != config["commit"]:
            raise ValueError("Source checkout must match the pinned FruitGym commit")
    for relative, digest in config["files"].items():
        path = target / relative
        if path.exists():
            data = path.read_bytes()
        elif source:
            data = (source / relative).read_bytes()
        else:
            url = (
                f"https://raw.githubusercontent.com/emlynw/fruit-gym/{config['commit']}/{relative}"
            )
            with urlopen(url, timeout=60) as response:
                data = response.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(
                f"Missing/modified upstream resource: {relative}; preserving existing files"
            )
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        print("FruitGym verified:", relative, flush=True)
    (target / "ASPIRE-SOURCE.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    print(f"FruitGym resources ready: {target}; no dependencies or physics settings changed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, help="Optional existing checkout at the pinned commit"
    )
    prepare(parser.parse_args().source)
