# SO-101 history compaction: initial comparison

Date: 2026-10-26. Baseline: `e763d2256d29b20ace9096a55479bc92353a3f80`
(the previous `codex/mejoras` head). The baseline uses the same Codex command
as that version, without a compaction override. The treatment adds
`history_compaction.token_limit=24000`.

## Results

Two repetitions of the same synthetic diagnostic fixture, ordered A/B then B/A.
All four model-generated programs were executed with the unchanged
`so101_control` MuJoCo evaluator, using measured initial joint positions.

| Metric | Existing defaults | Native compaction |
|---|---:|---:|
| Live model trials | 2 | 2 |
| Input tokens, summed | 573,434 | 259,421 |
| Cached input, included above | 440,832 | 169,216 |
| Uncached input | 132,602 | 90,205 |
| Output tokens | 1,531 | 1,692 |
| Total input + output | **574,965** | **261,113** |
| Mean total tokens per trial | 287,482.5 | 130,556.5 |
| Mean model-worker wall time | **36.23 s** | **95.96 s** |
| All six evidence pages inspected/reported | 2/2 | 2/2 |
| Correctly declined to claim harvest success | 2/2 | 2/2 |
| Generated control program completed successfully | 2/2 | 2/2 |
| Native physical control-task success | 2/2 | 2/2 |
| Simulator control ticks per program | 100 | 100 |

The measured reduction in CLI-reported total tokens was **54.59%**. Uncached
input decreased by **31.97%**, while model-worker wall time increased by about
**2.65 times**. Thus this setting demonstrates a token/latency trade-off, not a
general speed improvement. No dollar cost is inferred from saved ChatGPT login.

Both conditions retained the correct prerequisite diagnosis: unilateral contact
and unverified retention do not evaluate the proposed twisting maneuver, and
program completion does not establish physical harvest success. All four
programs exercised each of the five arm joints, returned to the measured initial
pose, and closed/reopened the jaw under the same native success predicate.

## Scope and reproducibility

- Codex CLI `0.164.0-alpha.11.1`, the same executable and native model default in
  both conditions, with user configuration ignored. There was no model override,
  preserving the previous connector behavior. The server model snapshot was not
  independently pinned.
- Fixture seed 17; six pages, each containing 120 rows of eight synthetic
  numerical measurements, plus a public task specification and failure evidence.
  Identical evidence hashes are checked across each pair.
- Only the local `read_evidence` MCP tool was enabled. It reads fixture data and
  writes its audit receipt; shell, web, plugins, and delegation were disabled.
- MuJoCo 3.3.0 / pinned SO-101 model; source checkout providers; WSLg/GLFW.
  Physics, success predicates, and initial state were unchanged by this PR.
- Raw request/response journals, event logs and native run manifests remain in
  `outputs/history-compression/pair-02` and `pair-03`. The committed
  [machine-readable report](benchmarks/so101-history-compaction-20261026.json)
  preserves the usage counters, trial results, diagnoses and evidence hashes.
- The earlier `pair-01` was an invalid fixture preflight: MCP approval prevented
  reading any page. It is excluded from the comparison. Its logs remain available;
  neither condition produced an evaluable control program in that preflight.

These are **two repetitions of one fixture and one control case**, not a
statistical estimate of general task success. Numerical logs intentionally stress
context growth. No strawberry-harvest learning campaign or held-out harvest cases
were executed. API-native compaction was tested using provider fixtures; live
model trials exercised the saved-login Codex connector.

Codex's JSONL output does not expose native compaction markers in this version,
so the report records the configured threshold and actual usage instead of
inventing a compaction count. The native API path records returned compaction
items explicitly.

The benchmark commands and report aggregation are documented in
[history compaction](so101-history-compaction.md). A broader harvest comparison
should freeze the initial library and model snapshot, repeat complete learning
runs, and compare disjoint final-evaluation cases before promoting this setting
as a default.
