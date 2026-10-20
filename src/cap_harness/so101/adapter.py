"""Five-axis SO-101 simulation adapter for public actions and recorded runs."""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType
from typing import Any

import numpy as np

from cap_harness.contracts import (
    ArmCommand,
    ExecutionResult,
    RobotAction,
    RobotPlanningContext,
    RobotState,
    StepResult,
)
from cap_harness.errors import ApiError, ErrorCode
from cap_harness.geometry import matrix_to_pose
from cap_harness.robosuite.adapter import RobosuiteAdapter
from cap_harness.so101.codec import SO101ActionCodec
from cap_harness.so101.registry import SO101TaskRegistry


class SO101Adapter(RobosuiteAdapter):
    BASE_FRAME = "so101_base"
    gripper_holds_intermediate = True

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("registry", SO101TaskRegistry())
        super().__init__(**kwargs)
        self.controller = "SO101_ABSOLUTE_POSITION"

    @property
    def embodiment(self) -> str:
        return "so101"

    def _make_environment(self, metadata):
        if self._env_factory is not None:
            return self._env_factory(metadata)
        from cap_harness.so101.environment import SO101ControlEnvironment

        if metadata.task_name != "so101_control":
            raise ValueError("Only the so101_control task is available")
        return SO101ControlEnvironment(
            width=self.camera_width,
            height=self.camera_height,
            frequency=self.control_frequency,
            horizon=self.horizon,
        )

    def _build_codec(self, metadata):
        return SO101ActionCodec(self.action_bounds)

    @staticmethod
    def _arm_has_gripper(robot) -> bool:
        return robot.action_dim == 6

    def _measured_gripper(self, index: int) -> float:
        return self._require_env().opening()

    def _camera_observation(self, name):
        """Match integer pixel rays to SO-101's single-sample OpenGL renderer."""
        camera = super()._camera_observation(name)
        height, width = camera.depth_m.shape
        intrinsics = camera.intrinsics.copy()
        # After the inherited vertical flip, pixel (0, 0) denotes the first
        # sample center. OpenGL's image center is halfway between the central
        # pixels, rather than at the bottom/right central pixel.
        intrinsics[0, 2] = (width - 1) / 2
        intrinsics[1, 2] = (height - 1) / 2
        return replace(camera, intrinsics=intrinsics)

    def get_robot_state(self) -> RobotState:
        env = self._require_env()
        world_from_eef = self._site_transform(env.sim, "so101_gripperframe")
        return RobotState(
            joint_positions={"primary": env.sim.data.qpos[env.qpos_indexes[:5]]},
            joint_velocities={"primary": env.sim.data.qvel[env.qvel_indexes[:5]]},
            end_effector_poses={
                "primary": matrix_to_pose(
                    self._primary_from_world() @ world_from_eef, frame=self.BASE_FRAME
                )
            },
            gripper_positions={"primary": env.opening()},
            joint_names={"primary": env.description.scene_joint_names[:5]},
            base_frame=self.BASE_FRAME,
            timestamp_s=self.current_time_s,
            embodiment=self.embodiment,
        )

    def get_planning_context(self) -> RobotPlanningContext:
        return RobotPlanningContext(
            embodiment=self.embodiment,
            model="so101",
            joint_names={"primary": self.get_robot_state().joint_names["primary"]},
            base_transforms={"primary": np.eye(4)},
            end_effector_links={"primary": "so101_gripper"},
        )

    def ik_request(self, target_pose, state, arm):
        if arm != "primary":
            raise ValueError("SO-101 only has the primary arm")
        return target_pose, state

    def _cancel_command_targets(self, *, keep_issued_gripper=False) -> None:
        """Latch measured arm state in both the servos and shared-command caches."""
        env = self._require_env()
        jaw = float(env.sim.data.ctrl[env.actuator_ids[5]])
        measured = env.sim.data.qpos[env.qpos_indexes].copy()
        env.sim.data.ctrl[env.actuator_ids] = measured
        self._joint_targets["primary"] = measured[:5].copy()
        self._gripper_targets["primary"] = env.opening()
        if keep_issued_gripper:
            env.sim.data.ctrl[env.actuator_ids[5]] = jaw
            self._gripper_targets["primary"] = self.issued_gripper_position()

    def native_step(self, action) -> StepResult:
        env = self._require_env()
        terminal = self._terminal_step_result()
        if terminal is not None:
            return terminal
        if action.embodiment != self.embodiment:
            raise ValueError(
                f"action embodiment {action.embodiment!r} does not match {self.embodiment!r}"
            )
        if set(action.arms) != {"primary"}:
            return StepResult(
                ok=False,
                error=ApiError(ErrorCode.NOT_FOUND, "SO-101 has only the primary arm"),
            )
        target = action.arms["primary"].target
        low, high = self.action_bounds
        if (
            target.shape != (5,)
            or not np.isfinite(target).all()
            or np.any(target < low[:5])
            or np.any(target > high[:5])
        ):
            return StepResult(
                ok=False,
                error=ApiError(
                    ErrorCode.INVALID_REQUEST, "SO-101 joint target exceeds actuator limits"
                ),
            )
        # Validate the complete encoded request before the base adapter commits
        # its accepted goals. Rejected input must never change pending commands.
        try:
            self._codec.encode(
                action,
                self.get_robot_state(),
                joint_targets=self._joint_targets,
                gripper_targets=self._gripper_targets,
            )
        except (TypeError, ValueError) as exc:
            return StepResult(ok=False, error=ApiError(ErrorCode.INVALID_REQUEST, str(exc)))
        if env.action_guard is None:
            env.action_stop = None
        env.active_command = {
            "kind": getattr(self, "_active_kind", "joint_position"),
            "step_index": self._elapsed_steps,
            "arms": {
                name: {"joints_rad": cmd.target.tolist(), "opening": cmd.gripper_position}
                for name, cmd in action.arms.items()
            },
        }
        try:
            result = super().native_step(action)
        except Exception:
            self._cancel_command_targets()
            raise
        if (
            not result.ok
            or result.terminated
            or result.truncated
            or env.action_stop is not None
            or env.safety_stop is not None
        ):
            self._cancel_command_targets()
        return result

    def set_gripper(self, position: float, *, arm: str = "primary") -> ExecutionResult:
        result = super().set_gripper(position, arm=arm)
        if result.ok and abs(self.get_robot_state().gripper_positions[arm] - position) > 0.025:
            return replace(
                result,
                ok=False,
                error=ApiError(ErrorCode.TIMEOUT, "SO-101 gripper did not reach its target"),
            )
        return result

    def get_controller_metadata(self):
        from cap_harness.so101.joint_control import action_limits

        metadata = dict(super().get_controller_metadata())
        env = self._require_env()
        low, high = self.action_bounds
        metadata.update(
            joint_names=self.get_robot_state().joint_names["primary"],
            model_commit=env.description.commit,
            gripper_semantics={
                "normalized": "0=closed angular stop, 1=open angular stop",
                "native": "hinge angle in radians, interpolated between model stops",
                "native_closed_rad": float(low[5]),
                "native_open_rad": float(high[5]),
                "calibration": "simulation model only; not a calibrated LeRobot aperture",
            },
            native_setpoint_rates_rad_s={"arm": 1.0, "jaw": 3.0},
            action_limits=action_limits(),
            supervised_control={
                "sensors": "virtual simulation fingertip contacts; not stock SO-101 hardware",
                "guard_period_s": float(env.model.opt.timestep),
                "force_scope": "requested stop threshold; inertia can overshoot it",
                "completion": "inspect completed and stop_reason; ok may acknowledge a guard stop",
            },
            camera_calibration={
                "pixel_centers": "integer coordinates; cx=(width-1)/2, cy=(height-1)/2",
                "offsamples": int(env.model.vis.quality.offsamples),
                "depth_clip_near_m": float(env.model.vis.map.znear * env.model.stat.extent),
                "depth_clip_far_m": float(env.model.vis.map.zfar * env.model.stat.extent),
            },
            cartesian_planning_supported=True,
            collision_avoidance=True,
            collision_check_scope="sampled robot meshes and public depth points via so101 planner",
            planning_providers={
                "standard_runner": "local so101 IK and bounded RRT-Connect",
                "custom_clients": "use make_api or configure providers explicitly",
                "scope": "observed geometry only; inspect plan diagnostics for limits",
            },
            tcp_approach_axis="+X in so101_gripperframe",
        )
        return MappingProxyType(metadata)

    def get_finger_contacts(self):
        """Read virtual fingertip contact forces; these sensors exist only in simulation."""
        from cap_harness.so101.sensing import read_finger_contacts

        return MappingProxyType(read_finger_contacts(self._require_env()))

    def command_joints(
        self,
        target,
        *,
        duration_s=2.5,
        speed_rad_s=0.2,
        force_limit_n=8.0,
        stop_on_contact_loss=False,
        tolerance_rad=0.003,
        gripper_position=None,
        gripper_speed=0.25,
        minimum_duration_s=0.0,
        arm="primary",
    ):
        from cap_harness.so101.joint_control import command_joints

        return command_joints(
            self,
            target,
            duration_s=duration_s,
            speed_rad_s=speed_rad_s,
            force_limit_n=force_limit_n,
            stop_on_contact_loss=stop_on_contact_loss,
            tolerance_rad=tolerance_rad,
            gripper_position=gripper_position,
            gripper_speed=gripper_speed,
            minimum_duration_s=minimum_duration_s,
            arm=arm,
        )

    def command_gripper(
        self,
        position,
        *,
        duration_s=2.5,
        speed=0.5,
        force_limit_n=8.0,
        stop_on_contact=False,
        arm="primary",
    ):
        """Rate-bounded angular command with substep virtual-force supervision."""

        def invalid(message):
            return ExecutionResult(
                ok=False,
                steps_executed=0,
                error=ApiError(ErrorCode.INVALID_REQUEST, message),
            )

        try:
            inputs = [position, duration_s, speed, force_limit_n]
            if any(isinstance(value, (bool, np.bool_)) or np.ndim(value) != 0 for value in inputs):
                return invalid("Gripper position and limits must be finite numeric scalars")
            position, duration_s, speed, force_limit_n = map(float, inputs)
            if (
                arm != "primary"
                or not np.isfinite([position, duration_s, speed, force_limit_n]).all()
                or not 0 <= position <= 1
                or not 0 < duration_s <= 10
                or not 0 < speed <= 1
                or not 0.1 <= force_limit_n <= 12
                or not isinstance(stop_on_contact, bool)
            ):
                return invalid(
                    "Expected position [0,1], duration_s (0,10], speed (0,1], "
                    "force_limit_n [0.1,12], boolean stop_on_contact; primary arm"
                )
        except (ValueError, TypeError, OverflowError):
            return invalid("Gripper position and limits must be finite numeric scalars")
        env = self._require_env()
        if env.action_guard is not None:
            return invalid("Another action guard is active")
        terminal = self._terminal_step_result()
        if terminal is not None:
            return ExecutionResult(
                ok=False,
                steps_executed=0,
                terminated=terminal.terminated,
                truncated=terminal.truncated,
                error=terminal.error,
            )
        peaks = {"fixed": 0.0, "moving": 0.0}
        env.action_stop = None

        def guard():
            sample = self.get_finger_contacts()
            forces = {side: sample[side]["normal_force_n"] for side in peaks}
            for side, force in forces.items():
                peaks[side] = max(peaks[side], force)
            if any(force >= force_limit_n for force in forces.values()):
                return "force_limit"
            if stop_on_contact and any(force >= 0.1 for force in forces.values()):
                return "contact"
            return None

        result = None
        reason = guard()
        steps = 0
        env.action_guard = guard
        self._active_kind = "gripper"
        try:
            joints = self.get_robot_state().joint_positions[arm]
            command = self.get_robot_state().gripper_positions[arm]
            for _ in range(
                0 if reason is not None else int(np.ceil(duration_s / self.control_period_s))
            ):
                reason = "duration_limit"
                command += float(
                    np.clip(
                        position - command,
                        -speed * self.control_period_s,
                        speed * self.control_period_s,
                    )
                )
                result = self.step(
                    RobotAction(
                        {arm: ArmCommand("joint_position", joints, command, embodiment="so101")}
                    )
                )
                steps += 1
                if not result.ok or result.terminated or result.truncated:
                    reason = env.safety_stop or "episode_terminal"
                    break
                if env.action_stop:
                    reason = env.action_stop
                    break
                if abs(env.opening() - position) <= 0.025 and abs(command - position) <= 0.01:
                    reason = "target_reached"
                    break
        finally:
            env.action_guard = None
            self._active_kind = "joint_position"
            measured = self.get_robot_state().gripper_positions[arm]
            self._cancel_command_targets()
        ok = (
            result is None or (result.ok and not result.terminated and not result.truncated)
        ) and reason in ("target_reached", "contact", "force_limit")
        return ExecutionResult(
            ok=ok,
            steps_executed=steps,
            final_observation=result.observation if result else None,
            terminated=result.terminated if result else False,
            truncated=result.truncated if result else False,
            error=None
            if ok
            else (
                (result.error if result else None)
                or ApiError(ErrorCode.TIMEOUT, "Gripper stopped: " + reason)
            ),
            diagnostics={
                "stop_reason": reason,
                "completed": reason == "target_reached" and ok,
                "peak_finger_forces_n": peaks,
                "measured_opening": measured,
                "target_reached": abs(measured - position) <= 0.025,
                "sensor_source": "virtual simulation contacts",
            },
        )

    def _terminal_step_result(self):
        env = self._require_env()
        if getattr(env, "safety_stop", None) is not None:
            self._cancel_command_targets()
            return StepResult(
                ok=False,
                truncated=True,
                error=ApiError(ErrorCode.ADAPTER_FAILED, "Episode stopped: " + env.safety_stop),
            )
        if (
            self._last_terminated
            or self._last_truncated
            or getattr(env, "elapsed", 0) >= getattr(env, "horizon", self.horizon)
        ):
            self._cancel_command_targets()
            terminated = self._last_terminated
            truncated = self._last_truncated or not terminated
            return StepResult(
                ok=False,
                terminated=terminated,
                truncated=truncated,
                error=self._terminal_error(terminated, truncated),
            )
        return None

    def issued_gripper_position(self, arm="primary") -> float:
        """Instantaneous servo setpoint, distinct from the accepted pending goal."""
        if arm != "primary":
            raise ValueError("SO-101 only has the primary arm")
        env = self._require_env()
        low, high = self.action_bounds
        angle = env.sim.data.ctrl[env.actuator_ids[5]]
        return float(np.clip((angle - low[5]) / (high[5] - low[5]), 0, 1))

    def commanded_gripper_position(self, arm="primary") -> float:
        """Accepted jaw goal, which can still be pending behind the rate limiter.

        Shared arm commands preserve this goal. A supervised bounded segment
        replaces it with its final issued target; cancellation replaces it with
        the measured opening.
        """
        if arm != "primary":
            raise ValueError("SO-101 only has the primary arm")
        self._require_env()
        return self._gripper_targets[arm]

    def planning_workspace(self) -> tuple[np.ndarray, np.ndarray]:
        """Conservative robot-model reach box, expressed in ``so101_base``.

        Every robot geom lies within the sum of its chain's body offsets,
        rotation-anchor displacements, and geom bounding sphere. Joint angles
        cannot increase that triangle-inequality bound. Include all robot
        geoms and the moving jaw, not only the TCP or the current pose.
        This removes unreachable depth background; it is not a task region.
        """
        if not hasattr(self, "_planning_workspace_bounds"):
            from cap_harness.so101.effector import EffectorGeometry

            if not hasattr(self, "_effector_geometry"):
                self._effector_geometry = EffectorGeometry()
            model = self._effector_geometry.robot.model  # robot-only model
            base = model.body(self.BASE_FRAME).id
            chain_radius = {base: 0.0}
            for body in range(base + 1, model.nbody):
                parent = int(model.body_parentid[body])
                if parent not in chain_radius:
                    continue
                extent = float(np.linalg.norm(model.body_pos[body]))
                first = int(model.body_jntadr[body])
                for joint in range(first, first + int(model.body_jntnum[body])):
                    kind = int(model.jnt_type[joint])
                    if kind in (1, 3):  # MuJoCo ball/hinge: rotation about local anchor.
                        extent += 2 * float(np.linalg.norm(model.jnt_pos[joint]))
                    elif kind == 2 and model.jnt_limited[joint]:  # bounded slide
                        reference = model.qpos0[model.jnt_qposadr[joint]]
                        extent += float(np.max(np.abs(model.jnt_range[joint] - reference)))
                    else:
                        raise ValueError("Cannot bound a robot body with unbounded translation")
                chain_radius[body] = chain_radius[parent] + extent
            radius = 0.0
            for geom in range(model.ngeom):
                body = int(model.geom_bodyid[geom])
                if body not in chain_radius:
                    continue
                if int(model.geom_type[geom]) in (0, 1):  # plane or height field
                    raise ValueError("Cannot bound an infinite or terrain geom attached to robot")
                radius = max(
                    radius,
                    chain_radius[body]
                    + float(np.linalg.norm(model.geom_pos[geom]))
                    + float(model.geom_rbound[geom]),
                )
            if not np.isfinite(radius) or radius <= 0:
                raise ValueError("Robot model has no finite positive geometry reach bound")
            # Outward rounding protects the analytical boundary from float rounding.
            upper = np.full(3, np.nextafter(radius, np.inf))
            self._planning_workspace_bounds = (-upper, upper)
        return tuple(bound.copy() for bound in self._planning_workspace_bounds)

    def get_gripper_geometry(self, opening=None):
        from cap_harness.so101.effector import EffectorGeometry

        if not hasattr(self, "_effector_geometry"):
            self._effector_geometry = EffectorGeometry()
        state = self.get_robot_state()
        return self._effector_geometry.describe(
            state.joint_positions["primary"],
            state.gripper_positions["primary"] if opening is None else opening,
        )

    def solve_point_axis_ik(
        self,
        point_in_tool_m,
        target_point_m,
        axis_in_tool,
        target_axis,
        *,
        frame="so101_base",
        arm="primary",
        seed_joints=None,
    ):
        """Robot-only IK on caller-supplied constraints; no simulation motion."""
        from cap_harness.so101.providers import SO101IKProvider

        if not hasattr(self, "_point_axis_ik"):
            self._point_axis_ik = SO101IKProvider()
        return self._point_axis_ik.solve_point_axis_ik(
            point_in_tool_m,
            target_point_m,
            axis_in_tool,
            target_axis,
            self.get_robot_state(),
            frame=frame,
            arm=arm,
            seed_joints=seed_joints,
        )

    def check_joint_path(
        self,
        waypoints,
        obstacle_points_m,
        finger_contact_mask=None,
        margin_m=0.003,
        gripper_positions=None,
    ):
        self.get_gripper_geometry()
        return self._effector_geometry.check_path(
            waypoints,
            obstacle_points_m,
            opening=self.get_robot_state().gripper_positions["primary"],
            openings=gripper_positions,
            finger_contact_mask=finger_contact_mask,
            margin_m=margin_m,
        )
