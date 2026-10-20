"""Analytic RGB-D sphere views for provider tests, independent of task code."""

from types import SimpleNamespace

import numpy as np

from cap_harness.contracts import CameraObservation, Pose


def sphere_views(center, extra=None, normalized=False):
    observations = {}
    height, width, focal = 128, 160, 300
    rows, cols = np.indices((height, width))
    rays = np.stack(
        ((cols - width / 2) / focal, (rows - height / 2) / focal, np.ones_like(rows)), axis=-1
    )
    for name, x in (("agentview", -0.06), ("sideview", 0.06)):
        origin = np.array([x, 0, 0])
        depth = np.ones((height, width))
        rgb = np.full((height, width, 3), 120, dtype=np.uint8)
        for point in [center, *([] if extra is None else [extra])]:
            relative = np.asarray(point) - origin
            a = (rays**2).sum(-1)
            b = -2 * (rays * relative).sum(-1)
            c = relative @ relative - 0.02**2
            disc = b**2 - 4 * a * c
            hit = disc >= 0
            z = (-b - np.sqrt(np.maximum(0, disc))) / (2 * a)
            hit &= (z > 0) & (z < depth)
            depth[hit] = z[hit]
            rgb[hit] = [180, 20, 25]
        if normalized:
            rgb = rgb.astype(float) / 255
        observations[name] = CameraObservation(
            rgb,
            depth,
            np.array([[focal, 0, width / 2], [0, focal, height / 2], [0, 0, 1]]),
            "camera/" + name,
            Pose(origin, np.array([1, 0, 0, 0]), "so101_base"),
            timestamp_s=0,
        )
    return SimpleNamespace(cameras=observations)
