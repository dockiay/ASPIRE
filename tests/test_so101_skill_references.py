"""External knowledge is explicit, frozen, reviewable and never auto-promoted."""

from copy import deepcopy
import json

import pytest
from test_so101_skill_provenance import audit_fixture, library_fixture

from cap_harness.so101 import campaign as c
from cap_harness.so101 import debug_agent, provenance, skill_references, skills


def bundle():
    return skill_references.snapshot(c.ROOT / "configs/so101/published-skill-references.json")


def test_published_sources_reach_actual_agent_prompt_without_changing_local_library(tmp_path):
    references = bundle()
    library = library_fixture(tmp_path)
    before = deepcopy(library)
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for name in ("SKILL.md", "agent-prompt.md"):
        (inputs / name).write_text("Profile fixture", encoding="utf-8")
    prompt = debug_agent.agent_prompt(
        tmp_path,
        {
            "suite": "so101_fruitgym_harvest",
            "skill_library": library,
            "skill_references": references,
        },
    )
    assert len(references["contents"]) == 5
    assert skill_references.validate(references, prompt)["sha256"] == references["sha256"]
    assert library == before
    assert set(library["contents"]).isdisjoint(references["contents"])
    assert "OUT of skill_report.consulted" in prompt


@pytest.mark.parametrize("damage", ["content", "hash", "membership", "verified", "missing_prompt"])
def test_tampered_or_unsupplied_references_rejected(damage):
    references = bundle()
    name = next(iter(references["contents"]))
    if damage == "content":
        references["contents"][name] += "replacement"
    elif damage == "hash":
        references["sha256"] = "0" * 64
    elif damage == "membership":
        del references["contents"][name]
    elif damage == "verified":
        references["manifest"]["references"][name]["status"] = "verified"
    with pytest.raises(ValueError):
        skill_references.validate(
            references, "missing" if damage == "missing_prompt" else json.dumps(references)
        )


def test_review_binds_external_input_and_requests_application_evidence(tmp_path):
    library = library_fixture(tmp_path)
    root, _ = audit_fixture(tmp_path, library)
    references = bundle()
    identity = c.read_json(root / "session.json")
    identity["skill_references"] = references
    c.write_json(root / "session.json", identity)
    request = c.read_json(root / "model/request.json")
    request["prompt"] += skill_references.prompt(references)
    c.write_json(root / "model/request.json", request)

    def reviewer(directory, prompt, spec, schema):
        inputs = c.read_json(directory / "inputs.json")
        assert inputs["permitted_external_references"]["sha256"] == references["sha256"]
        assert "reference_application_assessment" in schema["required"]
        assert "Consultation alone" in prompt
        return {
            "verdict": "PASS",
            "reason": "fixture",
            "constant_audit": [],
            "reference_application_assessment": "Supplied, no executed application in fixture",
        }

    result = provenance.audit(root, {"type": "fixture"}, reviewer=reviewer)
    assert "no executed application" in result["reference_application_assessment"]
    # A supplied external reference cannot be mislabeled as a promoted local member.
    with pytest.raises(ValueError, match="Unknown consulted skill"):
        skills.validate_report(
            {
                "skill_library_sha": library["sha256"],
                "consulted": [
                    {"skill": "upstream-grasp", "verdict": "useful", "evidence": "source only"}
                ],
                "proposed_edits": [],
                "proposed_new": [],
            },
            library,
            {},
        )
