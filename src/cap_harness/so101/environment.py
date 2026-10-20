"""Host-only SO-101 control task using Robosuite's MuJoCo bindings."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from cap_harness.robosuite.so101_model import build_so101_scene, load_so101_description


class SO101ControlEnvironment:
    camera_target = (0.08, 0, 0.18)
    camera_positions = (("agentview", (-0.50, -0.55, 0.48)), ("sideview", (0.55, 0.50, 0.48)))
    initial_joints = (0, 0, 0, 0, 0)
    depth_clip_near_m = 0.02
    depth_clip_far_m = 5.0
    # Radians/second: retain the original 20 Hz rates at every supported
    # frequency rather than scaling actuator speed with the number of ticks.
    actuator_setpoint_rates_rad_s = (1.0, 1.0, 1.0, 1.0, 1.0, 3.0)

    def __init__(self, *, width: int, height: int, frequency: float, horizon: int) -> None:
        if not np.isfinite(frequency) or frequency <= 0:
            raise ValueError("Control frequency must be positive and finite")
        import mujoco
        from robosuite.utils.binding_utils import MjRenderContextOffscreen, MjSim

        self.description = load_so101_description()
        scene = build_so101_scene(self.description)
        self.configure_scene(scene)
        for name, position in self.camera_positions:
            z_axis = np.asarray(position) - np.asarray(self.camera_target)
            z_axis /= np.linalg.norm(z_axis)
            x_axis = np.cross([0, 0, 1], z_axis)
            x_axis /= np.linalg.norm(x_axis)
            y_axis = np.cross(z_axis, x_axis)
            quat = np.empty(4)
            mujoco.mju_mat2Quat(quat, np.column_stack((x_axis, y_axis, z_axis)).ravel())
            scene.worldbody.add_camera(name=name, pos=position, quat=quat, fovy=45)
        self.model = scene.compile()
        # RGB and metric depth must describe the same integer pixel-center ray.
        # Multisample depth resolution chooses a subpixel depth sample and
        # biases even a flat interior surface when projected with a pinhole K.
        # Use one sample for both images instead of mixing RGB/depth captures.
        self.model.vis.quality.offsamples = 0
        # MuJoCo stores clip distances as factors of the scene extent. The
        # inherited near factor put the depth plane below one millimetre,
        # losing tens of micrometres at the robot even without multisampling.
        # Keep this sensor range metric and independent of plant/scene extent.
        self.model.vis.map.znear = self.depth_clip_near_m / self.model.stat.extent
        self.model.vis.map.zfar = self.depth_clip_far_m / self.model.stat.extent
        self.sim = MjSim(self.model)
        MjRenderContextOffscreen(
            self.sim, device_id=-1, max_width=max(640, width), max_height=max(640, height)
        )
        self.width, self.height = width, height
        self.frequency = frequency
        self.horizon = horizon
        ratio = 1 / (frequency * self.model.opt.timestep)
        if ratio < 1 or not np.isclose(ratio, round(ratio)):
            self.close()
            raise ValueError("Control period must be an integral number of MuJoCo timesteps")
        self.substeps = round(ratio)
        self.joint_ids = np.array(
            [self.model.joint(name).id for name in self.description.scene_joint_names]
        )
        self.qpos_indexes = self.model.jnt_qposadr[self.joint_ids]
        self.qvel_indexes = self.model.jnt_dofadr[self.joint_ids]
        self.actuator_ids = np.array(
            [self.model.actuator(name).id for name in self.description.scene_joint_names]
        )
        limits = self.model.actuator_ctrlrange[self.actuator_ids]
        self.action_spec = (limits[:, 0].copy(), limits[:, 1].copy())
        self.home = np.array(self.initial_joints, dtype=float)
        self.robots = [SimpleNamespace(action_dim=6)]

    def configure_scene(self, scene) -> None:
        """Allow a lesson to add objects before compiling the shared robot model."""

    def opening(self) -> float:
        low, high = self.action_spec
        angle = self.sim.data.qpos[self.qpos_indexes[5]]
        return float(np.clip((angle - low[5]) / (high[5] - low[5]), 0, 1))

    def reset(self) -> dict[str, np.ndarray]:
        self.sim.reset()
        self.elapsed = 0
        self.action_guard = None
        self.action_stop = None
        self.active_command = None
        self.safety_stop = None
        initial = np.append(self.home, self.action_spec[1][5])
        self.sim.data.qpos[self.qpos_indexes] = initial
        self.sim.data.ctrl[self.actuator_ids] = initial
        self.sim.forward()
        self._reset_task_state()
        return self._observation()

    def _reset_task_state(self) -> None:
        self.moved = np.zeros(5, dtype=bool)
        self.returned = np.zeros(5, dtype=bool)
        self.closed_seen = False
        self.reopened_seen = False

    def _observation(self) -> dict[str, np.ndarray]:
        observation = {}
        for name in ("agentview", "sideview"):
            image, depth = self.sim.render(self.width, self.height, camera_name=name, depth=True)
            observation[f"{name}_image"] = image
            observation[f"{name}_depth"] = depth
        return observation

    def step(self, action: np.ndarray):
        if self.safety_stop is not None:
            raise ValueError("Episode stopped: " + self.safety_stop)
        low, high = self.action_spec
        if (
            action.shape != (6,)
            or not np.isfinite(action).all()
            or np.any(action < low)
            or np.any(action > high)
        ):
            raise ValueError("SO-101 actuator targets are invalid or outside limits")
        # Bound the setpoint change per second; these are servo positions,
        # unlike the Panda adapter's delta/velocity controller inputs.
        previous = self.sim.data.ctrl[self.actuator_ids].copy()
        limit = np.asarray(self.actuator_setpoint_rates_rad_s) / self.frequency
        self.sim.data.ctrl[self.actuator_ids] = previous + np.clip(action - previous, -limit, limit)
        for _ in range(self.substeps):
            self.sim.step()
            self._after_physics_step()
            reason = self.action_guard() if self.action_guard else None
            if reason and self.action_stop is None:
                self.action_stop = reason
                self.sim.data.ctrl[self.actuator_ids] = self.sim.data.qpos[self.qpos_indexes]
            if not self.requires_safe_continuation():
                self.sim.data.ctrl[self.actuator_ids] = self.sim.data.qpos[self.qpos_indexes]
        self.sim.forward()
        self.elapsed += 1
        self._after_control_step()
        return (
            self._observation(),
            float(self._check_success()),
            self.elapsed >= self.horizon or self.safety_stop is not None,
            {"safety_stop": self.safety_stop},
        )

    def requires_safe_continuation(self):
        return True

    def _after_physics_step(self) -> None:
        """Lessons with obstacles inspect every physics step, not just rendered frames."""

    def _after_control_step(self) -> None:
        deviation = np.abs(self.sim.data.qpos[self.qpos_indexes[:5]] - self.home)
        self.moved |= deviation >= 0.12
        self.returned |= self.moved & (deviation <= 0.01)
        if self.returned.all() and self.opening() < 0.03:
            self.closed_seen = True
        if self.closed_seen and self.opening() > 0.97:
            self.reopened_seen = True

    def _check_success(self) -> bool:
        deviation = np.abs(self.sim.data.qpos[self.qpos_indexes[:5]] - self.home)
        return bool(
            self.returned.all()
            and self.reopened_seen
            and (deviation <= 0.01).all()
            and self.opening() > 0.97
        )

    def close(self) -> None:
        self.sim.free()
