"""Image-based motion must distinguish fruit rotation, tool rotation and unknown."""

from dataclasses import replace
import json

import cv2
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from cap_harness.contracts import CameraObservation, Observation, RobotState, Segmentation
from cap_harness.geometry import matrix_to_pose
from cap_harness.so101.visual_motion import _robust_fit, compare_visual_motion


def observation(rgb, depth, timestamp, tool=None, cameras=1):
    if tool is None:
        tool = np.eye(4)
        tool[:3, 3] = [0.015, -0.01, 0.4]
    state = RobotState(
        joint_positions={"primary": np.zeros(5)},
        joint_velocities={"primary": np.zeros(5)},
        end_effector_poses={"primary": matrix_to_pose(tool, frame="so101_base")},
        gripper_positions={"primary": 0.4},
        base_frame="so101_base",
        timestamp_s=timestamp,
        embodiment="so101",
    )
    return Observation(
        cameras={
            f"camera{index}": CameraObservation(
                rgb=rgb,
                depth_m=depth,
                intrinsics=np.array([[800, 0, 80], [0, 800, 80], [0, 0, 1]]),
                frame=f"camera{index}",
                camera_pose=matrix_to_pose(np.eye(4), frame="so101_base"),
                timestamp_s=timestamp,
            )
            for index in range(cameras)
        },
        robot_state=state,
        timestamp_s=timestamp,
    )


def rendered_pair(angles=(0, 0, 8), displacement=(0, 0, 0), tool_follows=True):
    """A textured metric plane rendered through known camera projection."""
    rng = np.random.default_rng(42)
    gray = cv2.GaussianBlur(rng.integers(10, 245, (160, 160), dtype=np.uint8), (3, 3), 0.6)
    y, x = np.indices(gray.shape)
    mask = (x - 80) ** 2 + (y - 80) ** 2 < 55**2
    gray[~mask] = 0
    rgb = np.repeat(gray[:, :, None], 3, axis=2)
    intrinsic = np.array([[800, 0, 80], [0, 800, 80], [0, 0, 1.0]])
    rotation = Rotation.from_euler("xyz", angles, degrees=True).as_matrix()
    center = np.array([0, 0, 0.4])
    translation = center + displacement - rotation @ center
    motion = np.eye(4)
    motion[:3, :3], motion[:3, 3] = rotation, translation
    homography = (
        intrinsic @ (rotation + np.outer(translation, [0, 0, 1]) / 0.4) @ np.linalg.inv(intrinsic)
    )
    after_rgb = cv2.warpPerspective(rgb, homography, (160, 160))
    after_mask = cv2.warpPerspective(
        mask.astype(np.uint8), homography, (160, 160), flags=cv2.INTER_NEAREST
    ).astype(bool)
    rays = np.stack([(x - 80) / 800, (y - 80) / 800, np.ones_like(x)], axis=-1)
    normal = rotation[:, 2]
    after_depth = (normal @ (center + displacement)) / (rays @ normal)
    first = observation(rgb, np.full((160, 160), 0.4), 0.0)
    before_tool = first.robot_state.end_effector_poses["primary"].as_matrix()
    second = observation(
        after_rgb, after_depth, 1.0, motion @ before_tool if tool_follows else before_tool
    )
    return first, second, {"camera0": mask}, {"camera0": after_mask}, motion


@pytest.mark.parametrize("angles", [(0, 0, 8), (5, -4, 6)])
def test_rendered_textured_rgbd_recovers_co_rotation(angles):
    before, after, masks0, masks1, expected = rendered_pair(angles)
    result = compare_visual_motion(before, after, masks0, masks1)
    assert result["status"] == "estimated", result
    assert result["evidence"] == "co_motion_consistent", result
    assert result["relative_motion"]["rotation_error_deg"] < 1.5
    assert result["relative_motion"]["point_prediction_rms_m"] < 0.001
    np.testing.assert_allclose(
        result["fruit_motion"]["rotation_matrix"], expected[:3, :3], atol=0.025
    )
    assert result["quality"]["inliers"] >= 6
    assert len(result["views"][0]["correspondences"]) <= 32
    json.dumps(result, allow_nan=False)


def test_stationary_fruit_does_not_inherit_tool_rotation():
    before, stationary, masks0, masks1, _ = rendered_pair((0, 0, 0))
    tool = stationary.robot_state.end_effector_poses["primary"].as_matrix().copy()
    tool[:3, :3] = Rotation.from_euler("z", 20, degrees=True).as_matrix()
    after = observation(
        stationary.cameras["camera0"].rgb, stationary.cameras["camera0"].depth_m, 1, tool
    )
    result = compare_visual_motion(before, after, masks0, masks1)
    assert result["status"] == "estimated", result
    assert result["evidence"] == "relative_motion_detected"
    assert result["fruit_motion"]["rotation_deg"] < 0.1
    assert result["relative_motion"]["rotation_error_deg"] == pytest.approx(20, abs=0.1)


