"""Compaction must preserve instruction priority, complete exchanges and audit replay."""

import copy
import json
from types import SimpleNamespace

import pytest

from cap_harness.so101 import api_backend, codex_backend
from cap_harness.so101.history import add_usage, configuration, responses_input


@pytest.mark.parametrize(
    "value",
    [
        True,
        8192,
        {},
        {"token_limit": True},
        {"token_limit": 4095},
        {"token_limit": 200001},
        {"token_limit": 8192.0},
        {"token_limit": 8192, "summary": "unsafe"},
    ],
)
def test_configuration_rejects_ambiguous_or_invalid_policies(value):
    with pytest.raises(ValueError, match="history_compaction"):
        configuration(value)


def test_native_window_keeps_instructions_and_whole_recent_tool_exchange():
    recent = [
        {"type": "reasoning", "encrypted_content": "opaque-reasoning"},
        {"type": "function_call", "call_id": "c", "name": "view_frame", "arguments": "{}"},
        {
            "type": "function_call_output",
            "call_id": "c",
            "output": [{"type": "input_image", "image_url": "data:image/png;base64,original"}],
        },
    ]
    compact = {"type": "compaction", "encrypted_content": "provider-state"}
    transcript = [
        {"role": "developer", "content": "Physical guards and original goal"},
        {"role": "assistant", "content": "old"},
        {"type": "compaction", "encrypted_content": "older-state"},
        {"role": "assistant", "content": "another old exchange"},
        compact,
        *recent,
    ]
    original = copy.deepcopy(transcript)
    assert responses_input(transcript, None) == original
    window = responses_input(transcript, {"token_limit": 8192})
    assert window == [transcript[0], compact, *recent]
    window[-1]["output"].clear()
    assert transcript == original


def test_codex_only_overrides_threshold_when_explicitly_configured():
    request = {"directory": "/tmp/worker", "codex": "codex"}
    assert not any("auto_compact" in arg for arg in codex_backend.codex_command(request))
    command = codex_backend.codex_command({**request, "history_compaction": {"token_limit": 12000}})
    assert "model_auto_compact_token_limit=12000" in command
    assert "multi_agent" in command and "shell_tool" in command


def test_compaction_does_not_orphan_an_exchange_crossing_the_boundary():
    transcript = [
        {"role": "developer", "content": "original"},
        {"type": "reasoning", "encrypted_content": "keep-with-call"},
        {"type": "function_call", "call_id": "pending"},
        {"type": "compaction", "encrypted_content": "state"},
        {"type": "function_call_output", "call_id": "pending", "output": "result"},
    ]
    assert responses_input(transcript, {"token_limit": 8192}) == transcript


def test_nested_usage_preserves_cache_and_reasoning_without_double_counting():
    total = {}
    for _ in range(2):
        add_usage(
            total,
            {
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
                "input_tokens_details": {"cached_tokens": 75},
                "output_tokens_details": {"reasoning_tokens": 10},
            },
        )
    assert total == {
        "input_tokens": 200,
        "output_tokens": 40,
        "total_tokens": 240,
        "input_tokens_details": {"cached_tokens": 150},
        "output_tokens_details": {"reasoning_tokens": 20},
    }


def test_api_compaction_replays_original_journals_without_rebilling(tmp_path):
    spec = api_backend.provider_spec(
        {"type": "api", "model": "fixture", "history_compaction": {"token_limit": 8192}}
    )
    requests = []
    calls = []
    service = SimpleNamespace(identity={"max_calls": 4}, audit_images=lambda action: None)
    service.call = lambda name, args: (calls.append(name) or {"ok": True}, [])
    compact = {"type": "compaction", "encrypted_content": "opaque-state"}

    def requester(spec, payload, timeout):
        requests.append(copy.deepcopy(payload))
        assert payload["context_management"] == [{"type": "compaction", "compact_threshold": 8192}]
        index = len(requests) - 1
        if index == 2:
            (tmp_path / "finish.json").write_text("{}")
            output = [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps({"done": True})}],
                }
            ]
        else:
            output = ([compact] if index == 1 else []) + [
                {"type": "reasoning", "encrypted_content": f"r-{index}"},
                {
                    "type": "function_call",
                    "name": "describe_task",
                    "arguments": "{}",
                    "call_id": f"call-{index}",
                },
            ]
        return {
            "status": "completed",
            "output": output,
            "usage": {
                "input_tokens": 100,
                "output_tokens": 10,
                "input_tokens_details": {"cached_tokens": 50},
            },
        }

    schema = {
        "type": "object",
        "properties": {"done": {"type": "boolean"}},
        "required": ["done"],
        "additionalProperties": False,
    }
    api_backend.run(tmp_path, spec, "original rules", schema, requester=requester, service=service)
    assert requests[-1]["input"][0] == {"role": "developer", "content": "original rules"}
    assert requests[-1]["input"][1] == compact
    assert all(item.get("call_id") != "call-0" for item in requests[-1]["input"])
    assert (
        json.loads((tmp_path / "model/turn-0000/response.json").read_text())["output"][1]["call_id"]
        == "call-0"
    )
    usage = json.loads((tmp_path / "model/events.jsonl").read_text().splitlines()[-1])["usage"]
    assert usage["input_tokens"] == 300 and usage["input_tokens_details"]["cached_tokens"] == 150
    before = calls[:]
    api_backend.run(
        tmp_path,
        spec,
        "original rules",
        schema,
        requester=lambda *args: pytest.fail("must reuse saved responses"),
        service=service,
    )
    assert calls == before
    with pytest.raises(ValueError, match="identity changed"):
        api_backend.run(
            tmp_path,
            {**spec, "history_compaction": {"token_limit": 9000}},
            "original rules",
            schema,
            service=service,
            requester=lambda *args: pytest.fail("changed policy must start a new session"),
        )
    path = tmp_path / "model/turn-0001/response.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="modified"):
        api_backend.run(
            tmp_path,
            spec,
            "original rules",
            schema,
            service=service,
            requester=lambda *args: pytest.fail("must not resend"),
        )


def test_compaction_only_response_continues_and_accounts_for_its_usage(tmp_path):
    service = SimpleNamespace(identity={"max_calls": 1})
    spec = api_backend.provider_spec(
        {"type": "api", "model": "fixture", "history_compaction": {"token_limit": 8192}}
    )
    calls = []

    def requester(spec, payload, timeout):
        calls.append(copy.deepcopy(payload))
        if len(calls) == 1:
            output = [{"type": "compaction", "encrypted_content": "native-memory"}]
        else:
            (tmp_path / "finish.json").write_text("{}")
            output = [
                {"type": "message", "content": [{"type": "output_text", "text": '{"done": true}'}]}
            ]
        return {
            "status": "completed",
            "output": output,
            "usage": {"input_tokens": 30, "output_tokens": 5},
        }

    schema = {"type": "object", "properties": {"done": {"type": "boolean"}}, "required": ["done"]}
    api_backend.run(tmp_path, spec, "original", schema, service=service, requester=requester)
    assert len(calls) == 2 and calls[1]["input"][1]["type"] == "compaction"
    events = (tmp_path / "model/events.jsonl").read_text().splitlines()
    assert json.loads(events[-1])["usage"] == {"input_tokens": 60, "output_tokens": 10}
