"""Model-level SO-101 import, measured servo check, video and optional 3D viewer.

Run with Python in .venv-robosuite. This host-side model check is separate from
cap-harness generated programs. Use so101_aspire_control.py with the so101 profile
for ASPIRE public-API actions.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import imageio.v2 as imageio
import mujoco
import numpy as np

from cap_harness.robosuite.so101_model import build_so101_scene, load_so101_description


def camera() -> mujoco.MjvCamera:
    view = mujoco.MjvCamera()
    view.lookat[:] = [0.08, 0, 0.18]
    view.distance = 0.82
    view.azimuth = 135
    view.elevation = -22
    return view


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path("outputs/local/so101-import"))
    parser.add_argument("--view", action="store_true", help="Open an orbitable, static 3D viewer")
    args = parser.parse_args()
    description = load_so101_description()
    scene = build_so101_scene(description)
    model = scene.compile()
    names = description.scene_joint_names
    assert model.nq == 6 and model.nu == 6, "Expected five arm axes and one gripper axis"
    joint_ids = np.array([model.joint(name).id for name in names])
    actuator_ids = np.array([model.actuator(name).id for name in names])
    addresses = model.jnt_qposadr[joint_ids]
    data = mujoco.MjData(model)
    home = np.zeros(6)
    home[-1] = 0.8  # Native gripper hinge angle in radians, not a normalized aperture.
    data.qpos[addresses] = home
    data.ctrl[actuator_ids] = home
    mujoco.mj_forward(model, data)

    if args.view:
        from mujoco import viewer as mj_viewer

        with mj_viewer.launch_passive(model, data) as viewer:
            viewer.cam.lookat[:] = camera().lookat
            viewer.cam.distance = camera().distance
            viewer.cam.azimuth = camera().azimuth
            viewer.cam.elevation = camera().elevation
            print("SO-101 3D viewer ready. Drag to orbit; close its window to exit.", flush=True)
            while viewer.is_running():
                viewer.sync()
                time.sleep(0.02)
        return

    run = args.output_root / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S.%fZ")
    run.mkdir(parents=True, exist_ok=False)
    (run / "scene.xml").write_text(scene.to_xml(), encoding="utf-8")
    # Check that the exported scene is usable independently of the in-memory spec.
    reloaded = mujoco.MjModel.from_xml_path(str(run / "scene.xml"))
    assert reloaded.nu == model.nu
    renderer = mujoco.Renderer(model, height=512, width=512)
    view = camera()
    render_every = round(1 / (20 * model.opt.timestep))
    phase_steps = round(1 / model.opt.timestep)
    commands = []
    for index, name in enumerate(names[:5]):
        target = home.copy()
        target[index] += 0.16
        commands.extend([(name + "_move", target), (name + "_return", home.copy())])
    closed = home.copy()
    closed[-1] = 0.15
    commands.extend([("gripper_close", closed), ("gripper_open", home.copy())])
    measurements = []
    frame_count = 0
    tick = 0
    try:
        with imageio.get_writer(str(run / "motion.mp4"), fps=20) as video:
            for phase, target in commands:
                start = data.ctrl[actuator_ids].copy()
                for step in range(phase_steps):
                    u = min(1.0, (step + 1) / (0.4 * phase_steps))
                    blend = 0.5 - 0.5 * np.cos(np.pi * u)
                    data.ctrl[actuator_ids] = start + blend * (target - start)
                    mujoco.mj_step(model, data)
                    assert np.isfinite(data.qpos).all(), "Non-finite simulated state"
                    if tick % render_every == 0:
                        renderer.update_scene(data, camera=view)
                        pixels = renderer.render()
                        video.append_data(pixels)
                        if frame_count == 0:
                            imageio.imwrite(run / "preview.png", pixels)
                        frame_count += 1
                    tick += 1
                measured = data.qpos[addresses].copy()
                error = float(np.max(np.abs(measured - target)))
                print(f"{phase}: maximum joint error {error:.5f} rad", flush=True)
                measurements.append({
                    "phase": phase, "target_rad": target.tolist(),
                    "measured_rad": measured.tolist(), "max_error_rad": error,
                })
                if error > 0.025:
                    raise RuntimeError(f"Servo tracking failed in {phase}: {error:.5f} rad")
    finally:
        renderer.close()

    report = {
        "model_import_ok": True,
        "validation_scope": "model_import_only",
        "upstream_commit": description.commit,
        "upstream_xml_sha256": hashlib.sha256(description.model_path.read_bytes()).hexdigest(),
        "composition": "Robosuite MujocoWorldBase + native MuJoCo MjSpec attachment",
        "joint_names": list(names), "joint_ranges_rad": model.jnt_range[joint_ids].tolist(),
        "actuators": model.nu, "meshes": model.nmesh,
        "gripper_units": "native hinge angle in radians; not LeRobot 0..100",
        "simulator_seconds": float(data.time), "video_frames": frame_count,
        "measurements": measurements,
    }
    (run / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"SO101_IMPORT_OK: {run}", flush=True)
    print("Five arm joints and the gripper tracked their targets. See so101_aspire_control.py for the public API example.")


if __name__ == "__main__":
    main()
