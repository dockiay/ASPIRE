"""Explicit color-prior RGB-D components; no semantic recognition model."""

import numpy as np

from cap_harness.contracts import CameraObservation, Segmentation, SegmentationSet
from cap_harness.errors import ApiError, ErrorCode


class ColorSegmentationProvider:
    """Color components, not SAM3 or semantic object recognition.

    Queries explicitly select a color prior. Each component remains a separate
    candidate: the policy must handle ambiguity from public geometry.
    """

    QUERIES = {
        "red": "red",
        "red strawberry": "red",
        "ripe red strawberry": "red",
        "blue": "blue",
        "blue container": "blue",
        "blue tray": "blue",
        "green": "green",
        "green foliage": "green",
    }

    def segment_text(self, observation, query):
        import cv2

        if not isinstance(observation, CameraObservation) or not isinstance(query, str):
            return SegmentationSet(
                ok=False,
                error=ApiError(
                    ErrorCode.INVALID_REQUEST, "Provide CameraObservation and a color query string"
                ),
            )
        color = self.QUERIES.get(query.strip().lower())
        diagnostics = {"provider": "color-rgbd", "semantic_model": False}
        if color is None:
            return SegmentationSet(
                ok=False,
                error=ApiError(
                    ErrorCode.UNSUPPORTED, "Color provider accepts: " + ", ".join(self.QUERIES)
                ),
                diagnostics=diagnostics,
            )
        rgb = observation.rgb
        if np.issubdtype(rgb.dtype, np.floating):
            rgb = np.rint(rgb * 255).astype(np.uint8)
        rgb = rgb.astype(np.uint8, copy=False)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        hue = hsv[:, :, 0]
        selected = (
            ((hue <= 7) | (hue >= 175))
            if color == "red"
            else (((hue >= 35) & (hue <= 90)) if color == "green" else ((hue >= 95) & (hue <= 125)))
        )
        mask = (selected & (hsv[:, :, 1] > 85) & (hsv[:, :, 2] > 35)).astype(np.uint8)
        depth = observation.depth_m
        if depth is not None:
            mask &= (np.isfinite(depth) & (depth > 0)).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        items = []
        for index in range(1, count):
            if stats[index, cv2.CC_STAT_AREA] < 12:
                continue
            component = labels == index
            if depth is not None:
                component &= np.abs(depth - np.median(depth[component])) <= 0.04
            if np.count_nonzero(component) < 12:
                continue
            items.append(
                Segmentation(
                    mask=component,
                    label=query,
                    score=1.0,
                    camera_name=observation.frame,
                    frame=observation.frame,
                )
            )
        if not items:
            return SegmentationSet(
                ok=False,
                error=ApiError(
                    ErrorCode.NOT_FOUND, "No matching color component in this public view"
                ),
                diagnostics=diagnostics,
            )
        return SegmentationSet(ok=True, segmentations=items, diagnostics=diagnostics)

    def segment_points(self, observation, points_px):
        return SegmentationSet(
            ok=False,
            error=ApiError(
                ErrorCode.UNSUPPORTED, "Point prompts are not implemented by color-rgbd"
            ),
        )
