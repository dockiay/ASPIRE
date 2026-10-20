"""Rate-bounded arm motion guarded by public virtual fingertip sensors."""

import numpy as np

from cap_harness.contracts import ArmCommand, ExecutionResult, RobotAction
from cap_harness.errors import ApiError, ErrorCode


def action_limits():
    """Fresh public request ranges, distinct from calibrated physical limits."""
    return {
        "scope": "valid request ranges; not calibrated safe forces or task success criteria",
        "command_joints": {
            "duration_s": {"exclusiveMinimum": 0, "maximum": 10},
            "speed_rad_s": {"exclusiveMinimum": 0, "maximum": 1},
            "force_limit_n": {"minimum": 0.1, "maximum": 12},
            "tolerance_rad": {"exclusiveMinimum": 0, "maximum": 0.02},
            "stop_on_contact_loss": {"type": "boolean"},
            "gripper_position": {"minimum": 0, "maximum": 1, "nullable": True},
            "gripper_speed": {"exclusiveMinimum": 0, "maximum": 1},
            "minimum_duration_s": {"minimum": 0, "maximum": 10},
            "target": "five finite radians within public robot actuator limits",
        },
        "command_gripper": {
            "position": {"minimum": 0, "maximum": 1},
            "duration_s": {"exclusiveMinimum": 0, "maximum": 10},
            "speed": {"exclusiveMinimum": 0, "maximum": 1},
            "force_limit_n": {"minimum": 0.1, "maximum": 12},
            "stop_on_contact": {"type": "boolean"},
        },
    }


