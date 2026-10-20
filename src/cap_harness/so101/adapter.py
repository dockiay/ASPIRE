"""Five-axis SO-101 simulation adapter for public actions and recorded runs."""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType
from typing import Any

import numpy as np

from cap_harness.contracts import (
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

    def _cancel_command_targets(self) -> None:
        env = self._require_env()
        measured = env.sim.data.qpos[env.qpos_indexes].copy()
        env.sim.data.ctrl[env.actuator_ids] = measured
        self._joint_targets["primary"] = measured[:5].copy()
        self._gripper_targets["primary"] = env.opening()

    def native_step(self, action: RobotAction) -> StepResult:
        env = self._require_env()
        if self._last_terminated or self._last_truncated or env.elapsed >= env.horizon:
            self._cancel_command_targets()
            terminated = self._last_terminated
            truncated = self._last_truncated or not terminated
            return StepResult(
                ok=False,
                terminated=terminated,
                truncated=truncated,
                error=self._terminal_error(terminated, truncated),
            )
        if action.embodiment != self.embodiment:
            raise ValueError(
                f"action embodiment {action.embodiment!r} does not match {self.embodiment!r}"
            )
        if set(action.arms) != {"primary"}:
            return StepResult(
                ok=False,
                error=ApiError(ErrorCode.NOT_FOUND, "SO-101 has only the primary arm"),
            )
        # The parent stores accepted goals before encoding. Reject the complete
        # request first, so invalid targets cannot change its pending commands.
        try:
            self._codec.encode(
                action,
                self.get_robot_state(),
                joint_targets=self._joint_targets,
                gripper_targets=self._gripper_targets,
            )
        except (TypeError, ValueError) as exc:
            return StepResult(ok=False, error=ApiError(ErrorCode.INVALID_REQUEST, str(exc)))
        result = super().native_step(action)
        if not result.ok or result.terminated or result.truncated:
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
            camera_calibration={
                "pixel_centers": "integer coordinates; cx=(width-1)/2, cy=(height-1)/2",
                "offsamples": int(env.model.vis.quality.offsamples),
                "depth_clip_near_m": float(env.model.vis.map.znear * env.model.stat.extent),
                "depth_clip_far_m": float(env.model.vis.map.zfar * env.model.stat.extent),
            },
            cartesian_planning_supported=False,
            collision_avoidance=False,
        )
        return MappingProxyType(metadata)
