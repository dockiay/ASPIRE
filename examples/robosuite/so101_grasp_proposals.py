# Public tools only. This observes and proposes; it sends no motion commands.
result = {"scope": "geometric proposals, no verified grasp", "views": []}
for camera in ["agentview", "sideview"]:
    masks = segment_text(camera, "red")
    row = {"camera": camera, "segmentation_ok": masks.ok, "targets": []}
    if masks.ok:
        for mask in masks.segmentations:
            proposals = generate_grasps(camera, mask, max_candidates=1)
            item = {"ok": proposals.ok, "error": str(proposals.error), "diagnostics": proposals.diagnostics}
            if proposals.ok:
                selected = select_grasp(proposals, strategy="highest_score")
                item["pose"] = selected.pose
                item["score"] = selected.score
                item["metadata"] = selected.metadata
                assert selected.metadata["grasp_verified"] == False
            row["targets"].append(item)
    else:
        row["error"] = str(masks.error)
    result["views"].append(row)
