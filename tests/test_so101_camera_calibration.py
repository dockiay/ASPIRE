"""Rendered analytic geometry independently checks the SO-101 camera model."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from cap_harness.contracts import Segmentation
from cap_harness.geometry import mask_to_point_cloud
from cap_harness.so101.adapter import SO101Adapter


@pytest.fixture(scope="module", params=["so101_control", "so101_fruitgym_harvest"])
def native_camera_adapter(request):
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    if not (Path(__file__).resolve().parents[1] / "third_party/so_arm100/Simulation/SO101/so101_new_calib.xml").is_file():
        pytest.skip("Run bash scripts/bootstrap_so101.sh")
    adapter = SO101Adapter(camera_width=64, camera_height=48, horizon=10)
    adapter.reset(request.param, 0)
    yield adapter
    adapter.close()


@pytest.mark.parametrize("width,height", [(64, 48), (1280, 960)])
@pytest.mark.parametrize("position", [(0.8, -0.6, 1.2), (-0.55, 0.45, 0.7)])
def test_public_projection_reconstructs_independently_rendered_plane(
    native_camera_adapter, width, height, position
):
    mujoco = pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    from robosuite.utils.binding_utils import MjRenderContextOffscreen, MjSim

    position = np.asarray(position)
    backward = position / np.linalg.norm(position)
    right = np.cross([0, 0, 1], backward)
    right /= np.linalg.norm(right)
    up = np.cross(backward, right)
    quaternion = np.empty(4)
    mujoco.mju_mat2Quat(quaternion, np.column_stack([right, up, backward]).ravel())
    actual_model = native_camera_adapter.native_env.model
    # This plane's true equation is z=0. Expected 3D points come from geometry,
    # not from repeating the production formula for cx/cy or depth conversion.
    # Copy each actual scene's extent and renderer parameters, so tiny near
    # planes and their depth quantization cannot hide behind a synthetic extent.
    xml = f"""
    <mujoco>
      <statistic extent="{actual_model.stat.extent}"/>
      <visual>
        <global offwidth="{width}" offheight="{height}"/>
        <quality offsamples="{actual_model.vis.quality.offsamples}"/>
        <map znear="{actual_model.vis.map.znear}" zfar="{actual_model.vis.map.zfar}"/>
      </visual>
      <worldbody>
        <body name="so101_base"/>
        <geom name="known_plane" type="plane" size="10 10 .01" pos="0 0 0"
              rgba=".6 .7 .8 1"/>
        <camera name="agentview" pos="{" ".join(map(str, position))}"
                quat="{" ".join(map(str, quaternion))}" fovy="45"/>
      </worldbody>
    </mujoco>
    """
    model = mujoco.MjModel.from_xml_string(xml)
    sim = MjSim(model)
    MjRenderContextOffscreen(sim, device_id=-1, max_width=width, max_height=height)
    try:
        sim.forward()
        image, depth = sim.render(width, height, camera_name="agentview", depth=True)
        adapter = SO101Adapter()
        adapter._env = SimpleNamespace(sim=sim)
        adapter._raw_observation = {"agentview_image": image, "agentview_depth": depth}
        camera = adapter._camera_observation("agentview")
        selected = np.zeros((height, width), dtype=bool)
        selected[4:-4:5, 4:-4:5] = True
        cloud = mask_to_point_cloud(
            camera,
            Segmentation(selected, "analytic plane", 1.0, "agentview", camera.frame),
            target_frame="so101_base",
        )
        # Express the tolerance in physical image resolution. GPU depth
        # rasterization has a finite precision floor, particularly at 64x48;
        # requiring identical micrometre residuals at every resolution is not
        # a portable camera contract. Allow 1% of a pixel footprint, then prove
        # that the half-pixel calibration error still fails the same criterion.
        footprint = 2 * np.min(camera.depth_m[selected]) * np.tan(np.deg2rad(45 / 2)) / height
        tolerance = 0.01 * footprint
        assert np.max(np.abs(cloud.points[:, 2])) < tolerance
        incorrect_intrinsics = camera.intrinsics.copy()
        incorrect_intrinsics[:2, 2] += 0.5
        incorrect = mask_to_point_cloud(
            replace(camera, intrinsics=incorrect_intrinsics),
            Segmentation(selected, "analytic plane", 1.0, "agentview", camera.frame),
            target_frame="so101_base",
        )
        assert np.sqrt(np.mean(incorrect.points[:, 2] ** 2)) > 10 * tolerance
        # The override must preserve the parent adapter's images and transforms.
        np.testing.assert_array_equal(camera.rgb, image[::-1])
        np.testing.assert_allclose(camera.camera_pose.position, position)
        assert camera.frame == "camera/agentview"
        assert camera.camera_pose.frame == "so101_base"
    finally:
        sim.free()


def test_sensor_parameters_and_public_intrinsics_match(native_camera_adapter):
    adapter = native_camera_adapter
    observation = adapter.get_observation()
    metadata = adapter.get_controller_metadata()
    calibration = metadata["camera_calibration"]
    assert calibration["depth_clip_near_m"] == pytest.approx(0.02)
    assert calibration["depth_clip_far_m"] == pytest.approx(5.0)
    assert calibration["offsamples"] == 0
    for camera in observation.cameras.values():
        np.testing.assert_allclose(camera.intrinsics[:2, 2], [31.5, 23.5])
        assert camera.depth_m.shape == (48, 64)
        assert camera.camera_pose.frame == "so101_base"
    assert adapter.current_time_s == 0


def test_current_scene_sensor_range_contains_conservative_robot_reach(native_camera_adapter):
    adapter = native_camera_adapter
    observation = adapter.get_observation()
    model = adapter.native_env.model
    near = float(model.vis.map.znear * model.stat.extent)
    far = float(model.vis.map.zfar * model.stat.extent)
    assert near == pytest.approx(0.02)
    assert far == pytest.approx(5.0)
    assert model.vis.quality.offsamples == 0
    reach_radius = adapter.planning_workspace()[1][0]
    for camera in observation.cameras.values():
        np.testing.assert_allclose(camera.intrinsics[:2, 2], [31.5, 23.5])
        assert camera.depth_m.shape == (48, 64)
        assert camera.camera_pose.frame == "so101_base"
        forward = camera.camera_pose.as_matrix()[:3, 2]
        base_depth = -float(camera.camera_pose.position @ forward)
        assert base_depth - reach_radius > near
        assert base_depth + reach_radius < far
    assert adapter.current_time_s == 0


@pytest.mark.parametrize(
    "task,seed", [("so101_strawberry_detachment", 0), ("so101_strawberry_detachment_cases", 101)]
)
def test_legacy_detachment_initial_finite_geometry_is_within_sensor_depth_range(task, seed):
    mujoco = pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    adapter = SO101Adapter(camera_width=64, camera_height=48, horizon=10)
    try:
        adapter.reset(task, seed)
        model, sim = adapter.native_env.model, adapter.native_env.sim
        near = float(model.vis.map.znear * model.stat.extent)
        far = float(model.vis.map.zfar * model.stat.extent)
        for camera in range(model.ncam):
            forward = -sim.data.get_camera_xmat(model.camera(camera).name)[:, 2]
            origin = sim.data.get_camera_xpos(model.camera(camera).name)
            for geom in range(model.ngeom):
                if model.geom_type[geom] in (
                    mujoco.mjtGeom.mjGEOM_PLANE,
                    mujoco.mjtGeom.mjGEOM_HFIELD,
                ):
                    continue
                center_depth = float((sim.data.geom_xpos[geom] - origin) @ forward)
                radius = float(model.geom_rbound[geom])
                assert center_depth - radius > near
                assert center_depth + radius < far
        # This proves the initial finite geometry only. These older close
        # cameras do not contain the entire robot-reach sphere at every pose.
        assert adapter.current_time_s == 0
    finally:
        adapter.close()
