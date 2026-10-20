"""Deterministic loop tests; Codex and simulation are fakes unless a worker is explicitly tested."""

import json
import sys

import pytest

from cap_harness.so101 import campaign as c
from cap_harness.so101 import codex_backend as b
from cap_harness.so101 import learning

LIMITS = {"max_steps": 800, "timeout_s": 180.0, "max_attempts": 2, "width": 160, "height": 120}
INITIAL = "result = 0\n"
CONTEXT = "Public SO-101 API context."


def identity(rounds=2):
    return learning.build_identity(
        INITIAL, CONTEXT, [101, 102], LIMITS, {"runtime": "fake"}, {"provider": "fake"}, rounds, 30
    )


def fake_evaluator(directory, code, ident, env):
    count = min(2, int(code.strip().split("=")[-1]))
    return {
        "task_success": count,
        "program_ok": 2,
        "planned": 2,
        "cases": [{"task_success": index < count} for index in range(2)],
    }


def test_real_feedback_drives_next_proposal_and_resume_does_not_regenerate(tmp_path):
    prompts = []

    def generator(directory, prompt, spec, timeout_s):
        prompts.append(prompt)
        return {
            "program": f"result = {len(prompts)}\n",
            "analysis": "Use feedback",
            "change_summary": "Correction",
        }, {}

    first = learning.run_learning(
        tmp_path,
        identity(),
        INITIAL,
        CONTEXT,
        {},
        round_budget=1,
        generator=generator,
        evaluator=fake_evaluator,
    )
    assert first["status"] == "paused" and first["model_proposals"] == 1
    complete = learning.run_learning(
        tmp_path, identity(), INITIAL, CONTEXT, {}, generator=generator, evaluator=fake_evaluator
    )
    assert complete["status"] == "selected_cases_passed"
    assert complete["model_proposals"] == 2 and complete["best"]["round"] == 2
    assert '"task_success": 0' in prompts[0]
    assert '"previous_program": "result = 1\\n"' in prompts[1]
    assert '"task_success": 1' in prompts[1]
    learning.run_learning(
        tmp_path, identity(), INITIAL, CONTEXT, {}, generator=generator, evaluator=fake_evaluator
    )
    assert len(prompts) == 2
    assert (tmp_path / "best.py").read_text() == "result = 2\n"
    assert complete["reserved_cases_executed"] is False


def test_invalid_policy_is_not_executed_and_is_returned_for_correction(tmp_path):
    prompts, evaluated = [], []

    def generator(directory, prompt, spec, timeout_s):
        prompts.append(prompt)
        return {
            "program": "import os\n" if len(prompts) == 1 else "result = 2\n",
            "analysis": "Fix API violation",
            "change_summary": "Public code",
        }, {}

    def evaluator(*args):
        evaluated.append(args[1])
        return fake_evaluator(*args)

    result = learning.run_learning(
        tmp_path, identity(), INITIAL, CONTEXT, {}, generator=generator, evaluator=evaluator
    )
    assert result["rounds"][1]["status"] == "rejected"
    assert "program_rejected" in prompts[1] and "Import of 'os'" in prompts[1]
    assert evaluated == [INITIAL, "result = 2\n"]


def test_declining_or_tied_candidate_does_not_replace_best_and_budget_is_finite(tmp_path):
    def generator(*args):
        return {"program": "result = 0\n", "analysis": "No gain", "change_summary": "Tie"}, {}

    result = learning.run_learning(
        tmp_path, identity(), INITIAL, CONTEXT, {}, generator=generator, evaluator=fake_evaluator
    )
    assert result["status"] == "budget_exhausted" and result["model_proposals"] == 2
    assert result["best"]["round"] == 0


def test_complete_requires_successful_execution_as_well_as_physical_success():
    assert not learning.complete({"task_success": 2, "program_ok": 1}, 2)
    assert learning.complete({"task_success": 2, "program_ok": 2}, 2)


def test_tampered_finished_proposal_rejected_on_resume(tmp_path):
    def generator(*args):
        return {"program": "result = 1\n", "analysis": "a", "change_summary": "b"}, {}

    learning.run_learning(tmp_path, identity(), INITIAL, CONTEXT, {}, 1, generator, fake_evaluator)
    (tmp_path / "round-001/candidate.py").write_text("result = 2\n")
    with pytest.raises(ValueError, match="modified"):
        learning.run_learning(
            tmp_path,
            identity(),
            INITIAL,
            CONTEXT,
            {},
            generator=generator,
            evaluator=fake_evaluator,
        )


@pytest.mark.parametrize(
    "code", ["import os", "state._env", "for _ in range(3): pass", "from math import sin"]
)
def test_policy_validation_reuses_aspire_restrictions(code):
    with pytest.raises(ValueError):
        learning.validate_program(code)


def test_reserved_seeds_and_changed_identity_rejected(tmp_path):
    with pytest.raises(ValueError, match="partition"):
        learning.build_identity(INITIAL, CONTEXT, [1], LIMITS, {}, {}, 2, 30)
    ident = identity()
    with c.campaign_lock(tmp_path):
        learning.prepare(tmp_path, ident, INITIAL, CONTEXT)
    changed = {**ident, "max_rounds": 3}
    with pytest.raises(ValueError, match="identity changed"):
        learning.run_learning(tmp_path, changed, INITIAL, CONTEXT, {}, evaluator=fake_evaluator)


