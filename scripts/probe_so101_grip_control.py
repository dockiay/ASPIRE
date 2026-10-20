"""Engineering A/B on an existing public grasp prefix; never a learned policy.

Each branch replays the same prefix with SAM3. Native full-state hashes must match
before comparing. Evaluator geometry is used only for host-side measurements.
No fracture parameters, scene positions or skill library members are modified.
"""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

import mujoco
import numpy as np
from PIL import Image

from cap_harness.api import CapApi
from cap_harness.contracts import MotionStrategy
from cap_harness.registry import SO101_PUBLIC_TOOL_NAMES, ToolRegistry
from cap_harness.runtime import ProgramExecutor
from cap_harness.so101.adapter import SO101Adapter
from cap_harness.so101.perception import configuration, provider
from cap_harness.so101.providers import SO101IKProvider


def run(source, seed, mode, movement, output):
    adapter = SO101Adapter(camera_width=1280, camera_height=960, horizon=1200)
    try:
        adapter.reset("so101_fruitgym_harvest", seed)
        api = CapApi(
            adapter,
            segmentation_provider=provider(configuration("so101_fruitgym_harvest")),
            ik_providers={"so101": SO101IKProvider()},
            default_motion_strategy=MotionStrategy(ik_solver="so101"),
        )
        execution = ProgramExecutor(
            api.register_tools(ToolRegistry(public_extension_allowlist=SO101_PUBLIC_TOOL_NAMES))
        ).execute_program(source)
        if not execution.ok:
            (output / f"setup-failure-{seed}-{movement}-{mode}.txt").write_text(str(execution))
            raise RuntimeError(str(execution.error))
        env = adapter.native_env
        spec = mujoco.mjtState.mjSTATE_INTEGRATION
        state = np.zeros(mujoco.mj_stateSize(env.model, spec))
        mujoco.mj_getState(env.model, env.sim.data._data, state, spec)
        initial_hash = hashlib.sha256(state.tobytes()).hexdigest()
        initial = adapter.get_robot_state()
        initial_relative = env.fruit_relative_position().copy()
        directory = output / f"case-{seed}-{movement}-{mode}"
        directory.mkdir(parents=True, exist_ok=True)
        for camera, frame in adapter.get_observation().cameras.items():
            Image.fromarray(frame.rgb).save(directory / f"{camera}-before.png")
        samples = []
        original = env._after_physics_step

        def sample():
            original()
            finger = adapter.get_finger_contacts()
            index = env.actuator_ids[5]
            samples.append(
                {
                    "time_s": float(env.sim.data.time),
                    "jaw_error_rad": float(
                        env.sim.data.ctrl[index] - env.sim.data.qpos[env.qpos_indexes[5]]
                    ),
                    "jaw_actuator_force": float(env.sim.data.actuator_force[index]),
                    "opening": env.opening(),
                    "finger_forces_n": {
                        s: finger[s]["normal_force_n"] for s in ("fixed", "moving")
                    },
                    "relative_displacement_m": float(
                        np.linalg.norm(env.fruit_relative_position() - initial_relative)
                    ),
                }
            )

        env._after_physics_step = sample
        # Avoid rendering 20 high-resolution frames per second in a sensor probe.
        rendering = env._observation
        cached = rendering()
        env._observation = lambda: cached
        target = initial.joint_positions["primary"].copy()
        if movement == "rotate":
            target[4] += 0.05  # Host test excitation; not a harvesting waypoint.
        arguments = (
            {}
            if mode == "measured"
            else {
                "gripper_position": 0.0,
                "gripper_speed": 0.02,
            }
        )
        result = adapter.command_joints(
            target,
            duration_s=1.5,
            minimum_duration_s=1.0,
            speed_rad_s=0.08,
            force_limit_n=11,
            stop_on_contact_loss=True,
            **arguments,
        )
        env._observation = rendering
        for camera, frame in adapter.get_observation().cameras.items():
            Image.fromarray(frame.rgb).save(directory / f"{camera}-after.png")
        row = {
            "seed": seed,
            "mode": mode,
            "movement": movement,
            "initial_state_sha256": initial_hash,
            "ok": result.ok,
            "diagnostics": dict(result.diagnostics),
            "sample_count": len(samples),
            "safety_stop": env.safety_stop,
            "final_joint_displacement_rad": (
                adapter.get_robot_state().joint_positions["primary"]
                - initial.joint_positions["primary"]
            ).tolist(),
            "maximum_relative_displacement_m": max(
                (s["relative_displacement_m"] for s in samples), default=0
            ),
            "initial_forces_n": samples[0]["finger_forces_n"] if samples else None,
            "final_forces_n": samples[-1]["finger_forces_n"] if samples else None,
            "peak_finger_force_n": max(
                (max(s["finger_forces_n"].values()) for s in samples), default=0
            ),
        }
        (directory / "samples.json").write_text(json.dumps(samples, indent=2) + "\n")
        (directory / "result.json").write_text(json.dumps(row, indent=2) + "\n")
        print(json.dumps(row), flush=True)
        return row
    finally:
        adapter.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1001])
    parser.add_argument("--movements", nargs="+", choices=["hold", "rotate"], default=["hold", "rotate"])
    parser.add_argument("--fixture-clearance-m", type=float)
    args = parser.parse_args()
    full_source = args.program.read_text()
    marker = "before,masks=snapshot()"
    if marker not in full_source:
        raise ValueError("Expected archived grasp-prefix boundary")
    prefix = full_source.split(marker)[0] + "\nresult = {'engineering_grasp_prefix': True}\n"
    if args.fixture_clearance_m is not None:
        if not 0 <= args.fixture_clearance_m <= 0.003:
            raise ValueError("Engineering fixture clearance must be in [0,.003]")
        prefix = prefix.replace("margin_m=.003", f"margin_m={args.fixture_clearance_m!r}")
    args.output.mkdir(parents=True, exist_ok=False)
    repository = Path(__file__).resolve().parents[1]
    with zipfile.ZipFile(args.output / "runtime-source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((repository / "src").rglob("*.py")):
            archive.write(path, str(path.relative_to(repository)))
        archive.write(Path(__file__), "scripts/probe_so101_grip_control.py")
    (args.output / "grasp-prefix.py").write_text(prefix)
    rows = []
    for seed in args.seeds:
        for movement in args.movements:
            for mode in ("measured", "explicit"):
                rows.append(run(prefix, seed, mode, movement, args.output))
    paired = all(
        len({r["initial_state_sha256"] for r in rows if r["seed"] == seed}) == 1
        for seed in args.seeds
    )
    report = {
        "scope": "engineering A/B, fixed public grasp prefix; not ASPIRE learning or skill promotion",
        "prefix_sha256": hashlib.sha256(prefix.encode()).hexdigest(),
        "fixture_clearance_m": args.fixture_clearance_m,
        "matched_initial_states": paired,
        "cases": rows,
    }
    (args.output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    if not paired:
        raise RuntimeError("Initial states differ; paired causal comparison is invalid")


if __name__ == "__main__":
    main()
