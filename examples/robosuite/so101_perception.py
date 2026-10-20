# Public tools only. Missing detections are recorded, not inferred as absence.
result = {"scope": "public segmentation + calibrated RGB-D; no motion", "views": []}
for camera in ["agentview", "sideview"]:
    for query in ["red", "green", "blue"]:
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
