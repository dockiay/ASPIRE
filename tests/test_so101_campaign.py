"""Campaign bookkeeping tests use synthetic artifacts, never reserved native scenes."""

import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys

import pytest

from cap_harness.so101 import campaign as c
from cap_harness.so101.cases import DEFAULT_CASES_PATH, canonical_sha256

PROGRAMS = {"probe": b"result = 1\n", "other": b"result = 2\n"}
LIMITS = {"max_steps": 800, "timeout_s": 180.0, "max_attempts": 2, "width": 320, "height": 240}
RUNTIME = {"engine": "synthetic artifacts only"}


def identity(programs=None, seeds=None, **kwargs):
    return c.build_identity(
        programs or PROGRAMS, "development", seeds or [101, 102], dict(LIMITS), RUNTIME, **kwargs
    )


def fake_runner(command, attempt, env, timeout_s):
    """Emit the same artifact contract as cap-harness, without simulating anything."""
    seed = int(command[command.index("--seed") + 1])
    program = Path(command[command.index("--program") + 1])
    case = next(row for row in c.load_detachment_cases() if row.seed == seed).to_record()
    run = attempt / "episodes" / str(seed) / "run-fake"
    run.mkdir(parents=True)
    files = {
        "outcome.json": {
            "program_ok": True,
            "task_success": False,
            "error": None,
            "termination_reason": "program_completed",
            "steps_executed": 8,
            "finalization_errors": [],
        },
        "evaluation/so101-task.json": {"case": case},
        "evaluation/so101-diagnostics.json": {
            "task_success": False,
            "status": "incomplete",
            "primary_finding": {"code": "grasp_not_qualified"},
        },
        "evaluation/so101-case-protocol.json": c.read_json(DEFAULT_CASES_PATH),
    }
    for name, value in files.items():
        c.write_json(run / name, value)
    (run / "source").mkdir()
    (run / "source/program.py").write_bytes(program.read_bytes())
    rebuild_manifest(run)
    return {"status": "exited", "returncode": 0, "wall_s": 0.01}


def rebuild_manifest(run):
    c.write_json(
        run / "manifest.json",
        {
            "files": [
                {"path": str(p.relative_to(run)), "sha256": c.file_sha(p)}
                for p in sorted(run.rglob("*"))
                if p.is_file() and p.name != "manifest.json"
            ]
        },
    )


def test_comparison_resume_and_physical_failures_are_not_retried(tmp_path):
    ident = identity()
    first = c.run_campaign(tmp_path, ident, PROGRAMS, {}, run_budget=1, runner=fake_runner)
    assert not first["complete"]
    assert first["comparison"]["other"]["recorded"] == 1
    assert first["comparison"]["probe"]["task_success_rate"] is None
    complete = c.run_campaign(tmp_path, ident, PROGRAMS, {}, runner=fake_runner)
    assert complete["complete"]
    assert all(len(row["attempts"]) == 1 for row in complete["cases"])
    assert complete["comparison"]["probe"]["task_success_rate"] == 0
    assert complete["comparison"]["other"]["findings"] == {"grasp_not_qualified": 2}

    def must_not_run(*args):
        pytest.fail("Finalized episodes must not run again")

    assert c.run_campaign(tmp_path, ident, PROGRAMS, {}, runner=must_not_run) == complete


def test_only_infrastructure_retries_and_budget_is_global_across_resumes(tmp_path):
    ident = identity({"probe": PROGRAMS["probe"]}, [101])
    calls = []

    def timeout(*args):
        calls.append(args)
        return {"status": "timeout"}

    one = c.run_campaign(tmp_path, ident, {"probe": PROGRAMS["probe"]}, {}, 1, runner=timeout)
    assert one["cases"][0]["status"] == "pending"
    two = c.run_campaign(tmp_path, ident, {"probe": PROGRAMS["probe"]}, {}, runner=timeout)
    assert two["cases"][0]["status"] == "exhausted"
    assert two["comparison"]["probe"]["task_success_rate"] is None
    c.run_campaign(tmp_path, ident, {"probe": PROGRAMS["probe"]}, {}, runner=timeout)
    assert len(calls) == 2


def test_interrupt_preserves_attempt_then_retries_without_overwrite(tmp_path):
    programs = {"probe": PROGRAMS["probe"]}
    ident = identity(programs, [101])

    def interrupt(command, attempt, *args):
        (attempt / "partial.log").write_text("kept")
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        c.run_campaign(tmp_path, ident, programs, {}, runner=interrupt)
    result = c.run_campaign(tmp_path, ident, programs, {}, runner=fake_runner)
    attempts = result["cases"][0]["attempts"]
    assert [a["status"] for a in attempts] == ["interrupted", "recorded"]
    assert (tmp_path / attempts[0]["directory"] / "partial.log").read_text() == "kept"


