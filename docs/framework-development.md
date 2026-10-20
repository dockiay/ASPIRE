# Framework improvement workspace

This fork is a development base for reducing ASPIRE's inference cost and avoidable
debugging iterations while preserving measured task success and physical checks.
The initial branch adds a development plan; it does not claim an efficiency gain.

## Repository layout

- Fork: <https://github.com/dockiay/ASPIRE>
- Upstream: <https://github.com/NVlabs/ASPIRE>
- Initial upstream revision: `fa00f0ef2bc1d91d594b9aa502c22133c9f538f7`.
- Initial work branch: `codex/framework-improvements`.
- Local checkout: `D:\AI\Aspire-framework`.

Keep general framework changes separate from the existing SO-101 experiments in
`D:\AI\Aspire`. Transfer an experimental change only after reviewing its scope,
dependencies, provenance, and tests. Generated runs, credentials, datasets, model
weights, and virtual environments do not belong in commits.

## Local development

Use Python 3.11. The base package supports Python 3.10 through 3.12; the system
Python on this workstation is newer. The lightweight development environment
does not need simulator submodules, model services, or physical hardware.

Windows PowerShell:

```powershell
uv venv --python 3.11 .venv-dev
uv pip install --python .venv-dev\Scripts\python.exe -e '.[dev,agent]'
.venv-dev\Scripts\python.exe -m pytest tests/test_contracts.py tests/test_api.py tests/test_geometry.py tests/test_runtime.py tests/test_registry.py -q
.venv-dev\Scripts\ruff.exe check src/cap_harness tests
```

On Linux, use `.venv-dev/bin/python` and `.venv-dev/bin/ruff` instead. The
simulation and provider environments have separate Linux/CUDA requirements;
follow [host setup](host-setup.md) and the selected benchmark runbook when needed.
Install only the submodules and providers required by that experiment.

Use a separate `codex/` branch for each concrete implementation. Refresh upstream
with `git fetch upstream`, review its changes, and base new work on the intended
revision. `origin` is the push destination; `upstream` is the reference repository.
The local configuration uses fast-forward-only pulls.

## Initial improvement queue

| Order | Change | Evidence required before accepting it |
| --- | --- | --- |
| 1 | Account for model input, cached input, output, and any separately reported reasoning usage by task and stage. Record calls, wall time, rollouts, and verified progress as well. | Totals reconcile with provider usage; missing usage stays unknown; retries and failures are included without double counting. |
| 2 | Make execution acceptance, motion completion, planning validity, and physical outcome unambiguous in tool results. Check generated programs against those contracts before expensive execution. | Existing clients remain compatible or receive an explicit migration; confusing an execution flag with a physical predicate is detected. |
| 3 | Focus search on the earliest unresolved prerequisite and detect repeated failure signatures. | Later-stage hypotheses are not credited unless exercised; a stalled prerequisite leads to a new diagnosis or an explicit dependency, rather than equivalent retries. |
| 4 | Build a compact, versioned context package from the current contract, verified state, relevant skills, and failure evidence. | Decision-critical evidence remains available; incompatible historical instructions are excluded; token use and task success are compared against the baseline. |
| 5 | Reuse validated skill components and retrieve both successful repairs and relevant failed attempts. | Applicability, robot/API versions, provenance, and independent reproduction are checked; a prior success never substitutes for current physical evidence. |

Start with accounting so later improvements can be evaluated. Add small changes
individually before combining them. Do not increase search breadth or delegate
more agents without measuring the resulting total cost.

## Comparison protocol

Freeze the code revision, tasks, development seed schedule, model settings, API
contracts, skill-library snapshot, services, and budget for each comparison.
Record environment changes explicitly. Use development cases for iteration;
keep validation and held-out evaluation separate and do not tune on their results.
Changing the search protocol creates a new experiment rather than rewriting an
upstream reproduction.

Report task success together with total cost, time, rollouts, repeated failures,
and newly verified physical predicates. Include failed and budget-exhausted tasks
in the comparison. Separate one-time skill discovery from repeated execution cost.
Track cached tokens separately; calculate monetary cost only when applicable
provider pricing is recorded. Set-level success still requires every relevant
object or predicate to be accounted for.

Use deterministic checks for schema, integrity, provenance hashes, and duplicate
work where possible. Retain independent behavioral verification. Any future
hardware experiment uses the registered native CAP tools and the repository's
[robot execution instructions](../AGENTS.md).

## Baseline checks

Initial results on 2026-10-20, Windows, CPython 3.11.9, pytest 9.1.1, Ruff 0.17.1:

- The five core test files listed above: **118 passed** in 5.73 seconds.
- `ruff check src/cap_harness tests`: **passed**.
- `git diff --check`: **passed**.
- Package installed in editable mode with the `dev` and `agent` extras.

Dependencies were resolved for this local environment using `uv pip install`;
this is not a reproduction of the Linux-only `uv.lock` environment. Core unit
tests establish an engineering baseline; they do not establish simulation
benchmark success, efficiency gains, or real-robot readiness.
