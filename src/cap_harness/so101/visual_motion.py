"""Conservative RGB-D motion evidence from public images and measured robot state.

SAM3 supplies caller-selected masks, not object orientation or persistent identity.
This module tracks image texture, lifts matching pixels through calibrated depth,
and fits a rigid transform. It never reads simulator objects, meshes or task state.
Missing texture is an unknown result: neither a mask centroid nor a PCA box can
replace corresponding material points when deciding whether a fruit rotated.
"""

from __future__ import annotations

import itertools

import cv2
import numpy as np

from cap_harness.contracts import Observation, Segmentation

THRESHOLDS = {
    "minimum_tracks": 6,
    "minimum_inlier_fraction": 0.60,
    "minimum_second_spread_m": 0.0025,
    "minimum_patch_std_8bit": 3.0,
    "minimum_patch_correlation": 0.80,
    "maximum_forward_backward_px": 0.6,
    "maximum_depth_patch_range_m": 0.004,
    "ransac_distance_m": 0.0025,
    "maximum_residual_rms_m": 0.0015,
    "maximum_rotation_uncertainty_deg": 12.0,
    "maximum_view_disagreement_deg": 12.0,
    "minimum_view_disagreement_tolerance_deg": 3.0,
    "maximum_view_center_disagreement_m": 0.004,
    "minimum_motion_deg": 3.0,
    "co_motion_rotation_floor_deg": 5.0,
    "co_motion_point_error_m": 0.003,
    "minimum_translation_m": 0.003,
}


def _angle(rotation):
    return float(np.degrees(np.arccos(np.clip((np.trace(rotation) - 1) / 2, -1, 1))))


def _rigid_fit(before, after):
    """Least-squares proper rigid transform for corresponding metric points."""
    center_before = before.mean(axis=0)
    center_after = after.mean(axis=0)
    left, _, right = np.linalg.svd((before - center_before).T @ (after - center_after))
    rotation = right.T @ left.T
    if np.linalg.det(rotation) < 0:
        right[-1] *= -1
        rotation = right.T @ left.T
    return rotation, center_after - rotation @ center_before


def _spread(points):
    return np.linalg.svd(points - points.mean(axis=0), compute_uv=False) / np.sqrt(len(points))


def _robust_fit(before, after):
    """Deterministic RANSAC; a fit is not accepted without later quality gates."""
    count = len(before)
    if count < THRESHOLDS["minimum_tracks"]:
        return None
    rng = np.random.default_rng(0)
    selections = (
        itertools.combinations(range(count), 3)
        if count <= 12
        else (rng.choice(count, 3, replace=False) for _ in range(256))
    )
    best = None
    for selection in selections:
        indices = np.asarray(selection)
        if min(_spread(before[indices])[1], _spread(after[indices])[1]) < 0.0005:
            continue
        rotation, translation = _rigid_fit(before[indices], after[indices])
        errors = np.linalg.norm(before @ rotation.T + translation - after, axis=1)
        mask = errors <= THRESHOLDS["ransac_distance_m"]
        score = (int(mask.sum()), -float(np.minimum(errors, 0.01).sum()))
        if best is None or score > best[0]:
            best = score, mask
    if best is None or best[0][0] < THRESHOLDS["minimum_tracks"]:
        return None
    mask = best[1]
    for _ in range(3):
        rotation, translation = _rigid_fit(before[mask], after[mask])
        errors = np.linalg.norm(before @ rotation.T + translation - after, axis=1)
        updated = errors <= THRESHOLDS["ransac_distance_m"]
        if updated.sum() < THRESHOLDS["minimum_tracks"] or np.array_equal(updated, mask):
            break
        mask = updated
    rotation, translation = _rigid_fit(before[mask], after[mask])
    errors = np.linalg.norm(before @ rotation.T + translation - after, axis=1)
    rms = float(np.sqrt(np.mean(errors[mask] ** 2)))
    spread = float(min(_spread(before[mask])[1], _spread(after[mask])[1]))
    # A deliberately conservative resolution/residual heuristic, not a calibrated
    # confidence interval. A 0.5 mm floor prevents a perfect numerical fit from
    # claiming that image correspondences are exact material-point measurements.
    uncertainty = float(np.degrees(np.arctan2(2 * max(rms, 0.0005), spread * np.sqrt(mask.sum()))))
    return rotation, translation, mask, rms, spread, uncertainty


