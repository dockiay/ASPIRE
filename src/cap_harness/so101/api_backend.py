"""Responses-compatible controller using the exact same audited tools as Codex.

Credentials are read from a named environment variable at request time, never
saved in configuration, request journals, telemetry or session identities.
"""

import base64
import copy
import json
import os
from pathlib import Path
import time
from urllib.parse import urlparse

import requests

from cap_harness.so101 import campaign as c
from cap_harness.so101.debug_mcp import DESCRIPTIONS, SCHEMAS
from cap_harness.so101.debug_tools import DebugTools


def provider_spec(config):
    allowed = {"type", "model", "base_url", "api_key_env", "max_output_tokens", "request_timeout_s"}
    if set(config) - allowed or config.get("type") != "api":
        raise ValueError("Invalid API controller configuration")
    model = config.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Configure an explicit API model")
    base = config.get("base_url", "https://api.openai.com/v1").rstrip("/")
    url = urlparse(base)
    if (
        url.username
        or url.password
        or url.query
        or url.fragment
        or (
            url.scheme != "https"
            and not (url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1"))
        )
    ):
        raise ValueError("Use HTTPS, or a local HTTP API; credentials must not appear in the URL")
    key_env = config.get("api_key_env", "OPENAI_API_KEY")
    if not isinstance(key_env, str) or not key_env.isidentifier():
        raise ValueError("api_key_env must name an environment variable")
    tokens = config.get("max_output_tokens", 16000)
    timeout = config.get("request_timeout_s", 180)
    if type(tokens) is not int or not 256 <= tokens <= 100000 or not 1 <= timeout <= 600:
        raise ValueError("Invalid API output budget or timeout")
    return {
        "type": "api",
        "protocol": "responses",
        "model": model,
        "base_url": base,
        "api_key_env": key_env,
        "max_output_tokens": tokens,
        "request_timeout_s": timeout,
    }


def strict_schema(schema):
    """Represent optional MCP fields as required nullable fields on the API wire."""
    value = copy.deepcopy(schema)
    if value.get("type") == "object":
        required = set(value.get("required", []))
        value["properties"] = {
            key: strict_schema(child)
            if key in required
            else {"anyOf": [strict_schema(child), {"type": "null"}]}
            for key, child in value.get("properties", {}).items()
        }
        value["required"] = list(value["properties"])
        value["additionalProperties"] = False
    if "items" in value:
        value["items"] = strict_schema(value["items"])
    return value


def tool_definitions():
    return [
        {
            "type": "function",
            "name": name,
            "description": DESCRIPTIONS[name],
            "strict": True,
            "parameters": strict_schema(
                {
                    "type": "object",
                    "properties": fields,
                    "required": list(fields),
                    "additionalProperties": False,
                }
            ),
        }
        for name, fields in SCHEMAS.items()
    ]


def post(spec, payload, timeout_s):
    key = os.environ.get(spec["api_key_env"])
    if not key:
        raise ValueError("Missing API credential in " + spec["api_key_env"])
    response = requests.post(
        spec["base_url"] + "/responses",
        json=payload,
        headers={"Authorization": "Bearer " + key},
        timeout=min(timeout_s, spec["request_timeout_s"]),
        allow_redirects=False,
    )
    if response.status_code != 200:
        # A provider error body may contain echoed request data; do not log it.
        raise ValueError(f"LLM API returned HTTP {response.status_code}; request journal preserved")
    if len(response.content) > 20_000_000:
        raise ValueError("API response exceeds the controller response limit")
    return response.json()


def run(root, spec, prompt, schema, *, timeout_s=7200, requester=post, service=None):
    """Resume only journaled replies; an indeterminate paid request is never retried."""
    from jsonschema import validate

    root = Path(root)
    if requester is post and not os.environ.get(spec["api_key_env"]):
        raise ValueError("Missing API credential in " + spec["api_key_env"])
    service = service or DebugTools(root)
    directory = root / "model"
    directory.mkdir(exist_ok=True)
    identity = {"provider": spec, "prompt": prompt, "timeout_s": timeout_s, "schema": schema}
    request_path = directory / "request.json"
    if request_path.exists() and c.read_json(request_path) != identity:
        raise ValueError("API controller identity changed")
    c.write_json(request_path, identity)
    transcript = [{"role": "developer", "content": prompt}]
    events = []
    usage_totals = {}
    deadline = time.monotonic() + timeout_s
    for index in range(service.identity["max_calls"] + 16):
        turn = directory / f"turn-{index:04d}"
        turn.mkdir(exist_ok=True)
        payload = {
            "model": spec["model"],
            "input": transcript,
            "tools": tool_definitions(),
            "parallel_tool_calls": False,
            "store": False,
            "include": ["reasoning.encrypted_content"],
            "max_output_tokens": spec["max_output_tokens"],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "aspire_result",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        request_hash = c.canonical_sha256(payload)
        receipt = turn / "request.json"
        if receipt.exists() and c.read_json(receipt)["sha256"] != request_hash:
            raise ValueError("API request history was modified")
        reply_path = turn / "response.json"
        if not reply_path.exists():
            if receipt.exists():
                raise ValueError(
                    "Indeterminate API request; recover its response before resuming; no automatic billing retry"
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("API controller wall-time budget exhausted")
            c.write_json(receipt, {"sha256": request_hash})
            reply = requester(spec, payload, remaining)
            c.write_json(reply_path, reply)
            c.write_json(turn / "response-hash.json", {"sha256": c.file_sha(reply_path)})
        if c.read_json(turn / "response-hash.json")["sha256"] != c.file_sha(reply_path):
            raise ValueError("API reply was modified")
        reply = c.read_json(reply_path)
        for key, value in (reply.get("usage") or {}).items():
            if isinstance(value, int) and not isinstance(value, bool):
                usage_totals[key] = usage_totals.get(key, 0) + value
        if reply.get("status", "completed") != "completed":
            raise ValueError("API response incomplete; inspect the saved reply")
        output = reply.get("output", [])
        transcript.extend(output)
        calls = [item for item in output if item["type"] == "function_call"]
        if not calls:
            raw = "".join(
                part.get("text", "")
                for item in output
                if item["type"] == "message"
                for part in item.get("content", [])
            )
            final = json.loads(raw)
            validate(final, schema)
            if not (root / "finish.json").is_file():
                raise ValueError("Controller returned before finishing the tool workflow")
            c.write_json(directory / "response.json", final)
            events.append({"type": "turn.completed", "usage": usage_totals})
            (directory / "events.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
            )
            c.write_json(
                directory / "worker-result.json",
                {
                    "status": "ok",
                    "request_sha256": c.file_sha(request_path),
                    "response_sha256": c.file_sha(directory / "response.json"),
                    "provider": "api",
                },
            )
            return
        for call_index, call in enumerate(calls):
            name = call["name"]
            if name not in SCHEMAS:
                raise ValueError("Unapproved API tool: " + name)
            arguments = json.loads(call["arguments"])
            if name == "finish_session" and isinstance(arguments.get("skill_report"), dict):
                for group in ("proposed_new", "proposed_edits"):
                    for proposal in arguments["skill_report"].get(group, []):
                        if proposal.get("verification_contract") is None:
                            proposal.pop("verification_contract", None)
            validate(
                arguments,
                {
                    "type": "object",
                    "properties": SCHEMAS[name],
                    "required": list(SCHEMAS[name]),
                    "additionalProperties": False,
                },
            )
            action_path = turn / f"tool-{call_index}.json"
            if action_path.exists():
                action = c.read_json(action_path)
                if action["name"] != name or action["arguments"] != arguments:
                    raise ValueError("API tool journal differs from reply")
                service.audit_images(action)
            else:
                pending = turn / f"tool-{call_index}-started.json"
                if pending.exists():
                    raise ValueError(
                        "Indeterminate tool call; audit its tool receipt before resuming"
                    )
                c.write_json(pending, {"name": name, "arguments": arguments})
                value, images = service.call(name, arguments)
                action = {
                    "name": name,
                    "arguments": arguments,
                    "result": value,
                    "images": [
                        {"path": str(path.relative_to(root)), "sha256": c.file_sha(path)}
                        for path in images
                    ],
                }
                c.write_json(action_path, action)
            events.append(
                {
                    "type": "item.completed",
                    "item": {"type": "function_tool_call", "server": "so101", "tool": name},
                }
            )
            content = [{"type": "input_text", "text": json.dumps(action["result"])}]
            for image in action["images"]:
                content.append(
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64,"
                        + base64.b64encode((root / image["path"]).read_bytes()).decode(),
                    }
                )
            transcript.append(
                {"type": "function_call_output", "call_id": call["call_id"], "output": content}
            )
    raise ValueError("API controller request budget exhausted")
