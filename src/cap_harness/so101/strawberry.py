"""A fixed, known-coordinate strawberry approach lesson; no harvesting physics."""

from __future__ import annotations

import math

import numpy as np

from cap_harness.so101.environment import SO101ControlEnvironment

APPROACH_POSITION = (0.30, 0.0, 0.24)
FRUIT_POSITION = (0.365, 0.0, 0.24)
POSITION_TOLERANCE = 0.008
AXIS_TOLERANCE_DEG = 10.0
HOLD_SECONDS = 0.25


def add_strawberry_plant(
    scene,
    *,
    dynamic_fruit: bool = False,
    contact_dimension: int = 3,
    releasable_junction: bool = False,
) -> None:
    """Compose collidable rigid plant parts and a purely visual target marker."""
    import mujoco

    plant = scene.worldbody.add_body(name="lesson_plant")
    fruit = None
    if dynamic_fruit:
        fruit = scene.worldbody.add_body(name="lesson_fruit", pos=FRUIT_POSITION)
        fruit.add_freejoint(name="fruit_free")
        scene.add_equality(
            name="fruit_fixture",
            type=(mujoco.mjtEq.mjEQ_CONNECT if releasable_junction else mujoco.mjtEq.mjEQ_WELD),
            objtype=mujoco.mjtObj.mjOBJ_BODY,
            name1="lesson_fruit",
            name2="lesson_plant",
            # The retention fixture welds at the fruit. The release proxy uses
            # a local calyx point and permits rotation. Neither is calibrated tissue.
            data=(
                [0, 0, 0.024, 0, 0, 0, 0, 0, 0, 0, 1]
                if releasable_junction
                else [*FRUIT_POSITION, 0, 0, 0, 0, 0, 0, 0, 1]
            ),
            solref=([0.01, 1] if releasable_junction else [0.004, 1]),
            solimp=(
                [0.9, 0.9, 0.001, 0.5, 2] if releasable_junction else [0.999, 0.999, 0.001, 0.5, 2]
            ),
        )

    def geom(name, kind, size, pos=(0, 0, 0), color=(0.12, 0.38, 0.08, 1), **kwargs):
        owner = plant
        if fruit is not None and name.startswith(("fruit", "calyx", "seed")):
            owner = fruit
            pos = np.asarray(pos) - FRUIT_POSITION
            # Declared 20 g rigid fruit, including the tip; decorative parts add no mass.
            kwargs["mass"] = {"fruit": 0.018, "fruit_tip": 0.002}.get(name, 0.0)
            if name in {"fruit", "fruit_tip"}:
                # A light free body needs explicit rigid-contact solver settings;
                # the default 20 ms contact is too compliant for this 20 g object.
                kwargs.update(
                    priority=1,
                    solref=[0.004, 1],
                    friction=[1, 0.005, 0.0001],
                    condim=contact_dimension,
                )
        return owner.add_geom(
            name="plant_" + name, type=kind, size=size, pos=pos, rgba=color, **kwargs
        )

    geom(
        "pot",
        mujoco.mjtGeom.mjGEOM_CYLINDER,
        [0.052, 0.039, 0],
        [0.43, 0.055, 0.034],
        [0.52, 0.24, 0.12, 1],
    )
    geom(
        "soil",
        mujoco.mjtGeom.mjGEOM_CYLINDER,
        [0.048, 0.004, 0],
        [0.43, 0.055, 0.075],
        [0.16, 0.09, 0.035, 1],
    )
    geom(
        "stem",
        mujoco.mjtGeom.mjGEOM_CAPSULE,
        [0.004, 0, 0],
        fromto=[0.43, 0.055, 0.075, 0.43, 0.055, 0.29],
    )
    geom(
        "branch",
        mujoco.mjtGeom.mjGEOM_CAPSULE,
        [0.0025, 0, 0],
        fromto=[0.43, 0.055, 0.29, 0.365, 0, 0.285],
    )
    geom(
        "peduncle",
        mujoco.mjtGeom.mjGEOM_CAPSULE,
        [0.002, 0, 0],
        # Capsule radius is 2 mm. Leave a 1 mm gap above the free fruit's top
        # so its temporary fixture is the only plant support in this lesson.
        fromto=[0.365, 0, 0.285, 0.365, 0, 0.267 if dynamic_fruit else 0.258],
    )
    geom(
        "fruit",
        mujoco.mjtGeom.mjGEOM_ELLIPSOID,
        [0.018, 0.017, 0.024],
        FRUIT_POSITION,
        [0.82, 0.025, 0.045, 1],
    )
    geom(
        "fruit_tip",
        mujoco.mjtGeom.mjGEOM_ELLIPSOID,
        [0.011, 0.010, 0.014],
        [0.365, 0, 0.221],
        [0.82, 0.025, 0.045, 1],
    )
    for index, (pos, angle) in enumerate(
        (
            ((0.454, 0.085, 0.25), 0.7),
            ((0.446, 0.015, 0.285), -0.7),
            ((0.417, 0.095, 0.19), 2.0),
        )
    ):
        geom(
            f"leaf_{index}",
            mujoco.mjtGeom.mjGEOM_ELLIPSOID,
            [0.039, 0.018, 0.003],
            pos,
            [0.08, 0.40 + index * 0.045, 0.10, 1],
            quat=[math.cos(angle / 2), 0, 0, math.sin(angle / 2)],
        )
    for index in range(5):
        angle = index * 2 * math.pi / 5
        geom(
            f"calyx_{index}",
            mujoco.mjtGeom.mjGEOM_ELLIPSOID,
            [0.010, 0.004, 0.002],
            [0.365 + 0.008 * math.cos(angle), 0.008 * math.sin(angle), 0.26],
            quat=[math.cos(angle / 2), 0, 0, math.sin(angle / 2)],
        )
    # Seeds are decoration; all fruit collision is supplied by the two red volumes.
    for row in range(3):
        z = (row - 1) * 0.012
        for index in range(9):
            angle = index * 2 * math.pi / 9 + row * 0.3
            scale = math.sqrt(1 - (z / 0.024) ** 2)
            geom(
                f"seed_{row}_{index}",
                mujoco.mjtGeom.mjGEOM_SPHERE,
                [0.0008, 0, 0],
                [
                    0.365 + 0.018 * scale * math.cos(angle),
                    0.017 * scale * math.sin(angle),
                    0.24 + z,
                ],
                [0.95, 0.70, 0.18, 1],
                contype=0,
                conaffinity=0,
            )
    scene.worldbody.add_site(
        name="approach_target",
        pos=APPROACH_POSITION,
        size=[0.008, 0, 0],
        rgba=[0.04, 0.75, 0.95, 0.5],
    )