def _mask(value, camera, camera_name):
    if isinstance(value, Segmentation):
        if value.camera_name not in (camera_name, camera.frame) or value.frame != camera.frame:
            raise ValueError("Segmentation camera/frame must match its observation")
        value = value.mask
    result = np.asarray(value)
    if result.dtype != np.bool_ or result.shape != camera.depth_m.shape:
        raise ValueError("Each mask must be boolean and match its camera image shape")
    return result


def _gray(camera):
    rgb = camera.rgb
    if np.issubdtype(rgb.dtype, np.floating):
        rgb = np.rint(rgb * 255).astype(np.uint8)
    elif rgb.dtype != np.uint8:
        rgb = rgb.astype(np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def _lift(camera, pixel):
    x, y = map(float, pixel)
    column, row = int(np.floor(x)), int(np.floor(y))
    if not 0 <= row < camera.depth_m.shape[0] - 1 or not 0 <= column < camera.depth_m.shape[1] - 1:
        return None
    patch = camera.depth_m[row : row + 2, column : column + 2]
    if (
        not np.all(np.isfinite(patch) & (patch > 0))
        or np.ptp(patch) > THRESHOLDS["maximum_depth_patch_range_m"]
    ):
        return None
    dx, dy = x - column, y - row
    depth = (1 - dy) * ((1 - dx) * patch[0, 0] + dx * patch[0, 1]) + dy * (
        (1 - dx) * patch[1, 0] + dx * patch[1, 1]
    )
    ray = np.linalg.solve(camera.intrinsics, [x, y, 1.0])
    point = ray * depth / ray[2]
    transform = camera.camera_pose.as_matrix()
    return transform[:3, :3] @ point + transform[:3, 3]


def _track_view(camera_before, camera_after, mask_before, mask_after, camera_name):
    report = {
        "camera": camera_name,
        "status": "unknown",
        "reason": "insufficient_texture_or_visible_interior",
        "features": 0,
        "accepted_tracks": 0,
        "inliers": 0,
        "correspondences": [],
    }
    gray_before, gray_after = _gray(camera_before), _gray(camera_after)
    # Nine-pixel patches must be wholly inside the selected masks. This keeps
    # silhouette, finger and background corners out of object-motion evidence.
    interior_before = cv2.erode(mask_before.astype(np.uint8), np.ones((11, 11), np.uint8))
    interior_after = cv2.erode(mask_after.astype(np.uint8), np.ones((11, 11), np.uint8))
    features = cv2.goodFeaturesToTrack(
        gray_before,
        maxCorners=120,
        qualityLevel=0.02,
        minDistance=3,
        mask=interior_before,
        blockSize=3,
    )
    empty = np.empty((0, 3))
    if features is None:
        return empty, empty, [], report
    report["features"] = len(features)
    current, forward_ok, _ = cv2.calcOpticalFlowPyrLK(
        gray_before,
        gray_after,
        features,
        None,
        winSize=(9, 9),
        maxLevel=2,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 40, 0.01),
    )
    if current is None:
        return empty, empty, [], report
    reverse, reverse_ok, _ = cv2.calcOpticalFlowPyrLK(
        gray_after,
        gray_before,
        current,
        None,
        winSize=(9, 9),
        maxLevel=2,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 40, 0.01),
    )
    if reverse is None:
        return empty, empty, [], report
    before, after, pixels = [], [], []
    height, width = gray_after.shape
    for index, (source, destination) in enumerate(zip(features[:, 0], current[:, 0], strict=True)):
        if (
            not forward_ok[index, 0]
            or not reverse_ok[index, 0]
            or not np.all(np.isfinite(destination))
            or np.linalg.norm(features[index] - reverse[index])
            > THRESHOLDS["maximum_forward_backward_px"]
        ):
            continue
        column, row = np.rint(destination).astype(int)
        if not 0 <= row < height or not 0 <= column < width or not interior_after[row, column]:
            continue
        first = cv2.getRectSubPix(gray_before, (9, 9), tuple(map(float, source))).astype(float)
        second = cv2.getRectSubPix(gray_after, (9, 9), tuple(map(float, destination))).astype(float)
        if min(float(first.std()), float(second.std())) < THRESHOLDS["minimum_patch_std_8bit"]:
            continue
        correlation = float(np.corrcoef(first.reshape(-1), second.reshape(-1))[0, 1])
        if not np.isfinite(correlation) or correlation < THRESHOLDS["minimum_patch_correlation"]:
            continue
        source_point = _lift(camera_before, source)
        destination_point = _lift(camera_after, destination)
        if source_point is None or destination_point is None:
            continue
        before.append(source_point)
        after.append(destination_point)
        pixels.append([*map(float, source), *map(float, destination)])
    report["accepted_tracks"] = len(before)
    report["reason"] = (
        "insufficient_valid_correspondences" if len(before) < 6 else "pending_rigid_fit"
    )
    return np.asarray(before).reshape(-1, 3), np.asarray(after).reshape(-1, 3), pixels, report