def test_finished_episode_without_result_record_is_recovered(tmp_path):
    programs = {"probe": PROGRAMS["probe"]}
    ident = identity(programs, [101])
    c.run_campaign(tmp_path, ident, programs, {}, runner=fake_runner)
    next(tmp_path.glob("attempts/*/*/attempt-*/result.json")).unlink()

    def must_not_run(*args):
        pytest.fail("A finalized episode must be recovered rather than repeated")

    result = c.run_campaign(tmp_path, ident, programs, {}, runner=must_not_run)
    assert result["complete"]
    assert result["cases"][0]["attempts"][0]["recovered_after_interruption"]


def test_runtime_change_during_episode_invalidates_campaign_even_if_reverted(tmp_path):
    programs = {"probe": PROGRAMS["probe"]}
    ident = identity(programs, [101])
    calls = []

    def runtime_check():
        calls.append(1)
        return RUNTIME if len(calls) == 1 else {"engine": "changed"}

    with pytest.raises(ValueError, match="changed during an episode"):
        c.run_campaign(
            tmp_path, ident, programs, {}, runner=fake_runner, check_runtime=runtime_check
        )
    with pytest.raises(ValueError, match="previous episode"):
        c.run_campaign(tmp_path, ident, programs, {}, runner=fake_runner)


@pytest.mark.parametrize("change", ["program", "runtime", "budget"])
def test_identity_change_rejected_before_execution(tmp_path, change):
    ident = identity()
    with c.campaign_lock(tmp_path):
        c.prepare(tmp_path, ident, PROGRAMS)
    changed = json.loads(json.dumps(ident))
    if change == "program":
        changed["programs"]["probe"] = "changed"
    elif change == "runtime":
        changed["runtime"]["engine"] = "different physics"
    else:
        changed["limits"]["max_steps"] += 1
    with pytest.raises(ValueError, match="identity changed"):
        c.run_campaign(tmp_path, changed, PROGRAMS, {}, runner=fake_runner)


@pytest.mark.parametrize("target", ["program", "protocol", "episode", "manifest"])
def test_tampered_snapshots_or_recorded_evidence_are_rejected(tmp_path, target):
    programs = {"probe": PROGRAMS["probe"]}
    ident = identity(programs, [101])
    c.run_campaign(tmp_path, ident, programs, {}, runner=fake_runner)
    if target == "program":
        path = tmp_path / "inputs/programs/probe.py"
    elif target == "protocol":
        path = tmp_path / "inputs/protocol.json"
    else:
        run = next(tmp_path.glob("attempts/*/*/attempt-*/episodes/*/run-*"))
        path = run / ("outcome.json" if target == "episode" else "manifest.json")
    if target == "manifest":
        path.write_text(path.read_text() + "\n")
    elif target == "protocol":
        c.write_json(path, {"modified": True})
    else:
        path.write_text("changed")
    with pytest.raises(ValueError):
        c.run_campaign(tmp_path, ident, programs, {}, runner=fake_runner)


def test_audited_program_error_is_counted_once_and_score_is_task_success(tmp_path):
    def error_runner(*args):
        result = fake_runner(*args)
        attempt = args[1]
        run = next((attempt / "episodes").glob("*/run-*"))
        outcome = c.read_json(run / "outcome.json")
        outcome.update(program_ok=False, task_success=True, error={"message": "late exception"})
        c.write_json(run / "outcome.json", outcome)
        c.write_json(
            run / "evaluation/so101-diagnostics.json",
            {"task_success": True, "status": "completed", "primary_finding": None},
        )
        rebuild_manifest(run)
        return {**result, "returncode": 1}

    programs = {"probe": PROGRAMS["probe"]}
    result = c.run_campaign(tmp_path, identity(programs, [101]), programs, {}, runner=error_runner)
    assert result["comparison"]["probe"]["program_ok"] == 0
    assert result["comparison"]["probe"]["task_success_rate"] == 1
    assert len(result["cases"][0]["attempts"]) == 1