def command_joints(
    adapter,
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
    """Supervise arm motion with optional simultaneous, rate-limited jaw control.

    A guard stops setpoint advancement; inertia can still overshoot the requested
    force threshold. Native episode constraints always retain priority.
    Without an explicit jaw target the legacy measured-aperture behavior applies.
    Explicit targets persist only after normal completion; every abnormal stop
    cancels them. This is position control, not a force regulator.
    """

    def invalid(message):
        return ExecutionResult(
            ok=False,
            steps_executed=0,
            error=ApiError(ErrorCode.INVALID_REQUEST, message),
        )

    try:
        scalars = [
            duration_s,
            speed_rad_s,
            force_limit_n,
            tolerance_rad,
            gripper_speed,
            minimum_duration_s,
        ]
        if any(isinstance(value, (bool, np.bool_)) or np.ndim(value) != 0 for value in scalars):
            return invalid("Joint command limits must be finite numeric scalars")
        if gripper_position is not None and (
            isinstance(gripper_position, (bool, np.bool_)) or np.ndim(gripper_position) != 0
        ):
            return invalid("Gripper position must be a finite numeric scalar")
        target = np.asarray(target, dtype=float)
        values = np.asarray(
            [
                duration_s,
                speed_rad_s,
                force_limit_n,
                tolerance_rad,
                gripper_speed,
                minimum_duration_s,
            ],
            dtype=float,
        )
        if (
            arm != "primary"
            or target.shape != (5,)
            or not np.isfinite(target).all()
            or not np.isfinite(values).all()
            or not 0 < duration_s <= 10
            or not 0 < speed_rad_s <= 1
            or not 0.1 <= force_limit_n <= 12
            or not 0 < tolerance_rad <= 0.02
            or not isinstance(stop_on_contact_loss, bool)
            or not 0 < gripper_speed <= 1
            or not 0 <= minimum_duration_s <= duration_s
            or (
                gripper_position is not None
                and (
                    isinstance(gripper_position, bool)
                    or not np.isfinite(float(gripper_position))
                    or not 0 <= float(gripper_position) <= 1
                )
            )
        ):
            return invalid(
                "Expected 5 finite joints; duration_s (0,10], speed_rad_s (0,1], "
                "force_limit_n [0.1,12], tolerance_rad (0,0.02], boolean contact guard; "
                "optional gripper_position [0,1], gripper_speed (0,1], "
                "minimum_duration_s [0,duration_s]; primary arm"
            )
    except (ValueError, TypeError, OverflowError):
        return invalid("Joint target and limits must be finite numeric values")
    low, high = adapter.action_bounds
    if np.any(target < low[:5]) or np.any(target > high[:5]):
        return invalid("Joint target exceeds actuator limits")
    env = adapter._require_env()
    if env.action_guard is not None:
        return invalid("Another action guard is active")
    terminal = adapter._terminal_step_result()
    if terminal is not None:
        return ExecutionResult(
            ok=False,
            steps_executed=0,
            terminated=terminal.terminated,
            truncated=terminal.truncated,
            error=terminal.error,
        )
    state = adapter.get_robot_state()
    opening = state.gripper_positions[arm]
    explicit_gripper = gripper_position is not None
    requested_opening = float(gripper_position) if explicit_gripper else opening
    if explicit_gripper:
        # Continue from the issued target, preserving preload across normal
        # segmented motions instead of reinitializing it to the measured jaw.
        opening = adapter.issued_gripper_position(arm)
    start_time = state.timestamp_s
    command = state.joint_positions[arm].copy()
    peaks = {"fixed": 0.0, "moving": 0.0}

    def guard():
        sample = adapter.get_finger_contacts()
        forces = {side: sample[side]["normal_force_n"] for side in peaks}
        for side, force in forces.items():
            peaks[side] = max(peaks[side], force)
        if any(force >= force_limit_n for force in forces.values()):
            return "force_limit"
        if stop_on_contact_loss and not all(force >= 0.1 for force in forces.values()):
            return "contact_lost"
        return None

    reason = guard()
    result = None
    steps = 0
    env.action_stop = None
    env.action_guard = guard
    adapter._active_kind = "guarded_joint_position"
    try:
        if reason is None:
            reason = "duration_limit"
            for _ in range(int(np.ceil(duration_s / adapter.control_period_s))):
                measured = adapter.get_robot_state().joint_positions[arm]
                if (
                    np.max(np.abs(measured - target)) <= tolerance_rad
                    and steps * adapter.control_period_s + 1e-9 >= minimum_duration_s
                    and (not explicit_gripper or steps > 0)
                ):
                    reason = "target_reached"
                    break
                command += np.clip(
                    target - command,
                    -speed_rad_s * adapter.control_period_s,
                    speed_rad_s * adapter.control_period_s,
                )
                opening += float(
                    np.clip(
                        requested_opening - opening,
                        -gripper_speed * adapter.control_period_s,
                        gripper_speed * adapter.control_period_s,
                    )
                )
                result = adapter.step(
                    RobotAction(
                        {
                            arm: ArmCommand(
                                "joint_position",
                                command,
                                opening,
                                embodiment="so101",
                            )
                        }
                    )
                )
                steps += 1
                if not result.ok or result.terminated or result.truncated:
                    reason = env.safety_stop or "episode_terminal"
                    break
                if env.action_stop:
                    reason = env.action_stop
                    break
            else:
                if (
                    np.max(np.abs(adapter.get_robot_state().joint_positions[arm] - target))
                    <= tolerance_rad
                ):
                    reason = "target_reached"
    finally:
        env.action_guard = None
        adapter._active_kind = "joint_position"
        # Arm setpoints always latch measured state. Preserve only the jaw
        # setpoint actually issued on normal completion, never the unexecuted
        # requested target. Guard/timeout/exception/terminal paths cancel both.
        preserve_jaw = (
            explicit_gripper
            and reason == "target_reached"
            and steps > 0
            and env.safety_stop is None
            and env.action_stop is None
        )
        adapter._cancel_command_targets(keep_issued_gripper=preserve_jaw)
    final = adapter.get_robot_state()
    error = result.error if result is not None else None
    terminal = result is not None and (not result.ok or result.terminated or result.truncated)
    ok = not terminal and reason in {"target_reached", "force_limit", "contact_lost"}
    return ExecutionResult(
        ok=ok,
        steps_executed=steps,
        final_observation=result.observation if result is not None else None,
        terminated=result.terminated if result is not None else False,
        truncated=result.truncated if result is not None else False,
        error=None if ok else (error or ApiError(ErrorCode.TIMEOUT, "Arm stopped: " + reason)),
        diagnostics={
            "stop_reason": reason,
            "completed": reason == "target_reached" and not terminal,
            "gripper_mode": "explicit_position" if explicit_gripper else "measured_aperture",
            "requested_gripper_position": gripper_position,
            "retained_gripper_setpoint": adapter._gripper_targets[arm],
            "gripper_setpoint_preserved": preserve_jaw,
            "start_time_s": start_time,
            "end_time_s": final.timestamp_s,
            "peak_finger_forces_n": peaks,
            "target_reached": bool(
                np.max(np.abs(final.joint_positions[arm] - target)) <= tolerance_rad
            ),
            "measured_joints_rad": final.joint_positions[arm].tolist(),
            "measured_opening": final.gripper_positions[arm],
            "sensor_source": "public virtual simulation fingertip sensors; not stock SO-101 hardware",
            "guard_period_s": float(env.model.opt.timestep),
            "scope": "force/contact stop, not grasp verification or a guaranteed force bound; no path certification",
        },
    )
