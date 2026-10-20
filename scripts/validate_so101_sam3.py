"""Observation-only SAM3/RGB-D integration check; no robot movement or harvest policy."""

import argparse
from pathlib import Path

from cap_harness.run import run_program
from cap_harness.so101 import campaign as c
from cap_harness.so101.debug_tools import runtime_identity
from cap_harness.so101.harvest_protocol import SUITE

PROGRAM = """result = {"scope": "public SAM3 + calibrated RGB-D; no motion", "views": []}
for camera in ["agentview", "sideview"]:
    for query in ["strawberry", "leaf", "container"]:
        masks = segment_text(camera, query)
        row = {"camera": camera, "query": query, "ok": masks.ok, "instances": [], "error": str(masks.error), "error_code": masks.error.code.value if masks.error else None}
        if masks.ok:
            for mask in masks.segmentations:
                item = {"score": mask.score, "pixel_count": sum(sum(row) for row in mask.mask.tolist())}
                try:
                    cloud = mask_to_point_cloud(mask, camera_name=camera, target_frame="so101_base", erosion_pixels=1, depth_range_m=[0.1, 2.0])
                    geometry = estimate_geometry(cloud)
                    item["visible_center_m"] = geometry.pose.position.tolist()
                    item["visible_extents_m"] = geometry.extents.tolist()
                    item["frame"] = cloud.frame
                    item["point_count"] = len(cloud.points)
                except Exception as error:
                    item["geometry_error"] = str(error)
                row["instances"].append(item)
        result["views"].append(row)
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    env = c.child_environment("glfw")
    identity = runtime_identity(env, SUITE)
    if identity["perception"]["backend"] != "sam3":
        parser.error("This check requires SAM3, not the color baseline")
    args.output.mkdir(parents=True, exist_ok=False)
    c.write_json(args.output / "runtime.json", identity)
    program = args.output / "perception_check.py"
    program.write_text(PROGRAM, encoding="utf-8")
    outcome = run_program(
        benchmark="so101",
        suite=SUITE,
        task_id=0,
        seed=0,
        program_path=program,
        output_root=args.output / "episodes",
        max_steps=2,
        camera_width=640,
        camera_height=480,
        capture_videos=False,
    )
    runs = list(args.output.glob("episodes/**/source/program-result.json"))
    result = c.read_json(runs[0]) if len(runs) == 1 else {}
    views = (result.get("result") or {}).get("views", [])
    inference_ok = (
        outcome.program_ok
        and len(views) == 6
        and all(row["ok"] or row.get("error_code") == "no_segmentation" for row in views)
    )
    c.write_json(
        args.output / "verification.json",
        {
            "scope": "live service integration; detections are unverified model estimates",
            "program_ok": outcome.program_ok,
            "inference_transport_ok": inference_ok,
            "task_success": outcome.task_success,
            "physical_success_required": False,
            "steps_executed": c.read_json(outcome.run_dir / "outcome.json")["steps_executed"],
            "queries_completed": len(views),
            "queries_with_detections": sum(bool(row["ok"]) for row in views),
            "instances_with_geometry": sum(
                "visible_center_m" in instance for row in views for instance in row["instances"]
            ),
            "geometry_errors": sum(
                "geometry_error" in instance for row in views for instance in row["instances"]
            ),
            "projection_filter": {
                "erosion_pixels": 1,
                "depth_range_m": [0.1, 2.0],
                "scope": "explicit engineering observation range and one-pixel silhouette margin; not physical camera calibration",
            },
            "views": views,
        },
    )
    print(args.output / "verification.json")
    return 0 if inference_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