def test_freeze_requires_full_development_and_guards_reserved_partitions(tmp_path):
    programs = {"probe": PROGRAMS["probe"]}
    partial = tmp_path / "partial"
    c.run_campaign(partial, identity(programs, [101]), programs, {}, runner=fake_runner)
    with pytest.raises(ValueError, match="all development"):
        c.freeze_selection(partial, "probe")
    full = tmp_path / "full"
    ident = c.build_identity(programs, "development", None, LIMITS, RUNTIME)
    c.run_campaign(full, ident, programs, {}, run_budget=1, runner=fake_runner)
    with pytest.raises(ValueError, match="unfinished"):
        c.freeze_selection(full, "probe")
    c.run_campaign(full, ident, programs, {}, runner=fake_runner)
    selection = c.read_json(c.freeze_selection(full, "probe"))
    # Construct identities only: NEVER execute native validation/evaluation cases here.
    for partition, count in [("validation", 6), ("evaluation", 12)]:
        with pytest.raises(ValueError, match="frozen"):
            c.build_identity(programs, partition, None, LIMITS, RUNTIME)
        guarded = c.build_identity(programs, partition, None, LIMITS, RUNTIME, selection)
        assert len(guarded["cases"]) == count
        assert guarded["selection_sha256"] == canonical_sha256(selection)
        with pytest.raises(ValueError, match="does not match"):
            c.build_identity({"probe": b"modified\n"}, partition, None, LIMITS, RUNTIME, selection)
    with pytest.raises(ValueError, match="entire partition"):
        c.build_identity(programs, "evaluation", [1], LIMITS, RUNTIME, selection)


def test_exclusive_lock_and_glfw_environment(tmp_path, monkeypatch):
    with (
        c.campaign_lock(tmp_path),
        pytest.raises(ValueError, match="Another process"),
        c.campaign_lock(tmp_path),
    ):
        pass
    for key in ("PYOPENGL_PLATFORM", "EGL_PLATFORM", "MUJOCO_EGL_DEVICE_ID"):
        monkeypatch.setenv(key, "obsolete-egl")
    monkeypatch.setenv("MESA_D3D12_DEFAULT_ADAPTER_NAME", "NVIDIA")
    env = c.child_environment("glfw")
    assert env["MUJOCO_GL"] == "glfw"
    assert "PYOPENGL_PLATFORM" not in env
    assert env["MESA_D3D12_DEFAULT_ADAPTER_NAME"] == "NVIDIA"


@pytest.mark.parametrize(
    "limits", [dict(LIMITS, timeout_s=float("nan")), dict(LIMITS, max_steps=0)]
)
def test_invalid_budgets_rejected(limits):
    with pytest.raises(ValueError):
        c.build_identity(PROGRAMS, "development", [101], limits, RUNTIME)


@pytest.mark.skipif(sys.platform != "linux", reason="Launcher is Linux/WSL only")
def test_wall_timeout_kills_process_group(tmp_path):
    pid_file = tmp_path / "child-pid"
    child = "import time; time.sleep(20)"
    source = (
        "import subprocess,sys,time,pathlib; "
        f"p=subprocess.Popen([sys.executable,'-c',{child!r}]); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); time.sleep(20)"
    )
    result = c.execute([sys.executable, "-c", source], tmp_path, os.environ.copy(), 0.5)
    assert result["status"] == "timeout" and result["wall_s"] < 3
    pid = int(pid_file.read_text())
    # An adopted child may briefly remain a zombie; it must no longer be running.
    status = Path(f"/proc/{pid}/status")
    assert not status.exists() or "State:\tZ" in status.read_text()


def test_cli_rejects_reserved_and_never_launches_simulator(tmp_path):
    program = tmp_path / "probe.py"
    program.write_bytes(PROGRAMS["probe"])
    # Runtime fingerprinting is replaced, so this guard is independent of GPU installation.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(c, "runtime_identity", lambda env: RUNTIME)
        assert (
            c.main(
                [
                    "run",
                    "--output",
                    str(tmp_path / "reserved"),
                    "--program",
                    f"probe={program}",
                    "--partition",
                    "evaluation",
                ]
            )
            == 1
        )
    assert not (tmp_path / "reserved").exists()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux parent-death signal")
def test_forced_launcher_death_terminates_simulator(tmp_path):
    pid_file = tmp_path / "pid"
    child_source = (
        "import os,signal,pathlib,time; "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); "
        "os.kill(os.getppid(),signal.SIGKILL); time.sleep(20)"
    )
    source = (
        "import os,sys; from pathlib import Path; "
        "from cap_harness.so101.campaign import execute; "
        f"execute([sys.executable,'-c',{child_source!r}],Path({str(tmp_path)!r}),os.environ.copy(),10)"
    )
    parent = subprocess.run([sys.executable, "-c", source], timeout=5, capture_output=True)
    assert parent.returncode == -signal.SIGKILL
    child_pid = int(pid_file.read_text())
    try:
        descriptor = os.pidfd_open(child_pid)
    except ProcessLookupError:
        return
    try:
        assert select.select([descriptor], [], [], 2)[0], "Orphaned simulator is still alive"
    finally:
        os.close(descriptor)