def test_same_scalar_rotation_about_different_axes_is_relative_motion():
    before, rotated, masks0, masks1, _ = rendered_pair((0, 0, 8))
    tool = before.robot_state.end_effector_poses["primary"].as_matrix().copy()
    tool[:3, :3] = Rotation.from_euler("x", 8, degrees=True).as_matrix()
    after = observation(rotated.cameras["camera0"].rgb, rotated.cameras["camera0"].depth_m, 1, tool)
    result = compare_visual_motion(before, after, masks0, masks1)
    assert result["status"] == "estimated", result
    assert result["fruit_motion"]["rotation_deg"] == pytest.approx(8, abs=1)
    assert result["tool_motion"]["rotation_deg"] == pytest.approx(8, abs=0.1)
    assert result["relative_motion"]["rotation_error_deg"] > 10
    assert result["evidence"] == "relative_motion_detected"


def test_translation_without_rotation_does_not_certify_rotation():
    before, after, masks0, masks1, _ = rendered_pair(
        (0, 0, 0), displacement=np.array([0.002, 0.001, 0])
    )
    result = compare_visual_motion(before, after, masks0, masks1)
    assert result["status"] == "estimated", result
    assert result["evidence"] == "motion_too_small"
    assert result["fruit_motion"]["rotation_deg"] < 0.2
    assert result["fruit_motion"]["displacement_m"] == pytest.approx(np.sqrt(5) / 1000, abs=0.0001)


def test_measurable_translation_certifies_translation_only():
    before, after, masks0, masks1, _ = rendered_pair(
        (0, 0, 0), displacement=np.array([0.006, 0, 0])
    )
    result = compare_visual_motion(before, after, masks0, masks1)
    assert result["evidence"] == "co_motion_consistent", result
    assert result["motion_components"]["translation"] == "co_motion_consistent"
    assert result["motion_components"]["rotation"] == "motion_too_small"


def test_translating_tool_with_static_fruit_reports_slip():
    before, stationary, masks0, masks1, _ = rendered_pair((0, 0, 0))
    tool = stationary.robot_state.end_effector_poses["primary"].as_matrix().copy()
    tool[0, 3] += 0.006
    after = observation(
        stationary.cameras["camera0"].rgb, stationary.cameras["camera0"].depth_m, 1, tool
    )
    result = compare_visual_motion(before, after, masks0, masks1)
    assert result["evidence"] == "relative_motion_detected"


def test_image_motion_with_fixed_robot_reports_slip():
    before, after, masks0, masks1, _ = rendered_pair((0, 0, 8), tool_follows=False)
    result = compare_visual_motion(before, after, masks0, masks1)
    assert result["evidence"] == "relative_motion_detected", result


@pytest.mark.parametrize("condition", ["smooth", "occluded", "no_depth", "tiny_mask"])
def test_missing_visual_information_is_unknown(condition):
    before, after, masks0, masks1, _ = rendered_pair()
    if condition == "smooth":
        first = np.full((160, 160, 3), 120, dtype=np.uint8)
        before = observation(first, np.full((160, 160), 0.4), 0)
        after = observation(first, np.full((160, 160), 0.4), 1)
    elif condition == "occluded":
        masks1["camera0"][:] = False
    elif condition == "no_depth":
        after = observation(after.cameras["camera0"].rgb, np.zeros((160, 160)), 1)
    else:
        masks0["camera0"][:] = False
        masks0["camera0"][76:84, 76:84] = True
    result = compare_visual_motion(before, after, masks0, masks1)
    assert result["status"] == "unknown", result
    assert result["evidence"] == "unknown"
    assert result["fruit_motion"] is None
    assert result["relative_motion"] is None
    assert result["current_time_s"] == 1


def test_matching_same_timestamp_images_are_allowed_but_no_rotation_evidence():
    before, _, masks0, _, _ = rendered_pair()
    result = compare_visual_motion(before, before, masks0, masks0)
    assert result["status"] == "estimated", result
    assert result["evidence"] == "motion_too_small"
    assert result["fruit_motion"]["rotation_deg"] < 0.1


