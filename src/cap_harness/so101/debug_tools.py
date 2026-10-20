"""Audited, development-only tools for a Codex SO-101 fix-loop agent."""

from __future__ import annotations

import ast
from collections.abc import Mapping
import contextlib
import dataclasses
import hashlib
import io
from pathlib import Path
import re
import sys

from cap_harness.so101 import campaign as c
from cap_harness.so101 import strategy_search
from cap_harness.so101.learning import feedback_for, validate_program
from cap_harness.so101.paths import workspace_root

ROOT = workspace_root()
SCHEMA = "so101-iterative-agent-v1"
CAMERAS = ("agentview", "sideview")
TOOLS = (
    "describe_task",
    "explore_scene",
    "execute_program",
    "inspect_results",
    "view_frame",
    "finish_session",
)
PROFILE = ROOT / ".claude/skills/iterative-debugging/so101"


def runtime_identity(env, suite):
    value = c.runtime_identity(env)
    from cap_harness.so101.perception import runtime_identity as perception_identity

    value["perception"] = perception_identity(suite, env)
    if suite == "so101_fruitgym_harvest":
        from cap_harness.so101.harvest_protocol import resource_identity

        value["task_resources"] = resource_identity()
    return value


def task_metadata(suite):
    from cap_harness.so101.registry import SO101TaskRegistry

    return SO101TaskRegistry().resolve(suite)


