"""Frozen skill reuse is permitted evidence, never an automatic provenance pass.

All model responses are fixtures. These tests verify the review boundary and
immutable inputs, not whether a real reviewer can recognize correct skill use.
"""

from copy import deepcopy
import hashlib
import json

import pytest

from cap_harness.so101 import campaign as c
from cap_harness.so101 import provenance, skills

SKILL_NAME = "observed-object-grasp.md"
SKILL_TEXT = """# Observed object grasp

Trigger: a public camera identifies the intended object.
Verification contract: grasp_ripe_fruit_v1

```python
observation = get_observation()
# Derive the target from this observation; nunca usar coordenadas guardadas.
```
"""


def library_fixture(tmp_path):
    directory = tmp_path / "library"
    directory.mkdir()
    (directory / SKILL_NAME).write_text(SKILL_TEXT, encoding="utf-8")
    c.write_json(
        directory / "library.json",
        {
            "schema": "so101-skills-v1",
            "skills": {SKILL_NAME: hashlib.sha256(SKILL_TEXT.encode("utf-8")).hexdigest()},
        },
    )
    return skills.snapshot(directory)


def worker_prompt(library):
    return "Public observations only. Permitted frozen skill library:\n" + json.dumps(library)


def refresh_canonical_hash(library):
    library["sha256"] = c.canonical_sha256(
        {
            "manifest": library["manifest"],
            "contents": library["contents"],
        }
    )
    return library


def audit_fixture(tmp_path, library):
    root = tmp_path / "session"
    candidate_id = "c-0123456789abcdef"
    candidate = root / "candidates" / candidate_id
    candidate.mkdir(parents=True)
    program = "observation = get_observation()\nresult = {'source': 'current public observation'}\n"
    (candidate / "program.py").write_text(program, encoding="utf-8")
    c.write_json(
        candidate / "submission.json",
        {
            "candidate_id": candidate_id,
            "program_sha256": c.file_sha(candidate / "program.py"),
            "provenance": "Reusable frozen skill; target must be derived in this episode",
        },
    )
    c.write_json(
        root / "session.json",
        {
            "runtime": {"environment": {"MUJOCO_GL": "glfw"}},
            "skill_library": library,
        },
    )
    c.write_json(root / "model/request.json", {"prompt": worker_prompt(library)})
    c.write_json(root / "finish.json", {"candidate_id": candidate_id})
    c.write_json(
        root / "calls/000001.json",
        {
            "tool": "execute_program",
            "candidate_id": candidate_id,
            "public_observation": {"timestamp_s": 0.0},
        },
    )
    return root, candidate


def test_permitted_library_descriptor_binds_manifest_and_canonical_snapshot(tmp_path):
    library = library_fixture(tmp_path)
    descriptor = provenance.library_context(library, worker_prompt(library))
    assert descriptor == {
        "sha256": library["sha256"],
        "skills": library["manifest"]["skills"],
    }
    assert "contents" not in descriptor
    assert (
        descriptor["skills"][SKILL_NAME] == hashlib.sha256(SKILL_TEXT.encode("utf-8")).hexdigest()
    )


@pytest.mark.parametrize(
    "damage",
    ["canonical_sha", "changed_content", "changed_digest", "extra_content", "missing_content"],
)
def test_corrupt_library_is_rejected_even_with_its_exact_text_in_prompt(tmp_path, damage):
    library = library_fixture(tmp_path)
    if damage == "canonical_sha":
        library["sha256"] = "0" * 64
    elif damage == "changed_content":
        library["contents"][SKILL_NAME] += "\nInjected replacement instruction."
        refresh_canonical_hash(library)
    elif damage == "changed_digest":
        library["manifest"]["skills"][SKILL_NAME] = "0" * 64
        refresh_canonical_hash(library)
    elif damage == "extra_content":
        library["contents"]["unlisted-skill.md"] = "Not in frozen manifest."
        refresh_canonical_hash(library)
    else:
        del library["contents"][SKILL_NAME]
        refresh_canonical_hash(library)
    with pytest.raises(ValueError):
        provenance.library_context(library, worker_prompt(library))


def test_valid_library_not_actually_supplied_to_worker_is_rejected(tmp_path):
    library = library_fixture(tmp_path)
    with pytest.raises(ValueError):
        provenance.library_context(library, "Public observations only; no library supplied.")


def test_different_valid_snapshot_in_worker_prompt_is_not_permission(tmp_path):
    library = library_fixture(tmp_path)
    supplied = deepcopy(library)
    supplied["contents"][SKILL_NAME] += "\nDifferent frozen version."
    supplied["manifest"]["skills"][SKILL_NAME] = hashlib.sha256(
        supplied["contents"][SKILL_NAME].encode()
    ).hexdigest()
    refresh_canonical_hash(supplied)
    with pytest.raises(ValueError):
        provenance.library_context(library, worker_prompt(supplied))


