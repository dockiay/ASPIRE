"""Public RGB-D localization and robot-only approach; truth is used only in tests."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("cv2")
from cap_harness.contracts import CameraObservation, Pose
from cap_harness.so101.vision import localize

ROOT = Path(__file__).resolve().parents[1]


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


@pytest.mark.parametrize("center", [[0, 0, 0.45], [0.015, -0.008, 0.50], [-0.01, 0.01, 0.40]])
def test_metric_fit_tracks_translated_public_images(center):
    estimate = localize(sphere_views(center))
    assert np.linalg.norm(np.array(estimate["point_m"]) - center) < 0.001
    assert estimate["fit_rms_m"] < 0.001


def test_normalized_images_are_supported():
    assert localize(sphere_views([0, 0, 0.45], normalized=True))["ok"]


def test_far_background_depth_on_a_red_edge_is_rejected():
    observation = sphere_views([0, 0, 0.45])
    for name, camera in observation.cameras.items():
        depth = camera.depth_m.copy()
        rows, cols = np.nonzero(camera.rgb[:, :, 0] > 150)
        depth[rows[len(rows) // 2], cols[len(cols) // 2]] = 30
        observation.cameras[name] = replace(camera, depth_m=depth)
    assert np.linalg.norm(localize(observation)["point_m"] - np.array([0, 0, 0.45])) < 0.001


def test_no_motion_target_when_ambiguous_missing_or_uncalibrated():
    with pytest.raises(ValueError, match="unique"):
        localize(sphere_views([-0.03, 0, 0.45], extra=[0.03, 0, 0.45]))
    observation = sphere_views([0, 0, 0.45])
    observation.cameras.pop("sideview")
    with pytest.raises(ValueError, match="Both"):
        localize(observation)
    observation = sphere_views([0, 0, 0.45])
    observation.cameras["sideview"] = replace(observation.cameras["sideview"], timestamp_s=1)
    with pytest.raises(ValueError, match="timestamps"):
        localize(observation)


@pytest.fixture
def adapter(monkeypatch):
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    if not (ROOT / "third_party/fruit_gym/ASPIRE-SOURCE.json").exists():
        pytest.skip("Prepare pinned assets")
    from cap_harness.so101.adapter import SO101Adapter

    # This historical fixture tests the explicit color baseline, not SAM3.
    # Scope it to this test so production campaigns keep their SAM3 requirement.
    monkeypatch.setenv("CAP_HARNESS_SO101_SEGMENTATION", "color-rgbd")
    instance = SO101Adapter(camera_width=640, camera_height=480, horizon=300)
    instance.reset("so101_fruitgym_harvest", 0)
    yield instance
    instance.close()


def test_native_localization_follows_a_moved_fruit_without_model_lookup(adapter):
    first = adapter.localize_ripe_fruit()
    env = adapter.native_env
    before = env.fruit_position()
    delta = np.array([0.015, -0.02, 0.01])
    address = int(env.model.jnt_qposadr[env.fruit_joint_id])
    env.sim.data._data.eq_active[env.fixture_id] = False
    env.sim.data.qpos[address : address + 3] += delta
    env.sim.forward()
    adapter._raw_observation = env._observation()
    second = adapter.localize_ripe_fruit()
    assert np.linalg.norm(np.array(first["point_m"]) - before) < 0.008
    assert np.linalg.norm(np.array(second["point_m"]) - env.fruit_position()) < 0.008
    assert np.linalg.norm(np.array(second["point_m"]) - first["point_m"] - delta) < 0.004


def test_robot_only_kinematics_matches_public_state_and_planning_does_not_move(adapter):
    point = adapter.localize_ripe_fruit()["point_m"]
    before = adapter.get_robot_state()
    plan = adapter.plan_open_approach(point)
    after = adapter.get_robot_state()
    assert np.array_equal(before.joint_positions["primary"], after.joint_positions["primary"])
    assert after.timestamp_s == before.timestamp_s
    assert plan["ik_position_error_m"] < 0.004 and plan["tool_axis_error_deg"] < 5
    assert "not certified" in plan["collision_scope"]
    assert np.max(np.abs(np.diff(plan["waypoints"], axis=0))) <= 0.025 + 1e-9
    with pytest.raises(ValueError, match="workspace"):
        adapter.plan_open_approach([2, 0, 0.2])
    with pytest.raises(ValueError, match="standoff"):
        adapter.plan_open_approach(point, 0.001)


def test_public_policy_reaches_open_standoff_without_contact(adapter, monkeypatch):
    from cap_harness.api import CapApi
    from cap_harness.registry import SO101_PUBLIC_TOOL_NAMES, ToolRegistry
    from cap_harness.runtime import ProgramExecutor

    env = adapter.native_env
    images = env._observation()
    monkeypatch.setattr(env, "_observation", lambda: images)
    registry = CapApi(adapter).register_tools(
        ToolRegistry(public_extension_allowlist=SO101_PUBLIC_TOOL_NAMES)
    )
    execution = ProgramExecutor(registry).execute_program(
        (ROOT / "examples/robosuite/so101_visual_open_approach.py").read_text()
    )
    assert execution.ok, execution.error
    measured = adapter.get_robot_state()
    tcp = measured.end_effector_poses["primary"].position
    assert 0.055 <= np.linalg.norm(env.fruit_position() - tcp) <= 0.075
    assert np.linalg.norm(tcp - execution.result["plan"]["target_position_m"]) < 0.004
    assert measured.gripper_positions["primary"] > 0.97
    assert not env.forbidden_contacts and not env.limit_violations and not env.early_closure
    assert not any(env.current_contacts.values()) and env.detached_time is None
    assert not adapter.check_success()