def test_feedback_omits_hidden_parameters_seeds_and_native_object_state(tmp_path):
    directory = tmp_path / "attempt/episodes/run-one/evaluation"
    directory.mkdir(parents=True)
    diagnosis = {
        "status": "failed",
        "case": {"seed": 109, "bent_force_n": 5.10},
        "last_attached_junction_state": {"load_n": 4.454, "reaction_on_fruit_n": [1, 2, 3]},
        "findings": [
            {
                "code": "unexpected_support",
                "message": "Contact",
                "time_s": 18,
                "phase": "free_retention",
            }
        ],
        "events": [
            {
                "code": "unexpected_support",
                "time_s": 18,
                "phase": "free_retention",
                "detail": {"contact_pair": ["plant_fruit", "plant_peduncle"], "secret": 42},
            }
        ],
        "final_state": {
            "fruit_position_m": [1, 2, 3],
            "current_retention_s": 0.0,
            "gripper_opening": 0.25,
        },
    }
    c.write_json(directory / "so101-diagnostics.json", diagnosis)
    summary = {
        "partition": "development",
        "complete": True,
        "cases": [
            {
                "seed": 109,
                "attempts": [{"directory": "attempt"}],
                "episode": {
                    "run": "episodes/run-one",
                    "program_ok": True,
                    "task_success": False,
                    "termination_reason": "program_completed",
                    "execution_error": None,
                    "steps_executed": 591,
                },
            }
        ],
    }
    feedback = learning.feedback_for(tmp_path, summary)
    serialized = json.dumps(feedback)
    for forbidden in (
        "bent_force_n",
        "reaction_on_fruit_n",
        "fruit_position_m",
        "secret",
        '"seed"',
    ):
        assert forbidden not in serialized
    assert feedback["cases"][0]["events"][0]["contact_pair"] == ["plant_fruit", "plant_peduncle"]
    summary["partition"] = "evaluation"
    with pytest.raises(ValueError, match="development"):
        learning.feedback_for(tmp_path, summary)


@pytest.fixture
def fake_codex(tmp_path):
    path = tmp_path / "fake-codex"
    path.write_text("""#!/usr/bin/env python3
import json, os, pathlib, sys, time
if '--version' in sys.argv:
    print('fake-codex 1'); sys.exit(0)
if 'login' in sys.argv:
    print('Logged in using ChatGPT'); sys.exit(0)
prompt = sys.stdin.read()
if 'TIMEOUT_PROBE' in prompt:
    time.sleep(10)
if 'TOOL_PROBE' in prompt:
    print(json.dumps({'type':'item.completed','item':{'type':'mcp_tool_call'}}), flush=True)
response = {'analysis':str('OPENAI_API_KEY' not in os.environ), 'change_summary':'Fake only', 'program':'result = 1\\n'}
output = pathlib.Path(sys.argv[sys.argv.index('--output-last-message') + 1])
output.write_text(json.dumps(response))
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':10,'output_tokens':5}}))
""")
    path.chmod(0o755)
    return path


def spec_for(fake_codex, tmp_path):
    return {
        "codex": str(fake_codex),
        "host_python": sys.executable,
        "windows": False,
        "model": None,
        "exchange_dir": str(tmp_path / "exchange"),
    }


def test_native_worker_generation_is_cached_audited_and_has_no_api_key(
    tmp_path, fake_codex, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-sentinel")
    directory = tmp_path / "loop/round-001"
    directory.mkdir(parents=True)
    spec = spec_for(fake_codex, tmp_path)
    proposal, telemetry = b.generate(directory, "Return a public program", spec, 5)
    assert proposal["program"] == "result = 1\n" and proposal["analysis"] == "True"
    assert telemetry["usage"]["output_tokens"] == 5
    first = c.file_sha(directory / "model/worker-result.json")
    b.generate(directory, "Return a public program", spec, 5)
    assert c.file_sha(directory / "model/worker-result.json") == first
    (directory / "model/response.json").write_text("changed")
    with pytest.raises(b.ProviderError, match="modified"):
        b.validate_response(directory / "model")


@pytest.mark.parametrize("prompt", ["TIMEOUT_PROBE", "TOOL_PROBE"])
def test_native_worker_timeout_or_tool_use_is_rejected(tmp_path, fake_codex, prompt):
    directory = tmp_path / "loop/round-001"
    directory.mkdir(parents=True)
    with pytest.raises(b.ProviderError):
        b.generate(
            directory, prompt, spec_for(fake_codex, tmp_path), 0.4 if "TIMEOUT" in prompt else 5
        )
    assert (directory / "model/worker-result.json").is_file()


def test_codex_command_disables_side_effect_tools_and_uses_saved_auth(tmp_path):
    args = b.codex_command({"directory": str(tmp_path), "codex": "codex", "model": None})
    assert "--ignore-user-config" in args and "read-only" in args
    assert all(flag in args for flag in ("shell_tool", "apps", "plugins", "hooks", "multi_agent"))
    assert "--model" not in args and args[-1] == "-"