@pytest.mark.parametrize("damage", ["content_digest", "worker_prompt"])
def test_audit_rejects_tampering_before_reviewer_is_called(tmp_path, damage):
    library = library_fixture(tmp_path)
    root, _ = audit_fixture(tmp_path, library)
    if damage == "content_digest":
        library["contents"][SKILL_NAME] += "\nAltered after approval."
        refresh_canonical_hash(library)
        identity = c.read_json(root / "session.json")
        identity["skill_library"] = library
        c.write_json(root / "session.json", identity)
        c.write_json(root / "model/request.json", {"prompt": worker_prompt(library)})
    else:
        c.write_json(root / "model/request.json", {"prompt": "No supplied skill library."})
    calls = []

    def forbidden_reviewer(*args):
        calls.append(args)
        raise AssertionError("Tampered evidence must stop before any model request")

    with pytest.raises(ValueError):
        provenance.audit(root, {"type": "fixture"}, reviewer=forbidden_reviewer)
    assert calls == []
    assert not (root / "independent-provenance/audit.json").exists()


@pytest.mark.parametrize("verdict", ["PASS", "QUARANTINED"])
def test_review_receives_bound_library_but_its_verdict_is_never_overridden(tmp_path, verdict):
    library = library_fixture(tmp_path)
    root, candidate = audit_fixture(tmp_path, library)
    review_calls = []
    reviewer_reply = {
        "verdict": verdict,
        "reason": "Synthetic reviewer verdict; valid skill identity alone does not prove allowed target derivation.",
        "constant_audit": [
            "Reusable snippet inspected; every executable target still requires public provenance."
        ],
    }

    def reviewer(directory, prompt, spec, schema):
        review_calls.append((directory, prompt, spec, schema))
        inputs = c.read_json(directory / "inputs.json")
        assert inputs["permitted_skill_library"] == {
            "sha256": library["sha256"],
            "skills": library["manifest"]["skills"],
        }
        assert inputs["program"] == (candidate / "program.py").read_text()
        assert inputs["program_sha256"] == c.file_sha(candidate / "program.py")
        assert inputs["prompt"] == worker_prompt(library)
        assert inputs["public_trace"] == [c.read_json(root / "calls/000001.json")]
        assert json.dumps(inputs) in prompt
        instructions = prompt.split(json.dumps(inputs), 1)[0].lower()
        assert "frozen" in instructions and "skill" in instructions
        for prohibited in ("coordinates", "waypoints", "native", "evaluator", "seed branches"):
            assert prohibited in instructions
        return reviewer_reply

    result = provenance.audit(
        root, {"type": "fixture", "model": "fixture-model"}, reviewer=reviewer
    )
    assert len(review_calls) == 1
    for key, value in reviewer_reply.items():
        assert result[key] == value
    assert result["independent"] is True
    assert result["program_sha256"] == c.file_sha(candidate / "program.py")
    assert result["inputs_sha256"] == c.file_sha(root / "independent-provenance/inputs.json")
    assert c.read_json(root / "independent-provenance/audit.json") == result


def test_valid_library_does_not_allow_modified_selected_source(tmp_path):
    library = library_fixture(tmp_path)
    root, candidate = audit_fixture(tmp_path, library)
    (candidate / "program.py").write_text("result = 'modified source'\n")
    with pytest.raises(ValueError, match="Candidate code was modified"):
        provenance.audit(
            root,
            {"type": "fixture"},
            reviewer=lambda *_: pytest.fail("No review on changed source"),
        )


def test_visual_review_distinguishes_diagnostic_calls_from_executed_control(tmp_path):
    root, _ = audit_fixture(tmp_path, library_fixture(tmp_path))
    identity = c.read_json(root / "session.json")
    identity["feedback_review_version"] = 1
    c.write_json(root / "session.json", identity)

    def reviewer(directory, prompt, spec, schema):
        assert "visual_control_status" in schema["required"]
        assert "unexercised" in prompt and "executed branches" in prompt
        return {
            "verdict": "PASS",
            "reason": "Legal fixture, no vision control",
            "constant_audit": [],
            "visual_control_status": "diagnostic_only",
            "visual_control_assessment": "No result-dependent action observed.",
        }

    result = provenance.audit(root, {"type": "fixture"}, reviewer=reviewer)
    assert result["verdict"] == "PASS"
    assert result["visual_control_status"] == "diagnostic_only"


def test_changed_library_cannot_rewrite_an_existing_provenance_record(tmp_path):
    library = library_fixture(tmp_path)
    root, _ = audit_fixture(tmp_path, library)
    replies = []

    def reviewer(*_args):
        replies.append(True)
        return {
            "verdict": "QUARANTINED",
            "reason": "Historical fixture quarantine",
            "constant_audit": [],
        }

    provenance.audit(root, {"type": "fixture"}, reviewer=reviewer)
    paths = [
        root / "independent-provenance/inputs.json",
        root / "independent-provenance/audit.json",
    ]
    original = [path.read_bytes() for path in paths]
    changed = deepcopy(library)
    changed["contents"][SKILL_NAME] += "\nNew valid library version."
    changed["manifest"]["skills"][SKILL_NAME] = hashlib.sha256(
        changed["contents"][SKILL_NAME].encode()
    ).hexdigest()
    refresh_canonical_hash(changed)
    identity = c.read_json(root / "session.json")
    identity["skill_library"] = changed
    c.write_json(root / "session.json", identity)
    c.write_json(root / "model/request.json", {"prompt": worker_prompt(changed)})
    with pytest.raises(ValueError, match="Provenance inputs changed"):
        provenance.audit(root, {"type": "fixture"}, reviewer=reviewer)
    assert replies == [True]
    assert [path.read_bytes() for path in paths] == original
