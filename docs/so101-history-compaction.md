# Native history compaction for SO-101 controllers

Long controller sessions repeatedly submit old tool results, images and reasoning.
An optional `history_compaction` setting asks the selected provider to compact
that state before it reaches the provider's usual context limit.

```json
"history_compaction": {"token_limit": 32000}
```

The setting works in both controller configuration formats. Omit it to retain
the previous behavior: full stateless input replay for the API controller, and
the model/CLI defaults for Codex. The accepted range is 4,096–200,000 integer
tokens. The threshold is a trigger, not a hard context or spending limit.

## Provider behavior

- **Codex with saved ChatGPT authentication:** the native worker passes
  `model_auto_compact_token_limit` to the CLI. Both generator and controlled MCP
  worker requests freeze this option in their existing request identity.
- **Responses-compatible API:** the controller sends `context_management` with
  `type=compaction` and `compact_threshold`. When a native compaction item is
  returned, subsequent requests keep that item and all subsequent items, together
  with the original system/developer instructions. A tool exchange crossing the
  compaction boundary is retained whole. A provider must support this opt-in
  Responses extension; compatibility with ordinary Responses calls is insufficient.

No local text summary is substituted for encrypted reasoning. The provider owns
the compressed representation; this is not the paper's exact four-turn/2,000-token
rolling-summary protocol. A smaller threshold may increase compaction overhead
or lose useful context, so it needs measurement on the intended workload.

The full original response and tool journals, image hashes, request hashes and
indeterminate-call protection remain in place. Resuming audits and reconstructs
the same requests without repeating completed model requests or physical actions.
Changing the compaction policy requires a new session directory, as with other
provider configuration changes.

## Measurement

API `model/events.jsonl` now retains nested usage counters, including
`input_tokens_details.cached_tokens` and `output_tokens_details.reasoning_tokens`
when supplied. `model/context-usage.json` records request/item counts and observed
compaction items. Item counts are not token estimates. Missing counters remain
unavailable rather than being invented as zero. Codex keeps its original
`turn.completed.usage` counters, including cached input, in the worker event log.

Input includes cached input; reasoning output is generally a subset of output.
Do not add these detail counters to their parent totals. Report input, cached
input, uncached input, output, total and elapsed time separately. A reduction in
total tokens is not the same percentage reduction in API cost. Saved ChatGPT
authentication does not provide an API invoice.

## Reproducible context/control regression

Install the `agent` extra and use a Codex executable already logged in with
`codex login`. No API credential or credential-file access is needed.

```powershell
.venv-dev\Scripts\python.exe scripts\benchmark_so101_history.py `
  --output outputs/history-comparison/pair-a `
  --codex C:/path/to/codex.exe --token-limit 24000
```

The paired test uses the same six synthetic diagnostic pages and initial task
under two conditions: the existing provider defaults and native compaction.
It deliberately includes long numerical logs to stress context retention. The
model must read every page, retain the original public control specification,
diagnose an unmet grasp prerequisite and refrain from claiming harvest success.
The only enabled tool reads fixture evidence; shell, web and delegation are
disabled. Local read-only fixture approval is explicitly scoped to that tool.

The generated programs can then be tested in Linux/WSL using the existing
simulator installation and the pinned SO-101 assets:

```bash
cd /mnt/d/AI/Aspire-framework
export PYTHONPATH="$PWD/src"
export CAP_HARNESS_SO101_WORKSPACE="$PWD"
export CAP_HARNESS_SO101_MODEL_ROOT="$PWD/third_party/so_arm100"
export MUJOCO_GL=glfw
export GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA
/path/to/python scripts/benchmark_so101_history.py \
  --evaluate outputs/history-comparison/pair-a/baseline
/path/to/python scripts/benchmark_so101_history.py \
  --evaluate outputs/history-comparison/pair-a/compressed
```

Repeat with `--order compressed baseline` and a new output directory to balance
execution order. Preserve CLI version, model, fixture seed/size and source revision
across each pair. Count all inference, including native compaction overhead.

Aggregate the saved receipts and audit the simulator manifests without making
new model calls:

```powershell
.venv-dev\Scripts\python.exe scripts\benchmark_so101_history.py `
  --report outputs/history-comparison/pair-a outputs/history-comparison/pair-b `
  --output outputs/history-comparison/results.json --baseline-revision BASE_COMMIT
```

The [initial comparison](so101-history-compaction-results.md) records the measured
token reduction, unchanged control outcome, increased latency and scope limits.

This test measures real model token usage and physical **control-task** regression.
It does not estimate strawberry-harvest success, training sample efficiency, or
general performance on LIBERO/RoboDojo. A broader experiment must freeze the
initial skill library and task protocol, repeat multiple learning runs, and
evaluate final programs on disjoint cases. Do not add test outcomes to the model's
training context or infer success from its own completion statement.

References:

- [OpenAI native API compaction](https://developers.openai.com/api/docs/guides/compaction).
- [Codex compaction configuration](https://learn.chatgpt.com/docs/config-file/config-reference).
- [Paper, harness ablations in Table 13](https://arxiv.org/html/2610.22471v2).
