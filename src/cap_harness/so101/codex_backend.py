"""Codex CLI code generation; also a stdlib-only worker for Windows/WSL interop."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

SCHEMA = {
    "type": "object",
    "properties": {name: {"type": "string"} for name in ("analysis", "change_summary", "program")},
    "required": ["analysis", "change_summary", "program"],
    "additionalProperties": False,
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def host_path(path, windows):
    path = str(Path(path).resolve())
    if windows and sys.platform == "linux":
        return subprocess.run(
            ["wslpath", "-w", path], check=True, capture_output=True, text=True, timeout=10
        ).stdout.strip()
    return path


def provider_spec(config):
    """Inspect the CLI normally; never read or copy its saved credentials."""
    if set(config) - {"codex", "host_python", "exchange_dir", "model"}:
        raise ValueError("Unknown Codex configuration field")
    executable = shutil.which(config.get("codex", "codex"))
    if not executable:
        raise ValueError("Codex CLI not found; configure codex in the local JSON file")
    windows = executable.lower().endswith(".exe") and sys.platform == "linux"
    python = config.get("host_python", sys.executable)
    if windows and (not Path(python).is_file() or not python.lower().endswith(".exe")):
        raise ValueError("Windows Codex requires a Windows host_python executable")
    version = subprocess.run(
        [executable, "--version"], check=True, capture_output=True, text=True, timeout=15
    ).stdout.strip()
    auth = subprocess.run(
        [executable, "login", "status"], capture_output=True, text=True, timeout=15
    )
    if auth.returncode != 0:
        raise ValueError("Codex is not authenticated; run codex login on its host")
    if "ChatGPT" not in auth.stdout + auth.stderr:
        raise ValueError("This connector expects saved ChatGPT authentication; use codex login")
    exchange = Path(config["exchange_dir"]).resolve()
    if windows and not str(exchange).startswith("/mnt/"):
        raise ValueError(
            "Use a Windows-mounted exchange_dir, e.g. /mnt/d/AI/Aspire/outputs/codex-exchange"
        )
    return {
        "codex": str(Path(executable).resolve()),
        "host_python": str(Path(python).resolve()),
        "exchange_dir": str(exchange),
        "windows": windows,
        "version": version,
        "model": config.get("model"),
        "auth": "saved ChatGPT login",
        "worker_sha256": digest(__file__),
    }


def codex_command(request):
    directory = Path(request["directory"])
    command = [
        request["codex"],
        "exec",
        "--ignore-user-config",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "--json",
        "-c",
        'approval_policy="never"',
        "-c",
        'web_search="disabled"',
        "--output-schema",
        str(directory / "schema.json"),
        "--output-last-message",
        str(directory / "response.json"),
        "--cd",
        str(directory / "workspace"),
    ]
    for feature in ("shell_tool", "apps", "plugins", "hooks", "multi_agent"):
        command.extend(["--disable", feature])
    # Explicit opt-in for the separate controlled-agent mode. The ordinary
    # generator still has no MCP server and rejects all tool calls.
    for key, value in request.get("mcp", {}).items():
        command.extend(["-c", f"mcp_servers.so101.{key}={json.dumps(value)}"])
    if request.get("model"):
        command.extend(["--model", request["model"]])
    return [*command, "-"]


def kill_tree(process):
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=10)


def worker(request_path):
    """Native host owns the timeout, including when the WSL caller disappears."""
    request_path = Path(request_path)
    request = read_json(request_path)
    directory = request_path.parent
    (directory / "workspace").mkdir(exist_ok=True)
    write_json(
        directory / "worker-started.json",
        {"pid": os.getpid(), "request_sha256": digest(request_path)},
    )
    environment = os.environ.copy()
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY"):
        environment.pop(key, None)
    start = time.monotonic()
    status, returncode, process = "failed", None, None
    (directory / "prompt.txt").write_text(request["prompt"], encoding="utf-8")
    try:
        with (
            (directory / "events.jsonl").open("wb") as stdout,
            (directory / "stderr.log").open("wb") as stderr,
            (directory / "prompt.txt").open("rb") as stdin,
        ):
            process = subprocess.Popen(
                codex_command(request),
                cwd=directory / "workspace",
                env=environment,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                start_new_session=os.name != "nt",
            )
            while True:
                try:
                    process.wait(timeout=0.25)
                    returncode = process.returncode
                    status = "ok" if returncode == 0 else "failed"
                    break
                except subprocess.TimeoutExpired:
                    if (directory / "cancel").exists() or time.monotonic() - start >= request[
                        "timeout_s"
                    ]:
                        status = "cancelled" if (directory / "cancel").exists() else "timeout"
                        kill_tree(process)
                        returncode = process.returncode
                        break
    except (OSError, subprocess.SubprocessError) as exc:
        status = "failed"
        write_json(
            directory / "worker-error.json", {"error": type(exc).__name__, "message": str(exc)}
        )
    finally:
        if process is not None and process.poll() is None:
            kill_tree(process)
        write_json(
            directory / "worker-result.json",
            {
                "status": status,
                "returncode": returncode,
                "wall_s": time.monotonic() - start,
                "request_sha256": digest(request_path),
                "response_sha256": digest(directory / "response.json")
                if (directory / "response.json").exists()
                else None,
            },
        )
    return 0 if status == "ok" else 1


class ProviderError(ValueError):
    pass


def validate_response(directory, schema=None):
    result = read_json(directory / "worker-result.json")
    if result["request_sha256"] != digest(directory / "request.json"):
        raise ProviderError("Provider request was modified")
    if result["status"] != "ok":
        raise ProviderError(f"Codex call ended with status {result['status']}; inspect its logs")
    path = directory / "response.json"
    if (
        not path.is_file()
        or path.stat().st_size > 128_000
        or result["response_sha256"] != digest(path)
    ):
        raise ProviderError("Missing, oversized or modified Codex response")
    response = read_json(path)
    if schema is not None:
        from jsonschema import validate

        validate(response, schema)
    elif (
        not isinstance(response, dict)
        or set(response) != set(SCHEMA["required"])
        or any(not isinstance(value, str) for value in response.values())
        or not response["program"].strip()
        or len(response["program"].encode()) > 64_000
    ):
        raise ProviderError("Codex response does not match the proposal contract")
    events_path = directory / "events.jsonl"
    if events_path.stat().st_size > 10_000_000:
        raise ProviderError("Codex event log is too large")
    usage = None
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        item = event.get("item", {})
        if item.get("type") in {
            "command_execution",
            "file_change",
            "mcp_tool_call",
            "web_search",
            "tool_call",
        }:
            raise ProviderError("Code generator invoked a tool; proposal is quarantined")
        if event.get("type") == "turn.completed":
            usage = event.get("usage")
    return response, {**result, "usage": usage}


def generate(round_dir, prompt, spec, timeout_s, *, schema=None):
    round_dir = Path(round_dir)
    owner = (
        round_dir.parent.name
        + "-"
        + hashlib.sha256(str(round_dir.parent).encode()).hexdigest()[:12]
    )
    directory = Path(spec["exchange_dir"]) / owner / round_dir.name
    directory.mkdir(parents=True, exist_ok=True)
    request = {
        "codex": host_path(spec["codex"], spec["windows"]),
        "directory": host_path(directory, spec["windows"]),
        "prompt": prompt,
        "model": spec["model"],
        "timeout_s": timeout_s,
        "schema_sha256": hashlib.sha256(
            json.dumps(schema or SCHEMA, sort_keys=True).encode()
        ).hexdigest(),
    }
    request_path = directory / "request.json"
    if request_path.exists() and read_json(request_path) != request:
        raise ProviderError("A different generation already uses this exchange directory")
    if not request_path.exists():
        write_json(request_path, request)
        write_json(directory / "schema.json", schema or SCHEMA)
    terminal = directory / "worker-result.json"
    if not terminal.exists():
        if (directory / "launch-started.json").exists():
            raise ProviderError(
                "Previous Codex call is pending; wait for worker-result.json before resuming"
            )
        write_json(directory / "launch-started.json", {"request_sha256": digest(request_path)})
        command = [
            spec["host_python"],
            host_path(__file__, spec["windows"]),
            "--worker",
            host_path(request_path, spec["windows"]),
        ]
        with (directory / "launcher.log").open("wb") as log:
            process = subprocess.Popen(command, stdout=log, stderr=log)
            try:
                process.wait(timeout=timeout_s + 30)
            except (KeyboardInterrupt, subprocess.TimeoutExpired):
                (directory / "cancel").touch()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise
    for name in (
        "request.json",
        "schema.json",
        "prompt.txt",
        "worker-started.json",
        "worker-result.json",
        "worker-error.json",
        "events.jsonl",
        "stderr.log",
        "response.json",
        "launcher.log",
    ):
        path = directory / name
        if path.exists():
            target = round_dir / "model" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    if not terminal.exists():
        raise ProviderError("Codex worker did not produce a terminal record")
    return validate_response(round_dir / "model", schema=schema)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path, required=True)
    raise SystemExit(worker(parser.parse_args().worker))