def _fit_failures(fit, count):
    if fit is None:
        return ["insufficient_rigid_inliers"]
    _, _, mask, rms, spread, uncertainty = fit
    reasons = []
    if mask.sum() / count < THRESHOLDS["minimum_inlier_fraction"]:
        reasons.append("low_rigid_inlier_fraction")
    if spread < THRESHOLDS["minimum_second_spread_m"]:
        reasons.append("insufficient_spatial_spread")
    if rms > THRESHOLDS["maximum_residual_rms_m"]:
        reasons.append("rigid_fit_residual_too_large")
    if uncertainty > THRESHOLDS["maximum_rotation_uncertainty_deg"]:
        reasons.append("rotation_uncertainty_too_large")
    return reasons


def compare_visual_motion(before, after, masks_before, masks_after, arm="primary"):
    """Compare selected visible material motion with measured tool motion.

    Inputs are two public Observation values and camera-name → Segmentation or
    boolean-mask dictionaries. Select the same object in each image. This call
    does not segment, move, infer hidden geometry or establish grasp/release.
    ``ok`` means the comparison ran; inspect ``status`` and ``evidence``.
    """
    if not isinstance(before, Observation) or not isinstance(after, Observation):
        raise ValueError("before and after must be public Observation values")
    if before.timestamp_s is None or after.timestamp_s is None:
        raise ValueError("Both observations require acquisition timestamps")
    if after.timestamp_s < before.timestamp_s:
        raise ValueError("after must not precede before")
    for observation in (before, after):
        timestamps = [observation.robot_state.timestamp_s]
        timestamps.extend(camera.timestamp_s for camera in observation.cameras.values())
        if any(
            stamp is None or abs(stamp - observation.timestamp_s) > 1e-6 for stamp in timestamps
        ):
            raise ValueError("Camera, robot and observation acquisition timestamps must agree")
    if not isinstance(masks_before, dict) or not isinstance(masks_after, dict):
        raise ValueError("masks must map camera names to selected masks")
    if not masks_before or set(masks_before) != set(masks_after) or len(masks_before) > 4:
        raise ValueError("Use matching nonempty sets of at most four camera masks")
    if (
        arm not in before.robot_state.end_effector_poses
        or arm not in after.robot_state.end_effector_poses
    ):
        raise ValueError("arm must name a measured end effector in both observations")
    pose_before = before.robot_state.end_effector_poses[arm]
    pose_after = after.robot_state.end_effector_poses[arm]
    if pose_before.frame != pose_after.frame:
        raise ValueError("Measured tool poses must use the same base frame")
    tool_before, tool_after = pose_before.as_matrix(), pose_after.as_matrix()
    tool_delta = tool_after @ np.linalg.inv(tool_before)
    output = {
        "ok": True,
        "status": "unknown",
        "evidence": "unknown",
        "scope": "Public RGB-D texture tracks and measured tool pose; no grasp or release certification",
        "reference_time_s": float(before.timestamp_s),
        "current_time_s": float(after.timestamp_s),
        "frame": pose_before.frame,
        "fruit_motion": None,
        "tool_motion": {
            "rotation_deg": _angle(tool_delta[:3, :3]),
            "rotation_matrix": tool_delta[:3, :3].tolist(),
            "translation_m": tool_delta[:3, 3].tolist(),
            "displacement_m": float(np.linalg.norm(tool_after[:3, 3] - tool_before[:3, 3])),
        },
        "relative_motion": None,
        "quality": {
            "tracks": 0,
            "inliers": 0,
            "inlier_fraction": 0.0,
            "residual_rms_m": None,
            "spatial_spread_m": None,
            "rotation_uncertainty_deg": None,
            "view_agreement_deg": None,
        },
        "reasons": [],
        "views": [],
        "thresholds": dict(THRESHOLDS),
        "uncertainty_note": "Angular uncertainty is a fit/resolution heuristic, not a calibrated confidence interval; repeated texture can still misassociate. Masks carry no timestamp: selection identity and freshness are caller responsibility.",
    }
    source_parts, destination_parts, pixel_parts, fits = [], [], [], []
    for name in sorted(masks_before):
        if name not in before.cameras or name not in after.cameras:
            raise ValueError("Each mask must name a camera present in both observations")
        camera_before, camera_after = before.cameras[name], after.cameras[name]
        if camera_before.rgb.shape != camera_after.rgb.shape:
            raise ValueError("Each camera must retain its image dimensions between observations")
        if (
            camera_before.camera_pose.frame != pose_before.frame
            or camera_after.camera_pose.frame != pose_before.frame
        ):
            raise ValueError("Camera poses and measured tool poses must use the same base frame")
        selected_before = _mask(masks_before[name], camera_before, name)
        selected_after = _mask(masks_after[name], camera_after, name)
        source, destination, pixels, report = _track_view(
            camera_before, camera_after, selected_before, selected_after, name
        )
        fit = _robust_fit(source, destination)
        if not _fit_failures(fit, len(source)):
            fits.append(fit)
            report["status"] = "estimated"
            report["reason"] = "texture_tracks_fit_rigid_motion"
        output["views"].append(report)
        source_parts.append(source)
        destination_parts.append(destination)
        pixel_parts.append(pixels)
    source, destination = np.concatenate(source_parts), np.concatenate(destination_parts)
    output["quality"]["tracks"] = len(source)
    fit = _robust_fit(source, destination)
    failures = _fit_failures(fit, len(source))
    if fit is None:
        output["reasons"] = failures
        return output
    rotation, translation, inliers, rms, spread, uncertainty = fit
    output["quality"].update(
        {
            "inliers": int(inliers.sum()),
            "inlier_fraction": float(inliers.mean()),
            "residual_rms_m": rms,
            "spatial_spread_m": spread,
            "rotation_uncertainty_deg": uncertainty,
        }
    )
    offset = 0
    for report, pixels in zip(output["views"], pixel_parts, strict=True):
        selected = inliers[offset : offset + len(pixels)]
        report["inliers"] = int(selected.sum())
        # Evenly spaced bounded points let a reviewer check actual image tracks.
        for index in np.linspace(0, len(pixels) - 1, min(32, len(pixels)), dtype=int):
            report["correspondences"].append([*pixels[index], bool(selected[index])])
        offset += len(pixels)
    center = source[inliers].mean(axis=0)
    if len(fits) >= 2:
        angles, positions, angle_failures = [], [], []
        for first, second in itertools.combinations(fits, 2):
            angle = _angle(first[0].T @ second[0])
            angles.append(angle)
            tolerance = min(
                THRESHOLDS["maximum_view_disagreement_deg"],
                max(THRESHOLDS["minimum_view_disagreement_tolerance_deg"], first[5] + second[5]),
            )
            angle_failures.append(angle > tolerance)
            positions.append(
                float(np.linalg.norm(first[0] @ center + first[1] - second[0] @ center - second[1]))
            )
        output["quality"]["view_agreement_deg"] = max(angles)
        if any(angle_failures) or max(positions) > THRESHOLDS["maximum_view_center_disagreement_m"]:
            failures.append("camera_motion_estimates_disagree")
        # Pooling cannot manufacture stronger rotational evidence by averaging
        # contrary camera estimates or diluting one view's resolution limit.
        uncertainty = max(uncertainty, *(item[5] for item in fits), max(angles) / 2)
        output["quality"]["rotation_uncertainty_deg"] = uncertainty
    if failures:
        output["reasons"] = failures
        return output
    fruit_delta = np.eye(4)
    fruit_delta[:3, :3], fruit_delta[:3, 3] = rotation, translation
    # Map old tool coordinates, through observed object motion, into new tool
    # coordinates. Identity would preserve the full object/tool relationship.
    relative = np.linalg.inv(tool_after) @ fruit_delta @ tool_before
    angular_error = _angle(relative[:3, :3])
    prediction_error = float(
        np.sqrt(
            np.mean(
                np.sum(
                    (
                        source[inliers] @ tool_delta[:3, :3].T
                        + tool_delta[:3, 3]
                        - destination[inliers]
                    )
                    ** 2,
                    axis=1,
                )
            )
        )
    )
    fruit_angle = _angle(rotation)
    output["status"] = "estimated"
    output["fruit_motion"] = {
        "rotation_deg": fruit_angle,
        "rotation_matrix": rotation.tolist(),
        "translation_m": translation.tolist(),
        "displacement_m": float(np.linalg.norm(destination[inliers].mean(axis=0) - center)),
    }
    output["relative_motion"] = {
        "rotation_error_deg": angular_error,
        "translation_error_m": float(np.linalg.norm(relative[:3, 3])),
        "point_prediction_rms_m": prediction_error,
        "rotation_matrix": relative[:3, :3].tolist(),
        "translation_m": relative[:3, 3].tolist(),
    }
    tolerance = THRESHOLDS["co_motion_rotation_floor_deg"]
    significant_motion = max(THRESHOLDS["minimum_motion_deg"], 2 * uncertainty)
    tool_angle = output["tool_motion"]["rotation_deg"]
    fruit_displacement = float(np.linalg.norm(destination[inliers].mean(axis=0) - center))
    tool_displacement = float(
        np.linalg.norm(tool_delta[:3, :3] @ center + tool_delta[:3, 3] - center)
    )
    # Translation is measured at the tracked surface, so a rotating tool's
    # arbitrary frame origin cannot manufacture translation agreement.
    translation_uncertainty = 2 * max(rms, 0.0005)
    significant_translation = max(THRESHOLDS["minimum_translation_m"], 2 * translation_uncertainty)
    output["quality"]["translation_uncertainty_m"] = translation_uncertainty
    output["tool_motion"]["tracked_surface_displacement_m"] = tool_displacement
    disagreement = (
        angular_error - uncertainty > tolerance
        or prediction_error > THRESHOLDS["co_motion_point_error_m"]
    )
    rotation_evidence = "unknown"
    translation_evidence = "unknown"
    if disagreement:
        rotation_evidence = translation_evidence = "relative_motion_detected"
    else:
        if max(fruit_angle, tool_angle) < significant_motion:
            rotation_evidence = "motion_too_small"
        elif (
            min(fruit_angle, tool_angle) >= significant_motion
            and angular_error + uncertainty <= tolerance
        ):
            rotation_evidence = "co_motion_consistent"
        if max(fruit_displacement, tool_displacement) < significant_translation:
            translation_evidence = "motion_too_small"
        elif (
            min(fruit_displacement, tool_displacement) >= significant_translation
            and angular_error + uncertainty <= tolerance
            and prediction_error + translation_uncertainty <= THRESHOLDS["co_motion_point_error_m"]
        ):
            translation_evidence = "co_motion_consistent"
    output["motion_components"] = {
        "rotation": rotation_evidence,
        "translation": translation_evidence,
    }
    if disagreement:
        output["evidence"] = "relative_motion_detected"
    elif "co_motion_consistent" in output["motion_components"].values():
        output["evidence"] = "co_motion_consistent"
    elif all(value == "motion_too_small" for value in output["motion_components"].values()):
        output["evidence"] = "motion_too_small"
    else:
        output["evidence"] = "unknown"
    output["reasons"] = [
        "two_view_motion_agreement"
        if len(fits) >= 2
        else "single_view_or_pooled_tracks_without_independent_view_confirmation"
    ]
    if output["evidence"] == "unknown":
        output["reasons"].append("rotation_or_tool_agreement_not_resolved_above_uncertainty")
    return output