@pytest.mark.parametrize(
    "problem",
    [
        "shape",
        "dtype",
        "camera",
        "mask_frame",
        "time",
        "missing_time",
        "stale_camera",
        "missing_camera_time",
        "missing_robot_time",
        "arm",
    ],
)
def test_invalid_or_stale_inputs_are_rejected(problem):
    before, after, masks0, masks1, _ = rendered_pair()
    kwargs = {}
    if problem == "shape":
        masks0["camera0"] = np.ones((2, 2), bool)
    elif problem == "dtype":
        masks0["camera0"] = masks0["camera0"].astype(float)
    elif problem == "camera":
        masks0 = {"unknown": masks0["camera0"]}
        masks1 = {"unknown": masks1["camera0"]}
    elif problem == "mask_frame":
        masks0["camera0"] = Segmentation(
            mask=masks0["camera0"], label="target", score=1, camera_name="camera0", frame="wrong"
        )
    elif problem == "time":
        before, after = after, before
    elif problem == "missing_time":
        before = replace(before, timestamp_s=None)
    elif problem == "stale_camera":
        before = replace(
            before, cameras={"camera0": replace(before.cameras["camera0"], timestamp_s=3)}
        )
    elif problem == "missing_camera_time":
        before = replace(
            before, cameras={"camera0": replace(before.cameras["camera0"], timestamp_s=None)}
        )
    elif problem == "missing_robot_time":
        before = replace(before, robot_state=replace(before.robot_state, timestamp_s=None))
    else:
        kwargs["arm"] = "missing"
    with pytest.raises(ValueError):
        compare_visual_motion(before, after, masks0, masks1, **kwargs)


def test_rigid_fit_rejects_outliers_and_recovers_full_transform():
    rng = np.random.default_rng(2)
    points = rng.normal(size=(60, 3)) * 0.018 + [0.35, 0.02, 0.25]
    rotation = Rotation.from_euler("xyz", [12, -8, 4], degrees=True).as_matrix()
    translation = np.array([0.03, -0.04, 0.02])
    moved = points @ rotation.T + translation
    moved[:15] = rng.normal(size=(15, 3)) * 0.1
    result = _robust_fit(points, moved)
    assert result is not None
    np.testing.assert_allclose(result[0], rotation, atol=1e-10)
    np.testing.assert_allclose(result[1], translation, atol=1e-10)
    assert result[2].sum() == 45


def test_inconsistent_camera_motion_is_unknown():
    before, moving, masks0, masks1, _ = rendered_pair((0, 0, 8))
    _, opposite, _, opposite_mask, _ = rendered_pair((0, 0, -8))
    before = replace(
        before,
        cameras={
            "camera0": before.cameras["camera0"],
            "camera1": replace(before.cameras["camera0"], frame="camera1"),
        },
    )
    after = replace(
        moving,
        cameras={
            "camera0": moving.cameras["camera0"],
            "camera1": replace(opposite.cameras["camera0"], frame="camera1"),
        },
    )
    masks0["camera1"] = masks0["camera0"].copy()
    masks1["camera1"] = opposite_mask["camera0"]
    result = compare_visual_motion(before, after, masks0, masks1)
    assert result["status"] == "unknown", result
    assert "camera_motion_estimates_disagree" in result["reasons"]


def test_uncertain_stationary_fruit_never_claims_tool_co_rotation(monkeypatch):
    import cap_harness.so101.visual_motion as module

    before, stationary, masks0, masks1, _ = rendered_pair((0, 0, 0))
    tool = before.robot_state.end_effector_poses["primary"].as_matrix().copy()
    tool[:3, :3] = Rotation.from_euler("z", 6, degrees=True).as_matrix()
    after = observation(
        stationary.cameras["camera0"].rgb, stationary.cameras["camera0"].depth_m, 1, tool
    )
    original = module._robust_fit

    def uncertain_fit(*args):
        fit = original(*args)
        return (*fit[:-1], 5.0) if fit else None

    monkeypatch.setattr(module, "_robust_fit", uncertain_fit)
    result = compare_visual_motion(before, after, masks0, masks1)
    assert result["status"] == "estimated"
    assert result["evidence"] in ("unknown", "motion_too_small", "relative_motion_detected")
    assert result["evidence"] != "co_motion_consistent"


def test_pooling_cannot_average_contradictory_views_into_tool_co_motion():
    before, moving, masks0, masks1, _ = rendered_pair((0, 0, 8))
    _, stationary, _, static_mask, _ = rendered_pair((0, 0, 0))
    _, middle, _, _, _ = rendered_pair((0, 0, 4))
    before = replace(
        before,
        cameras={
            "camera0": before.cameras["camera0"],
            "camera1": replace(before.cameras["camera0"], frame="camera1"),
        },
    )
    after = replace(
        middle,
        cameras={
            "camera0": moving.cameras["camera0"],
            "camera1": replace(stationary.cameras["camera0"], frame="camera1"),
        },
    )
    masks0["camera1"] = masks0["camera0"].copy()
    masks1["camera1"] = static_mask["camera0"]
    result = compare_visual_motion(before, after, masks0, masks1)
    assert all(view["status"] == "estimated" for view in result["views"])
    assert result["quality"]["view_agreement_deg"] > 7
    assert result["status"] == "unknown", result
    assert result["evidence"] == "unknown"
    assert "camera_motion_estimates_disagree" in result["reasons"]
