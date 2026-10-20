"""Initial red-fruit localization using only calibrated public RGB-D images."""

import cv2
import numpy as np
from scipy.optimize import least_squares


def candidates(camera):
    rgb = camera.rgb
    if np.issubdtype(rgb.dtype, np.floating):
        rgb = np.round(rgb * 255).astype(np.uint8)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    # Engineering color prior for this first ripe-red-fruit scene, not a learned detector.
    mask = (
        ((hsv[:, :, 0] <= 7) | (hsv[:, :, 0] >= 175)) & (hsv[:, :, 1] > 85) & (hsv[:, :, 2] > 35)
    ).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8))
    count, labels, stats, centers = cv2.connectedComponentsWithStats(mask, 8)
    result = []
    for index in range(1, count):
        if stats[index, cv2.CC_STAT_AREA] < 12:
            continue
        rows, cols = np.nonzero(labels == index)
        depth = camera.depth_m[rows, cols]
        valid = np.isfinite(depth) & (depth > 0)
        rows, cols, depth = rows[valid], cols[valid], depth[valid]
        if len(depth) < 12:
            continue
        # RGB antialiasing can color a silhouette pixel while its depth hits the
        # distant background. Reject those returns before computing metric extent.
        surface = np.abs(depth - np.median(depth)) <= 0.04
        rows, cols, depth = rows[surface], cols[surface], depth[surface]
        if len(depth) < 12:
            continue
        k = camera.intrinsics
        xyz = np.column_stack(
            ((cols - k[0, 2]) * depth / k[0, 0], (rows - k[1, 2]) * depth / k[1, 1], depth)
        )
        transform = camera.camera_pose.as_matrix()
        points = xyz @ transform[:3, :3].T + transform[:3, 3]
        span = np.ptp(points, axis=0)
        # Broad candidate-size filter excludes the pot; these are configured priors.
        if 0.015 <= max(span) <= 0.08:
            result.append(
                {
                    "points": points,
                    "mask": labels == index,
                    "pixels": len(points),
                    "pixel_center": centers[index].tolist(),
                    "surface_center": np.median(points, axis=0),
                }
            )
    return result


def localize(observation):
    names = ("agentview", "sideview")
    if any(name not in observation.cameras for name in names):
        raise ValueError("Both public camera views are required for initial fruit localization")
    cameras = [observation.cameras[name] for name in names]
    frames = {camera.camera_pose.frame for camera in cameras}
    times = [camera.timestamp_s for camera in cameras]
    if len(frames) != 1 or None in times or max(times) - min(times) > 0.05:
        raise ValueError("Camera frames/timestamps disagree")
    detected = [candidates(camera) for camera in cameras]
    pairs = [
        (a, b)
        for a in detected[0]
        for b in detected[1]
        if np.linalg.norm(a["surface_center"] - b["surface_center"]) < 0.045
    ]
    if len(pairs) != 1:
        raise ValueError("No unique ripe-red fruit matched across both views; do not move")
    first, second = pairs[0]
    # Balance the views so resolution/visible area cannot dominate the fit.
    sampled = [
        item["points"][
            np.linspace(
                0, len(item["points"]) - 1, min(300, len(first["points"]), len(second["points"]))
            ).astype(int)
        ]
        for item in pairs[0]
    ]
    points = np.concatenate(sampled)
    center = np.median(points, axis=0)
    guess = np.append(center, 0.02)
    fit = least_squares(
        lambda value: np.linalg.norm(points - value[:3], axis=1) - value[3],
        guess,
        bounds=(np.append(points.min(0) - 0.03, 0.008), np.append(points.max(0) + 0.03, 0.04)),
        loss="soft_l1",
        f_scale=0.002,
        max_nfev=100,
    )
    rms = float(np.sqrt(np.mean(fit.fun**2)))
    if not fit.success or rms > 0.005:
        raise ValueError("Fruit surface fit is inconsistent; do not move")
    return {
        "ok": True,
        "point_m": fit.x[:3].tolist(),
        "frame": next(iter(frames)),
        "timestamp_s": max(times),
        "fit_radius_m": float(fit.x[3]),
        "fit_rms_m": rms,
        "source": "public RGB-D; red segmentation, dual-view surface sphere fit; approximate center, not full pose",
        "views": [
            {"camera": name, "pixels": item["pixels"], "pixel_center": item["pixel_center"]}
            for name, item in zip(names, pairs[0])
        ],
    }
