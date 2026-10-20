---
name: iterative-debugging-so101
description: Adapt ASPIRE iterative debugging, reserved evaluation and verified skills to SO-101 strawberry simulation with Codex or a Responses-compatible API.
---

# SO-101 strawberry ASPIRE profile

Use benchmark `so101`, suite `so101_fruitgym_harvest`, task 0.
The complete task is harvest, retain, carry and deposit the same fruit in one
episode. The controller owns its policy and corrections. Supply no baseline
program, offline waypoints, grasp pose or harvesting phase recipe.

## Coordinator protocol

Use the existing ASPIRE worker sequence and independent verification protocol,
with the SO-101 adapter `python -m cap_harness.so101.pipeline --output PATH`.
The adapter uses the native audited campaign runner, immutable selected source,
canonical skill-report validator and canonical progress artifact format.

1. Freeze protocol/runtime, applicable library, budgets and selection rule.
2. Start a clean controlled worker using [agent-prompt.md](agent-prompt.md).
   Observe the first development scene once without stepping. Generate a full
   program from public observations. Score every version on all development
   cases. Inspect errors and images before revising; group by failure mode.
3. Independently audit exact code, constants, prompt and public trace. A hash,
   tool audit, self-report or AST acceptance alone does not establish provenance.
   Quarantine a selection with uncertain/invalid provenance.
4. Freeze the selected program before the unseen-check. Measure it once on the
   complete registered validation partition; do not return its failures to the
   worker. Mark `stage1-done` only after these prerequisites.
5. The coordinator executes all final evaluation cases with identical source,
   protocol, runtime and limits. Mark the experimental process `done` when the
   full results exist. Report physical success separately.
6. For actual skill proposals, run a fresh verifier outside the proposer tree,
   with library/proposals and public observations only, never proposer code.
   Use at most two candidates on the first two development cases. Independently
   audit provenance and actual application of the named skill. Proposals may
   name a registered verification_contract. Those are checked individually on
   their exact predicates; skill_success is separate from full task_success.
   Promote only if all assigned cases pass that criterion, the proposed library
   hash matches, and independent review confirms application. Unscoped legacy
   proposals retain the full-harvest gate. Do not weaken the harvest benchmark.
7. Preserve source hashes, spent budgets and native artifacts on resume.
   An indeterminate paid/model/tool request requires recovery of its receipt;
   never automatically resubmit it. A source/protocol/runtime change starts a
   new campaign. A later library-based rerun is a separately labeled campaign;
   cases already measured must not be described as newly unseen.

## Environment and cases

- Linux/WSL, installed `.venv-robosuite`, WSLg/GLFW with D3D12 on this PC.
  Do not copy generic EGL settings. No physical robot is connected.
- Protocol: `configs/so101/fruitgym-harvest-v2.json`.
  Development 0/1001/1002, unseen-check 2001/2002, final evaluation
  3001/3002/3003. These are small synthetic variations of plant/container
  translation, release load and contact friction; not independent real plants.
- Dev0 is also the historical integration reference. Do not combine v1 results
  with v2 metrics or reuse the old detachment experiment's cases/results.
- Five-axis robot-only IK and joint interpolation are shared ASPIRE providers.
  Arbitrary 6D poses may be unreachable; handle typed failures explicitly.
- `so101.check_joint_path` checks robot limits, nominal self/table contacts and
  conservative mesh boxes against supplied PUBLIC obstacle points. Occluded
  geometry and space between samples remain uncertified.
- The full benchmark defaults to ASPIRE SAM3 semantic segmentation on public RGB,
  followed by shared RGB-D projection. Preflight pins checkpoint/code/threshold
  before controller calls. No silent color fallback. Color-rgbd is an explicit
  separate baseline; the legacy red localizer is disabled under SAM3. Confidence,
  ambiguity and missing depth are observations, not native object truth. Visible
  surfaces do not determine complete object shape or persistent identity.
- Fingertip force sensing is virtual. The angular jaw is not symmetric about
  the TCP: use public effector geometry. Supervised gripper commands check
  substeps, report peaks and stop reasons. Read actual results.

## Controller choice

Both controllers operate the same six audited tools:
`describe_task`, `explore_scene`, `execute_program`, `inspect_results`,
`view_frame`, `finish_session`.

Codex uses the native MCP transport and saved login. API mode uses a
Responses-compatible function/vision transport for that exact tool boundary.
Choose through `--controller-config`; the model is explicit in API config.
Read credentials from the named environment variable; never store secret values
in configuration or artifacts. See [operator guide](../../../../../docs/so101-iterative-debugging.md).

Only the coordinator owns partitions, runtime identities, review and promotion.
The worker has no shell, source, arbitrary filesystem, hidden geometry, seed
selection, reward/success sensor or reserved case access. Programs derive targets
at runtime. Generic relative tolerances must have a stated source and purpose.
Legacy `plan_open_approach` stays restricted to explicit approach-only demos.

## Skills and evidence

Supply a frozen library snapshot and its hash, initially empty if appropriate.
The worker authors the canonical `skill_report`: `skill_library_sha`,
`consulted`, `proposed_edits`, `proposed_new`, with candidate references for
proposals. Empty proposals are an honest outcome. Never synthesize a learned
skill from storing a failed program.

Registered contracts include read-only ripe-fruit localization (20 mm absolute
center tolerance, 10 mm displacement error across scenes, correct frame/time,
successful public RGB-D calls and zero control steps), qualified grasp,
mechanical release, retention, carry, placement and complete harvest. The
coordinator supplies authoritative criteria through describe_task. For an
explicit partial learning exercise use cap_harness.so101.skill_learning; that
assignment overrides the full-harvest stopping rule. The worker still owns the
program and reusable snippet. Never supply a host-written localization policy.

Runtime policies see public sensors, robot state and bounded actions only.
Post-episode reports may expose physical findings, event times, active commands,
contact pairs and force measurements, while filtering native poses, private
release thresholds and solver loads. Images alone do not prove grasp or success.

The original `so101_strawberry_detachment_cases` suite remains a historical
engineering experiment with its own protocol. Physical calibration, sensing and
transfer to an actual SO-101 are separate subsequent work.
