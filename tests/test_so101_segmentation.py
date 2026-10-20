"""Color-prior perception from analytic public images, with no task objects."""

from dataclasses import replace

import numpy as np
import pytest
from so101_rgbd_fixture import sphere_views

from cap_harness.errors import ErrorCode
from cap_harness.so101.segmentation import ColorSegmentationProvider

pytest.importorskip("cv2")


def test_components_follow_pixels_and_reject_unsupported_queries():
    provider = ColorSegmentationProvider()
    first = sphere_views([0, 0, 0.45]).cameras["agentview"]
    second = sphere_views([0.03, 0, 0.45]).cameras["agentview"]
    masks = [provider.segment_text(camera, "red") for camera in (first, second)]
    assert all(item.ok for item in masks)
    centers = [np.nonzero(item.segmentations[0].mask)[1].mean() for item in masks]
    assert centers[1] > centers[0] + 10
    assert provider.segment_text(first, "anything").error.code is ErrorCode.UNSUPPORTED
    assert provider.segment_text(first, "blue").error.code is ErrorCode.NOT_FOUND
    assert provider.segment_points(first, [[2, 3]]).error.code is ErrorCode.UNSUPPORTED
    assert masks[0].diagnostics["semantic_model"] is False


@pytest.mark.parametrize("dtype", [np.uint8, np.int16, np.float32, np.float64])
def test_rgb_numeric_formats_preserve_masks(dtype):
    camera = sphere_views([0, 0, 0.45]).cameras["agentview"]
    provider = ColorSegmentationProvider()
    expected = provider.segment_text(camera, "red").segmentations[0].mask
    rgb = camera.rgb.astype(dtype)
    if np.issubdtype(dtype, np.floating):
        rgb /= 255
    converted = replace(camera, rgb=rgb)
    result = provider.segment_text(converted, " RED ")
    assert result.ok
    np.testing.assert_array_equal(result.segmentations[0].mask, expected)
    np.testing.assert_array_equal(converted.rgb, rgb)


def test_components_remain_separate_and_invalid_depth_is_excluded():
    camera = sphere_views([-0.03, 0, 0.45], extra=[0.03, 0, 0.45]).cameras["agentview"]
    provider = ColorSegmentationProvider()
    result = provider.segment_text(camera, "red")
    assert result.ok and len(result.segmentations) == 2
    assert not np.any(result.segmentations[0].mask & result.segmentations[1].mask)
    assert not provider.segment_text(
        replace(camera, depth_m=np.zeros_like(camera.depth_m)), "red"
    ).ok
    rgb = camera.rgb.copy()
    rgb[camera.rgb[:, :, 0] > 150] = [20, 90, 160]
    blue = provider.segment_text(replace(camera, rgb=rgb), "blue container")
    assert blue.ok and len(blue.segmentations) == 2
    assert not provider.segment_text(replace(camera, rgb=rgb), "red").ok


def test_untyped_inputs_return_invalid_request():
    provider = ColorSegmentationProvider()
    camera = sphere_views([0, 0, 0.45]).cameras["agentview"]
    assert provider.segment_text(camera, None).error.code is ErrorCode.INVALID_REQUEST
    assert provider.segment_text(object(), "red").error.code is ErrorCode.INVALID_REQUEST