def public_json(value):
    if dataclasses.is_dataclass(value):
        return {f.name: public_json(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {str(k): public_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [public_json(v) for v in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def initial_public_snapshot(identity):
    """No stepping, native object lookup or privileged evaluator evidence."""
    from cap_harness.so101.adapter import SO101Adapter

    limits = identity["limits"]
    adapter = SO101Adapter(
        camera_width=limits["width"], camera_height=limits["height"], horizon=limits["max_steps"]
    )
    try:
        task = task_metadata(identity["suite"])
        adapter.reset(task, identity["seeds"][0])
        observation = adapter.get_observation()
        metadata = {
            "task_language": task.language,
            "robot_state": public_json(adapter.get_robot_state()),
            "task_metadata": public_json(adapter.get_task_metadata()),
            "controller_metadata": public_json(adapter.get_controller_metadata()),
            "finger_contacts": public_json(adapter.get_finger_contacts()),
            "simulation_steps": 0,
        }
        return metadata, {
            name: camera.rgb for name, camera in observation.cameras.items() if name in CAMERAS
        }
    finally:
        adapter.close()


def png_bytes(rgb):
    from PIL import Image

    buffer = io.BytesIO()
    Image.fromarray(rgb).save(buffer, format="PNG")
    return buffer.getvalue()


def public_approach_report(run):
    """Bounded policy self-report, explicitly separate from physical scoring."""
    relative = "source/program-result.json"
    indexed = {row["path"] for row in c.read_json(run / "manifest.json")["files"]}
    if relative not in indexed:
        return None
    value = c.read_json(run / relative).get("result")
    if not isinstance(value, dict):
        return None
    report = {"scope": "policy self-report from public APIs; not physical verification"}
    for name, keys in {
        "localization": ("point_m", "frame", "timestamp_s", "fit_radius_m", "fit_rms_m", "views"),
        "plan": (
            "target_position_m",
            "clearance_m",
            "ik_position_error_m",
            "tool_axis_error_deg",
            "collision_scope",
        ),
    }.items():
        if isinstance(value.get(name), dict):
            report[name] = {key: value[name][key] for key in keys if key in value[name]}
    for key in ("final_tcp_m", "final_opening"):
        if key in value:
            report[key] = value[key]
    import json

    return (
        report
        if len(json.dumps(report)) <= 8000
        else {"scope": "policy report omitted: size limit"}
    )


def build_identity(seeds, limits, runtime, max_programs=4, max_calls=48, *, suite=c.SUITE):
    base = c.build_identity(
        {"probe": b"result = None\n"}, "development", seeds, limits, runtime, suite=suite
    )
    if type(max_programs) is not int or not 1 <= max_programs <= 20:
        raise ValueError("max-programs must be between 1 and 20")
    if type(max_calls) is not int or not 1 <= max_calls <= 200:
        raise ValueError("max-calls must be between 1 and 200")
    return {
        "schema": SCHEMA,
        "suite": suite,
        "feedback_review_version": 1,
        "partition": "development",
        "seeds": [row["seed"] for row in base["cases"]],
        "limits": limits,
        "protocol_sha256": base["protocol_sha256"],
        "runtime": runtime,
        "max_programs": max_programs,
        "max_calls": max_calls,
        "selection_rule": "Max task_success then program_ok; earliest on ties",
        "provenance_audit": "PENDING; no canonical promotion or verified skill",
        "profile_files": {
            name: c.file_sha(PROFILE / name) for name in ("SKILL.md", "agent-prompt.md")
        },
    }


def initialize(root, identity):
    root = Path(root).resolve()
    with c.campaign_lock(root):
        manifest = root / "session.json"
        if manifest.exists():
            if c.read_json(manifest) != identity:
                raise ValueError("Agent session identity changed; use another output directory")
        else:
            if any(p.name != ".lock" for p in root.iterdir()):
                raise ValueError("Agent output must be empty")
            c.write_json(manifest, identity)
            c.write_json(root / "inputs/protocol.json", c.protocol_for(identity["suite"]))
            for name in identity["profile_files"]:
                path = root / "inputs" / name
                path.write_bytes((PROFILE / name).read_bytes())
        if (
            c.canonical_sha256(c.read_json(root / "inputs/protocol.json"))
            != identity["protocol_sha256"]
        ):
            raise ValueError("Agent protocol snapshot was modified")
        for name, digest in identity["profile_files"].items():
            if c.file_sha(root / "inputs" / name) != digest:
                raise ValueError("Agent profile snapshot was modified")
    return root


class DebugTools:
    def __init__(
        self,
        root,
        *,
        snapshot=initial_public_snapshot,
        run_campaign=c.run_campaign,
        runtime_check=True,
    ):
        self.root = Path(root).resolve()
        self.identity = c.read_json(self.root / "session.json")
        self.env = c.child_environment(self.identity["runtime"]["environment"]["MUJOCO_GL"])
        self.snapshot = snapshot
        self.run_campaign = run_campaign
        self.runtime_check = runtime_check

    def check_runtime(self):
        if (
            self.runtime_check
            and runtime_identity(self.env, self.identity["suite"]) != self.identity["runtime"]
        ):
            raise ValueError("Agent runtime changed; start a new session")

    def scored_summary(self, directory, summary):
        spec = self.identity.get("verification_contract")
        if spec is None:
            return summary
        from cap_harness.so101 import skill_contracts

        if spec != skill_contracts.contract(spec["id"]):
            raise ValueError("Skill verification criterion changed")
        return skill_contracts.enrich(directory, summary, spec["id"])

    def candidate(self, candidate_id):
        if not isinstance(candidate_id, str) or not re.fullmatch(r"c-[0-9a-f]{16}", candidate_id):
            raise ValueError("Invalid candidate ID")
        directory = self.root / "candidates" / candidate_id
        if not (directory / "submission.json").is_file():
            raise ValueError("Unknown candidate ID")
        submission = c.read_json(directory / "submission.json")
        if c.file_sha(directory / "program.py") != submission["program_sha256"]:
            raise ValueError("Candidate code was modified")
        return directory, submission

    def audit_images(self, metadata):
        for row in metadata["images"]:
            path = (self.root / row["path"]).resolve()
            if not path.is_relative_to(self.root) or c.file_sha(path) != row["sha256"]:
                raise ValueError("Recorded image was modified")

    def perception_contract(self):
        from cap_harness.so101.perception import configuration

        config = self.identity["runtime"].get("perception") or configuration(self.identity["suite"])
        source = (
            "SAM3 semantic image segmentation with text/point prompts; no color fallback. "
            "Use descriptive text such as strawberry, leaf or container. Confidence is model score, not calibrated correctness. "
            "The legacy color-only so101.localize_ripe_fruit is disabled. "
            if config["backend"] == "sam3"
            else "Explicit color-rgbd baseline, NOT SAM3. Queries red, red strawberry, ripe red strawberry, blue, blue container, blue tray, green, green foliage. The optional so101.localize_ripe_fruit is a dual-view red-color estimate. "
        )
        return source + (
            "segment_text returns ok, segmentations (mask, score, camera identity), error. "
            "Inspect ambiguity and both views before selecting a mask. mask_to_point_cloud uses public calibrated depth; "
            "It accepts explicit erosion_pixels (0 default, at most 8) and depth_range_m=[near, far] in camera-axis metres. "
            "These optional filters leave the raw SAM3 mask unchanged; choose margins/range from stated sensor or engineering limits. "
            "localize_object uses unfiltered projection by default; use the atomic tools when filtering is required. "
            "A silhouette/background depth return can make a PCA box unusable; inspect dispersion and other views. "
            "estimate_geometry returns visible-surface estimates, never complete shape or native object pose. "
            "localize_object uses the FIRST segmentation only and returns ok, geometry, point_cloud, error; "
            "geometry has pose (position, quaternion_wxyz, frame) and extents; point_cloud has points and frame. "
            "Occlusion, missing depth and no detection are observable failures. Fresh image inference has no persistent object ID."
        )

    def describe_task(self):
        from cap_harness.so101.joint_control import action_limits
        from cap_harness.so101.skill_contracts import catalog

        return {
            "schema": SCHEMA,
            "task": self.identity["suite"],
            "language": task_metadata(self.identity["suite"]).language,
            "case_scope": c.protocol_for(self.identity["suite"]).get(
                "scope", "Synthetic detachment cases"
            ),
            "partition": "development",
            "skill_verification_contracts": catalog(),
            "active_skill_contract": self.identity.get("verification_contract"),
            "case_count": len(self.identity["seeds"]),
            "max_programs": self.identity["max_programs"],
            "max_calls": self.identity["max_calls"],
            **(
                {
                    "search_protocol": self.identity["search_protocol"],
                    "search_instructions": strategy_search.instructions(
                        self.identity["search_protocol"]
                    ),
                }
                if self.identity.get("search_protocol")
                else {}
            ),
            "max_per_failure_mode": self.identity.get("max_per_failure_mode"),
            "selection_rule": self.identity["search_protocol"]["selection"]
            if self.identity.get("search_protocol")
            else "maximize skill_success, then program_ok; minimize AST size, then prefer earlier submission"
            if self.identity.get("verification_contract")
            else (
                "maximize task_success, then program_ok; minimize AST size, then prefer earlier submission"
                if self.identity.get("tie_breaker") == "ast_size"
                else self.identity["selection_rule"]
            ),
            "limits": self.identity["limits"],
            "cameras": list(CAMERAS),
            "provenance_audit": self.identity["provenance_audit"],
            "workflow": "Explore once; generate without a prior program; execute on all assigned development cases; inspect and view frames before revising. No held-out or evaluator access.",
            "public_policy_api": [
                "get_task_context()",
                "get_robot_state()",
                "get_observation()",
                "step(RobotAction({'primary': ArmCommand('joint_position', joints, gripper_position=opening, embodiment='so101')}))",
                "move_to_joints(target, tolerance=0.003, max_steps=100)",
                "so101.get_task_metadata()",
                "so101.get_controller_metadata()",
                "so101.get_finger_contacts()",
                "so101.get_gripper_geometry(opening=None)",
                "so101.command_gripper(position, duration_s=2.5, speed=0.5, force_limit_n=8.0, stop_on_contact=False)",
                "so101.command_joints(target, duration_s=2.5, speed_rad_s=0.2, force_limit_n=8.0, stop_on_contact_loss=False, tolerance_rad=0.003, gripper_position=None, gripper_speed=0.25, minimum_duration_s=0.0, arm='primary')",
                "so101.check_joint_path(waypoints, obstacle_points_m, finger_contact_mask=None, margin_m=0.003, gripper_positions=None)",
                "so101.solve_point_axis_ik(point_in_tool_m, target_point_m, axis_in_tool, target_axis, frame='so101_base', arm='primary', seed_joints=None)",
                "so101.compare_visual_motion(before, after, masks_before, masks_after, arm='primary')",
                "so101.localize_ripe_fruit()",
                "segment_text(camera_name, text)",
                "segment_points(camera_name, points_px): one positive [[x, y]] prompt with SAM3",
                "mask_to_point_cloud(mask, camera_name, target_frame=None, erosion_pixels=0, depth_range_m=None): omitted frame resolves to this robot's so101_base",
                "estimate_geometry(point_cloud)",
                "generate_grasps(camera_name, mask, backend=None, max_candidates=5): default so101-geometric; geometric proposals, not verified grasps",
                "select_grasp(grasps, strategy='top_down'): SO-101 approach axis is TCP +X; highest_score also available",
                "plan_motion(goal, start_joints=None, arm='primary', strategy=None, target_point_cloud=None): default SO-101 observed-obstacle trajectory search",
                "execute_trajectory(trajectory): executes a successful plan; inspect result and physical evidence",
                "localize_object(query, camera_name='agentview', target_frame='so101_base')",
                "solve_ik(target_pose, seed_joints=None, arm='primary', backend=None)",
                "move_to_pose(target_pose, tolerance=0.01, max_steps=120)",
                "set_gripper(position)",
                "open_gripper()",
                "close_gripper()",
            ],
            "public_contract": {
                "injected_types": ["RobotAction", "ArmCommand", "Pose", "MotionStrategy"],
                "robot_state": "state.joint_positions['primary'] is a five-element array; state.gripper_positions['primary'] is normalized 0=closed, 1=open; state.timestamp_s is measured simulation time",
                "step_result": "Check motion.ok and motion.truncated; no reward or success fields",
                "contacts": "timestamp_s and fixed/moving dictionaries with normal_force_n, contact_count, contacts; each contact has local_position_m in the gripper frame",
                "effector": "TCP is near the fixed fingertip, NOT between symmetric fingers. get_gripper_geometry(opening) returns pads (surface_center_m, surface_bounds_m), grasp_center_in_tcp_m, closing_direction_in_tcp, and approximate pad_center_separation_m in TCP. The moving jaw rotates; transform geometry with the measured TCP pose. Width is an approximate surface span, not guaranteed clearance. command_gripper checks virtual contacts each physics substep, controls normalized speed and returns stop_reason, peaks, measured_opening, target_reached. A force/contact stop can be ok without reaching width. All action results and terminal states must be checked; unrecoverable scene violations stop the episode.",
                "control_frequency_hz": 20,
                "action_limits": action_limits(),
                "guarded_arm": "command_joints rate-limits arm setpoints. gripper_position=None holds initial measured aperture. An explicit gripper_position [0,1] controls the jaw simultaneously at gripper_speed; minimum_duration_s allows supervised holding even when the arm already reached target. Normal completion preserves the last issued explicit jaw setpoint, not an unexecuted request. Guards/timeouts/native violations cancel native and cached arm/jaw targets. Shared motion preserves an accepted pending jaw target; this differs from the instantaneous rate-limited servo target. This is position control, not force regulation. Forces are checked before motion and every physics substep; contact loss requires both tips >=0.1N and does not identify the object. Inspect completed AND stop_reason; ok/target_reached may coexist with contact_lost. Inertia can overshoot force limits. Does not certify path or grasp; sensors are virtual.",
                "path_validation": "so101.check_joint_path checks joint limits, self/work-plane contacts and robot-mesh convex hulls against PUBLIC base-frame point samples. finger_contact_mask permits selected target points only within distal pad bounds, not whole fingers. gripper_positions supplies one opening per waypoint and checks jaw sweep. observed_clearance is a margin violation, not proof of contact. Sampled clearance cannot certify occluded geometry or gaps between samples.",
                "point_axis_ik": "so101.solve_point_axis_ik maps a point and nonzero direction fixed in the TCP frame to a caller-supplied base-frame point and direction, leaving rotation about that direction unconstrained. Returns IKResult, with point_error_m and axis_error_deg; acceptance 0.5 mm / 1 degree. Uses current measured opening and current joints or supplied seed_joints. It only computes joints; it does not move, predict grasp/fruit motion or validate path/collisions. All constraints must be derived from public observations. Existing solve_ik still requires the complete requested pose.",
                "perception": self.perception_contract(),
                "visual_motion": "compare_visual_motion consumes timestamped public observations and fresh caller-selected SAM3 masks without intervening motion. It tracks RGB texture with calibrated depth and compares the surface transform with measured tool motion. status is estimated/unknown; evidence is co_motion_consistent, relative_motion_detected, motion_too_small or unknown. motion_components distinguishes rotation from translation: successful translation does not establish rotation. Uncertainty values are heuristics, not calibrated confidence. Unknown is not zero motion or success. Branch on results during manipulation; a final print is diagnostic only. Object identity and mask freshness remain caller responsibilities. No native object poses, assets or task state are read. Camera images, masks, timestamps and measurements are recorded.",
                "motion": "Default IK and trajectory backends are so101. plan_motion/move_to_pose compose five-axis IK with bounded observed-obstacle path search using public RGB-D and the robot model. It can reject blocked/unreachable scenes; never silently falls back to unchecked interpolation. Inspect planner diagnostics: observed-only collision checks cannot certify unseen space or actual servo tracking. target_point_cloud keeps target samples as obstacles and permits only distal pad contact within 1 mm of those samples; the caller must identify that intended contact target from current vision. Other finger/arm surfaces and surrounding obstacles remain checked. Explicit MotionStrategy(ik_solver='so101', trajectory_planner='interpolation') remains an unchecked alternative, collision_aware=False. move_to_joints and command_joints do not automatically plan around obstacles. Five axes cannot realize arbitrary 6D poses; incompatible orientation returns IK_FAILED. Pose uses quaternion WXYZ and so101_base; TCP +X is forward.",
                "grasp_proposals": "generate_grasps defaults to so101-geometric: bounded geometry-based proposals from public target/scene clouds, angular-jaw robot geometry and public measured state. Candidate pose is the reachable TCP, not fruit center. Inspect metadata for opening, joint target and pregrasp. Proposal scores are heuristic, not probabilities or proof of grasp. Plan and check approach, then observe actual contacts; no supplied harvesting policy or Contact-GraspNet service is implied.",
                "syntax": "Runtime injects public functions and types. Only import math without aliases. No classes, with, async, global or nonlocal. Loops must be bounded. Optional result dictionary.",
            },
            "program_rules": "Only import math, no names/attributes beginning with underscore. No native state, reward, object geometry assets, seed branches or copied observed targets as constants. Derive targets at runtime via public APIs. Autonomous workers must compose general primitives: legacy so101.plan_open_approach is reserved for approach-only demonstrations. No harvesting program, waypoints or phase recipe is supplied.",
            **(
                {"legacy_stage_api": "so101.plan_open_approach(fruit_point_m, clearance_m=0.065)"}
                if self.identity.get("approach_only")
                else {}
            ),
        }, []

    def explore_scene(self):
        path = self.root / "exploration/snapshot.json"
        if not path.exists():
            self.check_runtime()
            with contextlib.redirect_stdout(sys.stderr):
                public, cameras = self.snapshot(self.identity)
            if set(cameras) != set(CAMERAS):
                raise ValueError("Public snapshot must contain both cameras")
            images = []
            for name, rgb in cameras.items():
                image_path = self.root / "exploration" / f"{name}.png"
                image_path.parent.mkdir(parents=True, exist_ok=True)
                image_path.write_bytes(png_bytes(rgb))
                images.append(
                    {
                        "camera": name,
                        "path": str(image_path.relative_to(self.root)),
                        "sha256": c.file_sha(image_path),
                        "time_s": 0.0,
                    }
                )
            c.write_json(path, {"public": public, "images": images})
        metadata = c.read_json(path)
        self.audit_images(metadata)
        return {
            "public": metadata["public"],
            "images": metadata["images"],
            "source": "public SO101Adapter observation at first assigned development case, zero control ticks",
        }, [self.root / row["path"] for row in metadata["images"]]

    def execute_program(self, code, hypothesis, provenance):
        if not (self.root / "exploration/snapshot.json").exists():
            raise ValueError("Explore the initial public scene before submitting a program")
        for name, value, maximum in (
            ("code", code, 64000),
            ("hypothesis", hypothesis, 4000),
            ("provenance", provenance, 8000),
        ):
            if not isinstance(value, str) or not value.strip() or len(value.encode()) > maximum:
                raise ValueError(f"{name} must be nonempty and bounded")
        digest = hashlib.sha256(code.encode()).hexdigest()
        candidate_id = "c-" + digest[:16]
        directory = self.root / "candidates" / candidate_id
        if not directory.exists() and self.identity.get("enforce_debug_sequence"):
            for prior_path in (self.root / "candidates").glob("*/result.json"):
                if not (prior_path.parent / "inspected.json").exists():
                    raise ValueError(
                        "Inspect each previous candidate before proposing a correction"
                    )
        if directory.exists():
            _, prior = self.candidate(candidate_id)
            if prior["program_sha256"] != digest:
                raise ValueError("Candidate ID collision")
            if self.identity.get("search_protocol") and (
                prior["hypothesis"] != hypothesis or prior["provenance"] != provenance
            ):
                raise ValueError("Cached candidate strategy/provenance cannot be rewritten")
        else:
            failure_mode = "initial"
            previous = sorted(
                (c.read_json(p) for p in (self.root / "candidates").glob("*/submission.json")),
                key=lambda row: row["order"],
            )
            if previous:
                last_path = self.root / "candidates" / previous[-1]["candidate_id"] / "result.json"
                prior_result = c.read_json(last_path)
                findings = prior_result.get("comparison", {}).get("findings", {})
                failure_mode = (
                    max(findings, key=findings.get) if findings else prior_result["status"]
                )
            budget = self.identity.get("max_per_failure_mode")
            if budget and sum(p.get("failure_mode") == failure_mode for p in previous) >= budget:
                raise ValueError(
                    "Failure-mode budget exhausted: "
                    + failure_mode
                    + "; finish with measured evidence"
                )
            count = len(list((self.root / "candidates").glob("*/submission.json")))
            if count >= self.identity["max_programs"]:
                raise ValueError("Program budget exhausted; no new candidate accepted")
            strategy = None
            if self.identity.get("search_protocol"):
                strategy = strategy_search.descriptor(
                    self.identity["search_protocol"], hypothesis, code, previous, self.root
                )
                for prior_path in (self.root / "candidates").glob("*/submission.json"):
                    prior_id = prior_path.parent.name
                    if (
                        not list((self.root / "frames").glob(f"{prior_id}-*.json"))
                        and c.read_json(prior_path.parent / "result.json")["status"] == "recorded"
                    ):
                        raise ValueError(
                            "View an audited frame of every prior recorded strategy before proposing another"
                        )
            directory.mkdir(parents=True)
            (directory / "program.py").write_bytes(code.encode())
            c.write_json(
                directory / "submission.json",
                {
                    "candidate_id": candidate_id,
                    "program_sha256": digest,
                    "order": count,
                    "hypothesis": hypothesis,
                    "provenance": provenance,
                    "provenance_audit": "PENDING",
                    "source": "agent-generated; no baseline supplied",
                    "failure_mode": failure_mode,
                    **({"search_strategy": strategy} if strategy is not None else {}),
                },
            )
        if (directory / "result.json").exists():
            return self.inspect_results(candidate_id, mark=False)
        try:
            validate_program(code)
            if not self.identity.get("approach_only"):
                if any(
                    isinstance(node, ast.Attribute) and node.attr == "plan_open_approach"
                    for node in ast.walk(ast.parse(code))
                ):
                    raise ValueError(
                        "Autonomous workers compose general motion primitives; plan_open_approach is a legacy stage demonstration"
                    )
        except (SyntaxError, ValueError) as exc:
            c.write_json(
                directory / "result.json",
                {
                    "candidate_id": candidate_id,
                    "status": "rejected",
                    "error": str(exc),
                    "provenance_audit": "PENDING",
                },
            )
            return c.read_json(directory / "result.json"), []
        self.check_runtime()
        programs = {"candidate": code.encode()}
        identity = c.build_identity(
            programs,
            "development",
            self.identity["seeds"],
            self.identity["limits"],
            self.identity["runtime"],
            suite=self.identity["suite"],
        )
        with contextlib.redirect_stdout(sys.stderr):
            summary = self.run_campaign(
                directory / "campaign",
                identity,
                programs,
                self.env,
                check_runtime=(lambda: runtime_identity(self.env, self.identity["suite"]))
                if self.runtime_check
                else None,
            )
        self.check_runtime()
        summary = self.scored_summary(directory / "campaign", summary)
        result = {
            "candidate_id": candidate_id,
            "status": "recorded" if summary["complete"] else "infrastructure_incomplete",
            "comparison": summary["comparison"]["candidate"],
            "ast_nodes": len(list(ast.walk(ast.parse(code)))),
            "provenance_audit": "PENDING",
        }
        c.write_json(directory / "result.json", result)
        return result, []

    def audited_summary(self, directory):
        root = directory / "campaign"
        identity = c.read_json(root / "campaign.json")
        expected = c.build_identity(
            {"candidate": (directory / "program.py").read_bytes()},
            "development",
            self.identity["seeds"],
            self.identity["limits"],
            self.identity["runtime"],
            suite=self.identity["suite"],
        )
        if identity != expected:
            raise ValueError("Candidate campaign differs from the assigned task/session")
        return self.scored_summary(root, c.summarize(root, identity))

    def inspect_results(self, candidate_id, mark=True):
        directory, submission = self.candidate(candidate_id)
        result = c.read_json(directory / "result.json")
        if result["status"] == "rejected":
            if mark:
                c.write_json(
                    directory / "inspected.json", {"program_sha256": submission["program_sha256"]}
                )
            return result, []
        summary = self.audited_summary(directory)
        if result["comparison"] != summary["comparison"]["candidate"]:
            raise ValueError("Candidate result differs from audited episodes")
        if not summary["complete"]:
            if mark:
                c.write_json(
                    directory / "inspected.json", {"program_sha256": submission["program_sha256"]}
                )
            return {
                **result,
                "physical_diagnosis": "unavailable for incomplete episodes",
                "execution_status": [
                    {"case_index": i, "status": row["status"]}
                    for i, row in enumerate(summary["cases"])
                ],
            }, []
        feedback = feedback_for(directory / "campaign", summary)
        from cap_harness.so101.action_feedback import action_feedback
        from cap_harness.so101.visual_feedback import visual_feedback

        for index, row in enumerate(summary["cases"]):
            run = directory / "campaign" / row["attempts"][-1]["directory"] / row["episode"]["run"]
            feedback["cases"][index]["public_action_results"] = action_feedback(run)
            feedback["cases"][index]["public_visual_motion"] = visual_feedback(run)
            diagnosis = c.read_json(run / "evaluation/so101-diagnostics.json")
            final = diagnosis["final_state"]
            feedback["cases"][index]["public_final_measurements"] = {
                key: final[key] for key in ("finger_forces_n", "gripper_opening") if key in final
            }
            if self.identity["suite"] == "so101_fruitgym_harvest":
                from cap_harness.so101 import skill_contracts

                feedback["cases"][index]["skill_evaluations"] = {
                    name: skill_contracts.score(run, name) for name in skill_contracts.CONTRACTS
                }
                if "skill_evaluation" in row:
                    feedback["cases"][index]["active_skill_evaluation"] = row["skill_evaluation"]
                feedback["cases"][index]["harvest_progress"] = {
                    key: final[key]
                    for key in (
                        "phase",
                        "free_hold_verified",
                        "destination_verified",
                        "deposit_started",
                        "placement_hold_s",
                        "container_base_contact",
                        "ordered_stages_complete",
                    )
                    if key in final
                }
                report = public_approach_report(run)
                if report:
                    feedback["cases"][index]["public_approach_report"] = report
                relative = "source/program-result.json"
                if relative in {
                    item["path"] for item in c.read_json(run / "manifest.json")["files"]
                }:
                    from cap_harness.so101.public_feedback import program_feedback

                    feedback["cases"][index]["public_program_result"] = program_feedback(
                        c.read_json(run / relative)
                    )
                from cap_harness.so101.experiment_feedback import experiment_feedback

                feedback["cases"][index]["experiment_evidence"] = experiment_feedback(
                    feedback["cases"][index]
                )
            frames = []
            for event in diagnosis["events"][:24]:
                reference = event.get("visual_reference", {})
                frames.append(
                    {
                        "event_code": event["code"],
                        "time_s": event["time_s"],
                        "frame_before": reference.get("frame_before"),
                        "frame_after": reference.get("frame_after"),
                    }
                )
            feedback["cases"][index]["event_frames"] = frames
        if mark:
            c.write_json(
                directory / "inspected.json", {"program_sha256": submission["program_sha256"]}
            )
        return {
            **result,
            "feedback": feedback,
            "frame_note": "Use view_frame by case_index and camera. Events between 20 Hz frames may require numerical evidence.",
        }, []

    def view_frame(self, candidate_id, case_index, camera, frame_index):
        import cv2

        directory, _ = self.candidate(candidate_id)
        if camera not in CAMERAS or type(case_index) is not int or type(frame_index) is not int:
            raise ValueError("Use an allowed camera and integer case/frame indices")
        summary = self.audited_summary(directory)
        if not 0 <= case_index < len(summary["cases"]) or frame_index < 0:
            raise ValueError("Case/frame index out of range")
        row = summary["cases"][case_index]
        if not row["episode"]:
            raise ValueError("This case has no audited episode")
        run = directory / "campaign" / row["attempts"][-1]["directory"] / row["episode"]["run"]
        relative = f"media/videos/{camera}.mp4"
        entry = next(
            (r for r in c.read_json(run / "manifest.json")["files"] if r["path"] == relative), None
        )
        if not entry or c.file_sha(run / relative) != entry["sha256"]:
            raise ValueError("Missing or modified audited video")
        video = cv2.VideoCapture(str(run / relative))
        try:
            count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(video.get(cv2.CAP_PROP_FPS))
            if not 0 <= frame_index < count or fps <= 0:
                raise ValueError("Frame index outside the recorded video")
            video.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, image = video.read()
            if not ok:
                raise ValueError("Recorded frame cannot be decoded")
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        finally:
            video.release()
        image_path = (
            self.root / "frames" / f"{candidate_id}-{case_index}-{camera}-{frame_index}.png"
        )
        image_path.parent.mkdir(exist_ok=True)
        image_path.write_bytes(png_bytes(rgb))
        record = {
            "candidate_id": candidate_id,
            "case_index": case_index,
            "camera": camera,
            "frame_index": frame_index,
            "frame_count": count,
            "time_s": frame_index / fps,
            "source_video_sha256": entry["sha256"],
            "path": str(image_path.relative_to(self.root)),
            "sha256": c.file_sha(image_path),
        }
        c.write_json(image_path.with_suffix(".json"), record)
        return record, [image_path]

    def finish_session(self, candidate_id, analysis, skill_report=None):
        directory, _ = self.candidate(candidate_id)
        if not isinstance(analysis, str) or not analysis.strip() or len(analysis) > 8000:
            raise ValueError("Provide a bounded final analysis")
        if not (directory / "inspected.json").exists():
            raise ValueError("Inspect the selected candidate first")
        if "skill_library" in self.identity:
            from cap_harness.so101.skills import validate_report

            candidates = {
                p.parent.name for p in (self.root / "candidates").glob("*/inspected.json")
            }
            validate_report(skill_report, self.identity["skill_library"], candidates)
            report_path = self.root / "skill-report.json"
            if report_path.exists() and c.read_json(report_path) != skill_report:
                raise ValueError("Skill report is already frozen")
        scored = []
        for path in (self.root / "candidates").glob("*/submission.json"):
            result_path = path.parent / "result.json"
            if result_path.exists() and c.read_json(result_path)["status"] == "recorded":
                summary = self.audited_summary(path.parent)
                comparison = summary["comparison"]["candidate"]
                submission = c.read_json(path)
                scored.append(
                    (
                        (
                            comparison.get("skill_success", comparison["task_success"]),
                            comparison["program_ok"],
                            -len(
                                list(
                                    ast.walk(
                                        ast.parse(
                                            (path.parent / "program.py").read_text(encoding="utf-8")
                                        )
                                    )
                                )
                            )
                            if self.identity.get("tie_breaker") == "ast_size"
                            else 0,
                            -submission["order"],
                        ),
                        submission["candidate_id"],
                    )
                )
        result, _ = self.inspect_results(candidate_id, mark=False)
        infrastructure_blocked = not scored and result["status"] == "infrastructure_incomplete"
        evidence_choice = self.identity.get("tie_breaker") == "evidence_choice"
        selected_score = next((score for score, name in scored if name == candidate_id), None)
        valid_choice = bool(scored) and (
            selected_score is not None and selected_score[:2] == max(scored)[0][:2]
            if evidence_choice
            else max(scored)[1] == candidate_id
        )
        if not infrastructure_blocked and not valid_choice:
            raise ValueError(
                "Choose the highest scoring candidate under the declared selection rule"
            )
        if self.identity.get("search_protocol") and not infrastructure_blocked:
            submissions = sorted(
                (c.read_json(p) for p in (self.root / "candidates").glob("*/submission.json")),
                key=lambda row: row["order"],
            )
            for index, row in enumerate(submissions):
                source = (self.root / "candidates" / row["candidate_id"] / "program.py").read_text(
                    encoding="utf-8"
                )
                if strategy_search.descriptor(
                    self.identity["search_protocol"],
                    row["hypothesis"],
                    source,
                    submissions[:index],
                    self.root,
                ) != row.get("search_strategy"):
                    raise ValueError("Search strategy record was modified")
            if (
                selected_score[0] != len(self.identity["seeds"])
                and len(submissions) < self.identity["max_programs"]
                and self.identity["search_protocol"].get("require_budget_exhaustion", True)
            ):
                raise ValueError(
                    "Complete diverse exploration/refinement budget before finishing without physical success"
                )
        if not infrastructure_blocked:
            if not list((self.root / "frames").glob(f"{candidate_id}-*.json")):
                raise ValueError("View at least one audited frame of the selected candidate")
            for path in (self.root / "frames").glob(f"{candidate_id}-*.json"):
                self.audit_images({"images": [c.read_json(path)]})
        finish = {
            "candidate_id": candidate_id,
            "analysis": analysis,
            "comparison": result["comparison"],
            "status": "infrastructure_blocked"
            if infrastructure_blocked
            else "experimental_candidate",
            "provenance_audit": "PENDING",
            "canonical_stage1_complete": False,
            "reserved_cases_executed": False,
            "verified_skill_promoted": False,
        }
        path = self.root / "finish.json"
        if path.exists() and c.read_json(path) != finish:
            raise ValueError("Session is already closed with another conclusion")
        if "skill_library" in self.identity:
            c.write_json(self.root / "skill-report.json", skill_report)
        c.write_json(path, finish)
        return finish, []

    def call(self, name, arguments):
        with c.campaign_lock(self.root):
            if name not in TOOLS:
                raise ValueError("Unknown debug tool")
            calls = self.root / "calls"
            calls.mkdir(exist_ok=True)
            index = len(list(calls.glob("*.json")))
            if index >= self.identity["max_calls"]:
                raise ValueError("Tool-call budget exhausted")
            record_path = calls / f"{index:04d}.json"
            record = {"tool": name, "arguments": arguments, "status": "started"}
            c.write_json(record_path, record)
            try:
                if (self.root / "finish.json").exists() and name in (
                    "execute_program",
                    "explore_scene",
                ):
                    raise ValueError("Session is closed")
                value, images = getattr(self, name)(**arguments)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                value, images = {"ok": False, "error": str(exc)[:1600]}, []
            record.update(
                status="completed",
                result=value,
                images=[
                    {"path": str(p.relative_to(self.root)), "sha256": c.file_sha(p)} for p in images
                ],
            )
            c.write_json(record_path, record)
            return value, images