class SO101StrawberryApproachEnvironment(SO101ControlEnvironment):
    camera_target = (0.27, 0.01, 0.17)
    camera_positions = (("agentview", (0.68, -0.67, 0.52)), ("sideview", (0.27, 0.78, 0.46)))
    initial_joints = (0.65, -1.219625, 0.744906, 0.474719, 0)

    def configure_scene(self, scene) -> None:
        add_strawberry_plant(scene)

    @staticmethod
    def lesson_metadata() -> dict:
        # Declared exercise inputs, not a detection result or evaluator status.
        return {
            "target_source": "declared_fixed_lesson_coordinates",
            "target_position_m": APPROACH_POSITION,
            "tool_site": "so101_gripperframe",
            "frame": "so101_base",
            "tool_x_direction": (1.0, 0.0, 0.0),
            "position_tolerance_m": POSITION_TOLERANCE,
            "axis_tolerance_deg": AXIS_TOLERANCE_DEG,
            "hold_seconds": HOLD_SECONDS,
            "retreat": "return to initial arm pose with gripper open",
            "scene_variation": "none; seeds repeat the same introductory scene",
        }

    def tool_position(self) -> np.ndarray:
        return self.sim.data.get_site_xpos("so101_gripperframe").copy()

    def _reset_task_state(self) -> None:
        self.initial_tool_position = self.tool_position()
        self.approach_streak = self.retreat_streak = 0
        self.approach_step = self.retreat_step = None
        self.forbidden_contacts: set[tuple[str, str]] = set()
        self.contact_samples = 0
        self.gripper_violation = False
        self.min_target_error = float(np.linalg.norm(self.tool_position() - APPROACH_POSITION))
        self.verified_target_error = None
        self.verified_axis_error = None
        # N endpoint samples span N-1 intervals; the first one is not a held tick.
        self.required_ticks = math.ceil(HOLD_SECONDS * self.frequency) + 1
        self.robot_geoms = set()
        self.obstacle_geoms = set()
        for index in range(self.model.ngeom):
            body = self.model.body(int(self.model.geom_bodyid[index])).name
            name = self.model.geom(index).name
            if body.startswith("so101_"):
                self.robot_geoms.add(index)
            if name.startswith("plant_") or name == "work_surface":
                self.obstacle_geoms.add(index)
        if self.min_target_error < 0.08:
            raise ValueError("Approach lesson must start at least 8 cm from the target")
        self._after_physics_step()

    def _after_physics_step(self) -> None:
        # Contacts from mj_step describe its pre-integration state. Forward again
        # to also inspect the resulting state, including the final physics tick.
        self.sim.forward()
        self.gripper_violation |= self.opening() < 0.97
        touched = False
        for contact in self.sim.data.contact:
            a, b = int(contact.geom1), int(contact.geom2)
            robot_obstacle = (a in self.robot_geoms and b in self.obstacle_geoms) or (
                b in self.robot_geoms and a in self.obstacle_geoms
            )
            robot_self = a in self.robot_geoms and b in self.robot_geoms
            if contact.dist <= 0 and (robot_obstacle or robot_self):
                names = tuple(sorted(self.model.geom(i).name or f"robot_geom_{i}" for i in (a, b)))
                self.forbidden_contacts.add(names)
                touched = True
        self.contact_samples += int(touched)

    def _axis_error(self) -> float:
        rotation = self.sim.data.get_site_xmat("so101_gripperframe")
        return float(np.degrees(np.arccos(np.clip(rotation[0, 0], -1, 1))))

    def _after_control_step(self) -> None:
        error = float(np.linalg.norm(self.tool_position() - APPROACH_POSITION))
        self.min_target_error = min(self.min_target_error, error)
        settled = np.max(np.abs(self.sim.data.qvel[self.qvel_indexes[:5]])) < 0.08
        eligible = not self.forbidden_contacts and not self.gripper_violation and settled
        near = error <= POSITION_TOLERANCE and self._axis_error() <= AXIS_TOLERANCE_DEG
        self.approach_streak = self.approach_streak + 1 if eligible and near else 0
        if self.approach_step is None and self.approach_streak >= self.required_ticks:
            self.approach_step = self.elapsed
            self.verified_target_error = error
            self.verified_axis_error = self._axis_error()
        returned = (
            np.linalg.norm(self.tool_position() - self.initial_tool_position) <= POSITION_TOLERANCE
            and np.max(np.abs(self.sim.data.qpos[self.qpos_indexes[:5]] - self.home)) <= 0.01
        )
        self.retreat_streak = (
            self.retreat_streak + 1
            if self.approach_step is not None and eligible and returned
            else 0
        )
        if self.retreat_step is None and self.retreat_streak >= self.required_ticks:
            self.retreat_step = self.elapsed

    def _check_success(self) -> bool:
        # The final state must still satisfy retreat; an old success is insufficient.
        return bool(
            self.approach_step is not None
            and self.retreat_streak >= self.required_ticks
            and not self.forbidden_contacts
            and not self.gripper_violation
        )

    def task_evidence(self) -> dict:
        """Host-only evidence saved after the generated program has finished."""
        return {
            "task": "so101_strawberry_approach",
            "scope": "fixed-coordinate approach and retreat; no grasp or harvest",
            "task_success": self._check_success(),
            "target_position_m": APPROACH_POSITION,
            "fruit_position_m": FRUIT_POSITION,
            "target_to_fruit_center_m": float(
                np.linalg.norm(np.subtract(FRUIT_POSITION, APPROACH_POSITION))
            ),
            "position_tolerance_m": POSITION_TOLERANCE,
            "minimum_target_error_m": self.min_target_error,
            "verified_target_error_m": self.verified_target_error,
            "verified_axis_error_deg": self.verified_axis_error,
            "final_retreat_error_m": float(
                np.linalg.norm(self.tool_position() - self.initial_tool_position)
            ),
            "approach_verified_step": self.approach_step,
            "retreat_verified_step": self.retreat_step,
            "required_hold_ticks": self.required_ticks,
            "gripper_open_throughout": not self.gripper_violation,
            "forbidden_contact_pairs": sorted(self.forbidden_contacts),
            "contact_samples_with_violation": self.contact_samples,
            "contact_monitor_period_s": float(self.model.opt.timestep),
        }
