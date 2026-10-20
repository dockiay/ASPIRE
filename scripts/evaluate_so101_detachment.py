"""Repeat the fixed public policy under documented uncalibrated assumptions."""

import argparse
import hashlib
import json
from pathlib import Path

from cap_harness.api import CapApi
from cap_harness.registry import SO101_PUBLIC_TOOL_NAMES, ToolRegistry
from cap_harness.runtime import ProgramExecutor
from cap_harness.so101.adapter import SO101Adapter

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--output", type=Path, default=Path("outputs/local/so101-detachment-sensitivity.json")
)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
program = (repo / "examples/robosuite/so101_strawberry_detachment.py").read_text()
program_sha256 = hashlib.sha256(program.encode()).hexdigest()
rows = []
cases = [
    ("low_force", 1.57, 70, 0.01),
    ("nominal", 3.175, 70, 0.01),
    ("high_force", 5.10, 70, 0.01),
    ("stiffer_proxy", 3.175, 70, 0.008),
    ("softer_proxy", 3.175, 70, 0.012),
    ("angle_60_assumed", 3.175, 60, 0.01),
    ("angle_80_assumed", 3.175, 80, 0.01),
]
for label, force, angle, timeconst in cases:
    adapter = SO101Adapter(camera_width=48, camera_height=48, horizon=1000)
    try:
        adapter.reset("so101_strawberry_detachment", 1)
        env = adapter.native_env
        images = env._observation()
        env._observation = lambda: images
        env.bent_force_n = force
        env.bend_trial_deg = angle
        env.model.eq_solref[env.fixture_id, 0] = timeconst
        registry = CapApi(adapter).register_tools(
            ToolRegistry(public_extension_allowlist=SO101_PUBLIC_TOOL_NAMES)
        )
        execution = ProgramExecutor(registry).execute_program(program)
        evidence = env.task_evidence()
        row = {
            "case": label,
            "program_sha256": program_sha256,
            "model_commit": env.description.commit,
            "threshold_n": force,
            "angle_gate_deg": angle,
            "solref_time_s": timeconst,
            "program_ok": execution.ok,
            "program_error": str(execution.error) if execution.error else None,
            "task_success": adapter.check_success(),
            **{
                k: evidence[k]
                for k in [
                    "release_event",
                    "maximum_bend_deg",
                    "maximum_junction_load_n",
                    "maximum_relative_slip_m",
                    "current_retention_s",
                    "longest_retention_s",
                    "forbidden_contact_pairs",
                    "limit_violations",
                    "retention_violations",
                    "peak_finger_forces_n",
                    "minimum_arm_joint_limit_margin_rad",
                ]
            },
        }
        rows.append(row)
        print(json.dumps(row), flush=True)
    finally:
        adapter.close()
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
