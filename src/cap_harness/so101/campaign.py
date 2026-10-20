"""Bounded, resumable strawberry campaigns for Linux/WSL; no model calls or motion hardware."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time

from cap_harness.so101.cases import DEFAULT_CASES_PATH, canonical_sha256, load_detachment_cases
from cap_harness.so101.paths import workspace_root

ROOT = workspace_root()
SCHEMA = "so101-strawberry-campaign-v1"
SUITE = "so101_strawberry_detachment_cases"
PARENT_GUARD = """import ctypes, os, signal, sys
if ctypes.CDLL(None).prctl(1, signal.SIGKILL) != 0 or os.getppid() != int(sys.argv[1]):
    os._exit(125)
os.execvpe(sys.argv[2], sys.argv[2:], os.environ)
"""
ENV_KEYS = (
    "MUJOCO_GL",
    "PYOPENGL_PLATFORM",
    "EGL_PLATFORM",
    "MUJOCO_EGL_DEVICE_ID",
    "GALLIUM_DRIVER",
    "MESA_D3D12_DEFAULT_ADAPTER_NAME",
    "CUDA_VISIBLE_DEVICES",
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "LD_LIBRARY_PATH",
    "PYTHONPATH",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "CAP_HARNESS_SO101_SEGMENTATION",
    "CAP_HARNESS_SAM3_URL",
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_identity(root, paths):
    return {str(p.relative_to(root)): file_sha(p) for p in sorted(set(paths)) if p.is_file()}


def child_environment(renderer):
    env = os.environ.copy()
    env["MUJOCO_GL"] = renderer
    if renderer == "glfw":
        for key in ("PYOPENGL_PLATFORM", "EGL_PLATFORM", "MUJOCO_EGL_DEVICE_ID"):
            env.pop(key, None)
    else:
        env["PYOPENGL_PLATFORM"] = "egl"
    return env


def runtime_identity(env):
    """Include dirty source and native model/assets, not merely the repository HEAD."""
    model_config = read_json(ROOT / "src/cap_harness/configs/robots/so101.json")
    model_root = ROOT / model_config["checkout"] / model_config["sparse_path"]
    if not model_root.is_dir():
        raise ValueError("Install the pinned SO-101 model before creating a campaign")
    spec = importlib.util.find_spec("robosuite")
    if spec is None or not spec.origin:
        raise ValueError("Activate .venv-robosuite before running a campaign")
    suite_root = Path(spec.origin).parent
    source = tree_identity(
        ROOT,
        [
            *ROOT.joinpath("src").rglob("*.py"),
            ROOT / "pyproject.toml",
            ROOT / "src/cap_harness/configs/robots/so101.json",
            *ROOT.joinpath(".claude/skills/iterative-debugging/scripts").glob("*.py"),
        ],
    )
    return {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "environment": {k: env.get(k) for k in ENV_KEYS},
        "distributions": sorted(
            [d.metadata["Name"], d.version] for d in importlib.metadata.distributions()
        ),
        "source_files": source,
        "model_files": tree_identity(model_root, model_root.rglob("*")),
        "robosuite_files": tree_identity(
            suite_root, (p for p in suite_root.rglob("*") if "__pycache__" not in p.parts)
        ),
    }


def protocol_for(suite):
    if suite == SUITE:
        return read_json(DEFAULT_CASES_PATH)
    from cap_harness.so101.harvest_protocol import SUITE as HARVEST
    from cap_harness.so101.harvest_protocol import protocol

    if suite == HARVEST:
        return protocol()
    raise ValueError("Unknown SO-101 campaign suite")


def build_identity(programs, partition, seeds, limits, runtime, selection=None, *, suite=SUITE):
    for name in ("max_steps", "max_attempts", "width", "height"):
        if type(limits[name]) is not int or limits[name] <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if not math.isfinite(limits["timeout_s"]) or limits["timeout_s"] <= 0:
        raise ValueError("timeout_s must be finite and positive")
    if suite == SUITE:
        all_cases = [case.to_record() for case in load_detachment_cases()]
    else:
        from cap_harness.so101.harvest_protocol import SUITE as HARVEST
        from cap_harness.so101.harvest_protocol import cases as harvest_cases

        if suite != HARVEST:
            raise ValueError("Unknown campaign suite")
        all_cases = harvest_cases()
    available = [case for case in all_cases if case["partition"] == partition]
    if not available:
        raise ValueError("Unknown partition")
    selected = seeds if seeds is not None else [case["seed"] for case in available]
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("Select a nonempty list of unique seeds")
    cases = [case for case in available if case["seed"] in selected]
    if len(cases) != len(selected):
        raise ValueError("Seeds must belong to the requested partition")
    if not programs or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", n) for n in programs):
        raise ValueError("Use unique, simple program labels")
    versions = {n: hashlib.sha256(code).hexdigest() for n, code in sorted(programs.items())}
    protocol = protocol_for(suite)
    identity = {
        "schema": SCHEMA,
        "suite": suite,
        "partition": partition,
        "cases": cases,
        "protocol_sha256": canonical_sha256(protocol),
        "programs": versions,
        "limits": limits,
        "runtime": runtime,
        "retry_policy": "First audited episode counts, including physical/program failures; retry only infrastructure failures.",
        "selection_sha256": canonical_sha256(selection) if selection else None,
    }
    if partition != "development":
        if len(programs) != 1 or len(cases) != len(available) or not selection:
            raise ValueError(
                "Reserved partitions require one frozen program and the entire partition"
            )
        if (
            selection.get("schema") != SCHEMA
            or selection.get("program_sha256") != next(iter(versions.values()))
            or selection.get("runtime_sha256") != canonical_sha256(runtime)
            or selection.get("limits") != limits
            or selection.get("protocol_sha256") != identity["protocol_sha256"]
        ):
            raise ValueError(
                "Frozen selection does not match this code, protocol, runtime or budget"
            )
    elif selection:
        raise ValueError("A frozen selection is only used for reserved partitions")
    return identity


@contextmanager
def campaign_lock(root):
    if sys.platform != "linux":
        raise ValueError("Run campaigns inside Linux/WSL")
    import fcntl

    root.mkdir(parents=True, exist_ok=True)
    with (root / ".lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another process owns this campaign") from exc
        try:
            yield stream.fileno()
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def prepare(root, identity, programs, selection=None):
    if (root / "invalidated.json").exists():
        raise ValueError("Runtime changed during a previous episode; use a new campaign directory")
    manifest = root / "campaign.json"
    if manifest.exists():
        if read_json(manifest) != identity:
            raise ValueError("Campaign identity changed; use a new output directory")
    else:
        if any(p.name != ".lock" for p in root.iterdir()):
            raise ValueError("Output directory is not an empty campaign")
        for name, code in programs.items():
            path = root / "inputs/programs" / f"{name}.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(code)
        write_json(root / "inputs/protocol.json", protocol_for(identity["suite"]))
        if selection:
            write_json(root / "inputs/selection.json", selection)
        write_json(manifest, identity)
    for name, digest in identity["programs"].items():
        if file_sha(root / "inputs/programs" / f"{name}.py") != digest:
            raise ValueError("Campaign program snapshot was modified")
    if canonical_sha256(read_json(root / "inputs/protocol.json")) != identity["protocol_sha256"]:
        raise ValueError("Campaign protocol snapshot was modified")
    if selection and read_json(root / "inputs/selection.json") != selection:
        raise ValueError("Campaign selection snapshot was modified")


def stop_process_group(process):
    # Kill descendants too (encoders or child workers), even if their parent exited.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def execute(command, attempt, env, timeout_s, lock_fd=None):
    start = time.monotonic()
    with (
        (attempt / "stdout.log").open("wb") as stdout,
        (attempt / "stderr.log").open("wb") as stderr,
    ):
        process = subprocess.Popen(
            [sys.executable, "-c", PARENT_GUARD, str(os.getpid()), *command],
            cwd=ROOT,
            env=env,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
            pass_fds=(lock_fd,) if lock_fd is not None else (),
        )
        try:
            code = process.wait(timeout=timeout_s)
            return {"status": "exited", "returncode": code, "wall_s": time.monotonic() - start}
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "returncode": None, "wall_s": time.monotonic() - start}
        finally:
            stop_process_group(process)


def audit_run(attempt, case, program_sha):
    runs = list((attempt / "episodes").glob("*/run-*"))
    if len(runs) != 1:
        raise ValueError("Expected exactly one finalized episode")
    run = runs[0]
    manifest = read_json(run / "manifest.json")
    paths = set()
    for row in manifest["files"]:
        path = (run / row["path"]).resolve()
        if not path.is_relative_to(run.resolve()) or row["path"] in paths:
            raise ValueError("Unsafe or repeated artifact path")
        paths.add(row["path"])
        if file_sha(path) != row["sha256"]:
            raise ValueError(f"Artifact hash mismatch: {row['path']}")
    required = {
        "outcome.json",
        "source/program.py",
        "evaluation/so101-task.json",
        "evaluation/so101-diagnostics.json",
        "evaluation/so101-case-protocol.json",
    }
    if not required <= paths:
        raise ValueError("Episode is missing required evidence")
    if file_sha(run / "source/program.py") != program_sha:
        raise ValueError("Episode executed different program bytes")
    evidence = read_json(run / "evaluation/so101-task.json")
    if evidence.get("case") != case:
        raise ValueError("Episode executed a different case")
    if (
        canonical_sha256(read_json(run / "evaluation/so101-case-protocol.json"))
        != case["protocol_sha256"]
    ):
        raise ValueError("Episode protocol differs from the campaign")
    outcome = read_json(run / "outcome.json")
    diagnosis = read_json(run / "evaluation/so101-diagnostics.json")
    if (
        type(outcome.get("program_ok")) is not bool
        or type(outcome.get("task_success")) is not bool
        or outcome["task_success"] != diagnosis["task_success"]
        or outcome.get("finalization_errors")
    ):
        raise ValueError("Episode outcome and diagnostic are incomplete or inconsistent")
    if outcome["termination_reason"] in ("harness_error", "provider_error", "user_interrupt"):
        raise ValueError("Infrastructure interrupted the episode: " + outcome["termination_reason"])
    return {
        "run": str(run.relative_to(attempt)),
        "manifest_sha256": file_sha(run / "manifest.json"),
        "program_ok": outcome["program_ok"],
        "task_success": outcome["task_success"],
        "termination_reason": outcome["termination_reason"],
        "execution_error": outcome["error"],
        "physical_status": diagnosis["status"],
        "primary_finding": diagnosis["primary_finding"],
        "steps_executed": outcome["steps_executed"],
    }


def command_for(root, name, case, attempt, limits, *, suite=SUITE):
    return [
        sys.executable,
        "-m",
        "cap_harness.cli",
        "run",
        "--benchmark",
        "so101",
        "--suite",
        suite,
        "--task-id",
        "0",
        "--seed",
        str(case["seed"]),
        "--program",
        str(root / "inputs/programs" / f"{name}.py"),
        "--output-root",
        str(attempt / "episodes"),
        "--flat-run-dir",
        "--max-steps",
        str(limits["max_steps"]),
        "--camera-width",
        str(limits["width"]),
        "--camera-height",
        str(limits["height"]),
    ]


def summarize(root, identity):
    rows = []
    for name, digest in identity["programs"].items():
        for case in identity["cases"]:
            attempts = []
            for directory in sorted(
                (root / "attempts" / name / str(case["seed"])).glob("attempt-*")
            ):
                result_path = directory / "result.json"
                if not result_path.exists():
                    # Kernel lock guarantees the old writer is gone; preserve its incomplete files.
                    try:
                        episode = audit_run(directory, case, digest)
                    except (ValueError, OSError, KeyError, TypeError):
                        recovered = {
                            "status": "interrupted",
                            "reason": "Previous writer ended without a terminal record",
                        }
                    else:
                        recovered = {
                            "status": "recorded",
                            "episode": episode,
                            "recovered_after_interruption": True,
                        }
                    write_json(result_path, recovered)
                result = read_json(result_path)
                if result["status"] == "recorded":
                    if audit_run(directory, case, digest) != result["episode"]:
                        raise ValueError("Previously recorded evidence changed")
                attempts.append({"directory": str(directory.relative_to(root)), **result})
            recorded = [a for a in attempts if a["status"] == "recorded"]
            if len(recorded) > 1:
                raise ValueError("Multiple scored episodes for one program/case")
            status = (
                "recorded"
                if recorded
                else (
                    "exhausted"
                    if len(attempts) >= identity["limits"]["max_attempts"]
                    else "pending"
                )
            )
            rows.append(
                {
                    "program": name,
                    "seed": case["seed"],
                    "status": status,
                    "attempts": attempts,
                    "episode": recorded[0]["episode"] if recorded else None,
                }
            )
    comparison = {}
    for name in identity["programs"]:
        subset = [r for r in rows if r["program"] == name]
        episodes = [r["episode"] for r in subset if r["episode"]]
        successes = sum(e["task_success"] for e in episodes)
        comparison[name] = {
            "planned": len(subset),
            "recorded": len(episodes),
            "pending": sum(r["status"] == "pending" for r in subset),
            "exhausted": sum(r["status"] == "exhausted" for r in subset),
            "program_ok": sum(e["program_ok"] for e in episodes),
            "task_success": successes,
            "task_success_rate": successes / len(subset) if len(episodes) == len(subset) else None,
            "findings": dict(
                Counter(e["primary_finding"]["code"] for e in episodes if e["primary_finding"])
            ),
        }
    summary = {
        "campaign_sha256": canonical_sha256(identity),
        "partition": identity["partition"],
        "complete": all(r["status"] == "recorded" for r in rows),
        "comparison": comparison,
        "cases": rows,
    }
    write_json(root / "summary.json", summary)
    return summary


def run_campaign(
    root,
    identity,
    programs,
    env,
    run_budget=None,
    selection=None,
    runner=execute,
    check_runtime=None,
):
    root = Path(root).resolve()
    if run_budget is not None and (type(run_budget) is not int or run_budget <= 0):
        raise ValueError("run-budget must be positive")
    with campaign_lock(root) as lock_fd:
        prepare(root, identity, programs, selection)
        summary = summarize(root, identity)
        submitted = 0
        for case in identity["cases"]:
            for name in identity["programs"]:
                while True:
                    row = next(
                        r
                        for r in summary["cases"]
                        if r["program"] == name and r["seed"] == case["seed"]
                    )
                    if row["status"] != "pending" or (
                        run_budget is not None and submitted >= run_budget
                    ):
                        break
                    if check_runtime and check_runtime() != identity["runtime"]:
                        raise ValueError(
                            "Runtime changed during the campaign; use a new output directory"
                        )
                    attempt = (
                        root
                        / "attempts"
                        / name
                        / str(case["seed"])
                        / f"attempt-{len(row['attempts']) + 1:03d}"
                    )
                    attempt.mkdir(parents=True, exist_ok=False)
                    command = command_for(
                        root, name, case, attempt, identity["limits"], suite=identity["suite"]
                    )
                    write_json(
                        attempt / "started.json",
                        {"command": command, "campaign_sha256": canonical_sha256(identity)},
                    )
                    print(f"{name}: seed {case['seed']}, {attempt.name}", flush=True)
                    try:
                        if runner is execute:
                            result = execute(
                                command,
                                attempt,
                                env,
                                identity["limits"]["timeout_s"],
                                lock_fd=lock_fd,
                            )
                        else:
                            result = runner(command, attempt, env, identity["limits"]["timeout_s"])
                        if result["status"] == "exited":
                            try:
                                episode = audit_run(attempt, case, identity["programs"][name])
                            except (ValueError, OSError, KeyError, TypeError) as exc:
                                result.update(status="infrastructure_error", reason=str(exc))
                            else:
                                result.update(status="recorded", episode=episode)
                    except KeyboardInterrupt:
                        write_json(attempt / "result.json", {"status": "interrupted"})
                        summarize(root, identity)
                        raise
                    except OSError as exc:
                        result = {"status": "infrastructure_error", "reason": str(exc)}
                    write_json(attempt / "result.json", result)
                    if check_runtime and check_runtime() != identity["runtime"]:
                        write_json(
                            root / "invalidated.json",
                            {
                                "reason": "Runtime fingerprint changed while an episode was running",
                                "attempt": str(attempt.relative_to(root)),
                            },
                        )
                        raise ValueError(
                            "Runtime changed during an episode; campaign cannot be resumed"
                        )
                    submitted += 1
                    summary = summarize(root, identity)
        print(json.dumps(summary["comparison"], indent=2), flush=True)
        return summary


def freeze_selection(root, program):
    root = Path(root).resolve()
    with campaign_lock(root):
        identity = read_json(root / "campaign.json")
        if identity["partition"] != "development" or program not in identity["programs"]:
            raise ValueError("Freeze a program from a development campaign")
        full = {
            row["seed"]
            for row in protocol_for(identity["suite"])["cases"]
            if row["partition"] == "development"
        }
        if {c["seed"] for c in identity["cases"]} != full:
            raise ValueError("Complete all development cases before freezing")
        programs = {
            n: (root / "inputs/programs" / f"{n}.py").read_bytes() for n in identity["programs"]
        }
        prepare(root, identity, programs)
        summary = summarize(root, identity)
        if summary["comparison"][program]["recorded"] != len(full):
            raise ValueError("Selected program has unfinished development cases")
        selection = {
            "schema": SCHEMA,
            "development_campaign_sha256": canonical_sha256(identity),
            "program": program,
            "program_sha256": identity["programs"][program],
            "runtime_sha256": canonical_sha256(identity["runtime"]),
            "limits": identity["limits"],
            "protocol_sha256": identity["protocol_sha256"],
            "policy": "Frozen before validation/evaluation; do not use evaluation failures to revise this candidate.",
        }
        path = root / "selection.json"
        if path.exists() and read_json(path) != selection:
            raise ValueError("This campaign already froze another selection")
        write_json(path, selection)
        return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument(
        "--program", action="append", required=True, help="Unique NAME=PATH, repeat to compare"
    )
    run.add_argument(
        "--partition", choices=("development", "validation", "evaluation"), default="development"
    )
    run.add_argument("--seeds", type=int, nargs="+")
    run.add_argument("--selection", type=Path)
    run.add_argument("--renderer", choices=("glfw", "egl"), default="glfw")
    run.add_argument("--max-steps", type=int, default=800)
    run.add_argument("--timeout-s", type=float, default=180)
    run.add_argument("--max-attempts", type=int, default=2)
    run.add_argument("--width", type=int, default=320)
    run.add_argument("--height", type=int, default=240)
    run.add_argument(
        "--run-budget", type=int, help="Maximum new attempts in this invocation; rerun to resume"
    )
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--output", type=Path, required=True, help="Existing development campaign")
    freeze.add_argument("--program", required=True, help="Program label to freeze")
    args = parser.parse_args(argv)
    try:
        if args.command == "freeze":
            print(freeze_selection(args.output, args.program))
            return 0
        programs = {}
        for entry in args.program:
            name, separator, source = entry.partition("=")
            if not separator or name in programs:
                raise ValueError("Programs require unique NAME=PATH entries")
            programs[name] = Path(source).read_bytes()
        limits = {
            k: getattr(args, k)
            for k in ("max_steps", "timeout_s", "max_attempts", "width", "height")
        }
        env = child_environment(args.renderer)
        selection = read_json(args.selection) if args.selection else None
        identity = build_identity(
            programs, args.partition, args.seeds, limits, runtime_identity(env), selection
        )
        summary = run_campaign(
            args.output,
            identity,
            programs,
            env,
            args.run_budget,
            selection,
            check_runtime=lambda: runtime_identity(env),
        )
        # Physical failures are valid campaign results. Exit 2 means infrastructure exhausted.
        return 2 if any(r["status"] == "exhausted" for r in summary["cases"]) else 0
    except KeyboardInterrupt:
        print("Campaign interrupted; rerun the same command to resume.", file=sys.stderr)
        return 130
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Campaign: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
