"""Host-only engineering measurements, never input or policy for the ASPIRE worker."""

import argparse
import json
from pathlib import Path

import numpy as np

from cap_harness.so101.adapter import SO101Adapter
from cap_harness.so101.cases import canonical_sha256
from cap_harness.so101.harvest_protocol import cases, protocol
from cap_harness.so101.vision import localize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = []
    for case in cases():
        if case["partition"] != "development":
            continue
        adapter = SO101Adapter(camera_width=320, camera_height=240, horizon=1200)
        try:
            adapter.reset("so101_fruitgym_harvest", case["seed"])
            env = adapter.native_env
            observation = env._observation()
            env._observation = lambda: observation
            # Explicit host-side engineering reference, not the controller's
            # SAM3 provider and never input to a generated harvesting policy.
            localization = dict(localize(adapter.get_observation()))
            error = float(
                np.linalg.norm(np.asarray(localization["point_m"]) - env.fruit_position())
            )
            for _ in range(env.substeps * 20):
                env.sim.step()
                env._after_physics_step()
            records.append(
                {
                    "seed": case["seed"],
                    "public_localization": localization,
                    "host_only_localization_error_m": error,
                    "initial_forbidden_contacts": sorted(env.forbidden_contacts),
                    "uncommanded_release_after_1s": env.detached_time is not None,
                    "joint_limit_margin_rad": env.minimum_joint_limit_margin_rad,
                    "effector_samples": [
                        adapter.get_gripper_geometry(opening)
                        for opening in (0, 0.2, 0.4, 0.6, 0.8, 1)
                    ],
                }
            )
        finally:
            adapter.close()
    result = {
        "schema": "so101-bank-engineering-v2",
        "localization_provider": "color-rgbd host-only engineering reference; not SAM3",
        "scope": "Development-scene calibration/idle checks; no generated harvesting policy and no benchmark success claim",
        "protocol_sha256": canonical_sha256(protocol()),
        "cases": records,
        "maximum_localization_error_m": max(
            row["host_only_localization_error_m"] for row in records
        ),
        "checks_pass": all(
            not row["initial_forbidden_contacts"]
            and not row["uncommanded_release_after_1s"]
            and row["joint_limit_margin_rad"] > 0
            for row in records
        ),
        "limitations": [
            "Uncalibrated release/friction/rigid foliage",
            "Public obstacle checker certifies samples only",
            "Stock SO-101 lacks these virtual force sensors",
            "Positive contact and force-stop fixtures are separate pytest evidence; not harvest trajectories",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "checks_pass": result["checks_pass"],
                "cases": len(records),
                "maximum_localization_error_m": result["maximum_localization_error_m"],
            }
        )
    )
    return 0 if result["checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
