"""Opt-in native compaction; original response/tool journals stay authoritative.

Let the provider compact reasoning and completed tool exchanges together rather
than truncating individual calls, images, or encrypted reasoning items locally.
Configuration validation lives in the stdlib-only Windows Codex worker as well.
"""

import copy

from cap_harness.so101.codex_backend import history_configuration as configuration


def responses_input(transcript, value):
    """Keep native compaction and everything after it, plus original instructions.

    Without explicit opt-in, preserve the original wire input. Never manufacture
    a summary or remove recent reasoning/function-call items individually.
    """
    if configuration(value) is None:
        return copy.deepcopy(transcript)
    last = next(
        (
            index
            for index in range(len(transcript) - 1, -1, -1)
            if transcript[index].get("type") == "compaction"
        ),
        None,
    )
    if last is None:
        return copy.deepcopy(transcript)
    # A provider may compact after proposing a call but before the host has
    # supplied its output. Keep the full exchange if it straddles the marker;
    # dropping its call would leave an orphan tool output on the wire.
    older_calls = {
        item.get("call_id")
        for item in transcript[:last]
        if item.get("type") in ("function_call", "custom_tool_call")
    }
    if any(
        item.get("type") in ("function_call_output", "custom_tool_call_output")
        and item.get("call_id") in older_calls
        for item in transcript[last:]
    ):
        return copy.deepcopy(transcript)
    instructions = [
        item for item in transcript[:last] if item.get("role") in ("system", "developer")
    ]
    return copy.deepcopy([*instructions, *transcript[last:]])


def add_usage(total, usage):
    """Sum provider counters recursively; absent details remain unavailable."""
    for key, value in (usage or {}).items():
        if isinstance(value, dict):
            child = total.setdefault(key, {})
            if not isinstance(child, dict):
                raise ValueError("Provider changed the shape of a usage counter")
            add_usage(child, value)
        elif type(value) is int:
            if value < 0:
                raise ValueError("Provider returned a negative usage counter")
            total[key] = total.get(key, 0) + value
    return total
