"""STDIO MCP transport for the SO-101 development tool boundary."""

import argparse
import asyncio
import base64
import json
import os
from pathlib import Path

from cap_harness.so101.debug_tools import TOOLS, DebugTools
from cap_harness.so101.skills import REPORT_SCHEMA

SCHEMAS = {
    "describe_task": {},
    "explore_scene": {},
    "execute_program": {
        "code": {"type": "string"},
        "hypothesis": {"type": "string"},
        "provenance": {"type": "string"},
    },
    "inspect_results": {"candidate_id": {"type": "string"}},
    "view_frame": {
        "candidate_id": {"type": "string"},
        "case_index": {"type": "integer"},
        "camera": {"type": "string", "enum": ["agentview", "sideview"]},
        "frame_index": {"type": "integer", "minimum": 0},
    },
    "finish_session": {
        "candidate_id": {"type": "string"},
        "analysis": {"type": "string"},
        "skill_report": REPORT_SCHEMA,
    },
}
DESCRIPTIONS = {
    "describe_task": "Read the SO-101 task, public API, budget and development-only workflow.",
    "explore_scene": "Observe the initial public scene and robot/contact state; returns both camera images without stepping. Cached after first observation.",
    "execute_program": "Run one new public Python candidate on ALL assigned development cases. Identical code is cached. State hypothesis and runtime public provenance. Cannot run held-out seeds.",
    "inspect_results": "Read audited execution errors, filtered physical diagnoses, final finger forces and event frame references. No hidden object state or junction parameters.",
    "view_frame": "View one audited video frame by candidate, case index, allowed camera and frame index. Returns actual image content, no arbitrary filesystem paths.",
    "finish_session": "Close with the best experimental candidate after inspecting results and a frame. Does not certify provenance, promote skills, or run reserved evaluation.",
}


async def serve(root):
    from jsonschema import validate
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import CallToolResult, ImageContent, TextContent, Tool, ToolAnnotations

    service = DebugTools(root)
    server = Server(
        "so101",
        version="0.1.0",
        instructions=(
            "Simulation only, development only. Describe then explore once. Generate without prior policies; derive targets at runtime through public APIs. Execute candidates on all assigned cases, inspect failures and view images before revising. No native object/evaluator state or reserved evaluation. Provenance remains PENDING."
        ),
    )
    mutex = asyncio.Lock()

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name=name,
                description=DESCRIPTIONS[name],
                inputSchema={
                    "type": "object",
                    "properties": SCHEMAS[name],
                    "required": list(SCHEMAS[name]),
                    "additionalProperties": False,
                },
                annotations=ToolAnnotations(
                    readOnlyHint=name in ("describe_task", "inspect_results", "view_frame"),
                    destructiveHint=False,
                    openWorldHint=False,
                ),
            )
            for name in TOOLS
        ]

    @server.call_tool()
    async def call_tool(name, arguments):
        async with mutex:
            try:
                if name not in SCHEMAS:
                    raise ValueError("Unknown SO101 tool")
                validate(
                    arguments,
                    {
                        "type": "object",
                        "properties": SCHEMAS[name],
                        "required": list(SCHEMAS[name]),
                        "additionalProperties": False,
                    },
                )
                value, images = await asyncio.to_thread(service.call, name, arguments)
            except Exception as exc:
                value, images = {"ok": False, "error": str(exc)[:1600]}, []
            content = [TextContent(type="text", text=json.dumps(value, ensure_ascii=False))]
            content.extend(
                ImageContent(
                    type="image",
                    data=base64.b64encode(p.read_bytes()).decode(),
                    mimeType="image/png",
                )
                for p in images
            )
            return CallToolResult(content=content, isError=value.get("ok") is False)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    # Apply render configuration before importing any native simulator bindings.
    from cap_harness.so101 import campaign as c

    runtime = c.read_json(args.workspace / "session.json")["runtime"]
    for key in ("PYOPENGL_PLATFORM", "EGL_PLATFORM", "MUJOCO_EGL_DEVICE_ID"):
        os.environ.pop(key, None)
    for key, value in runtime["environment"].items():
        if value is not None:
            os.environ[key] = value
    asyncio.run(serve(args.workspace))


if __name__ == "__main__":
    main()
