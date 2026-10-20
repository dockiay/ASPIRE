"""Search protocol tests use synthetic artifacts, never claim physical progress."""

import json

import pytest
from test_so101_debug_agent import service

from cap_harness.so101 import campaign as c
from cap_harness.so101 import debug_agent
from cap_harness.so101 import strategy_search as search


def hypothesis(index, *, phase="coarse", parent=None):
    return json.dumps(
        {
            "phase": phase,
            "family": f"family {index}",
            "dimensions": {
                key: f"{key} experimental alternative {index}" for key in search.DIMENSIONS
            },
            "parent_candidate_id": parent,
            "rationale": "Synthetic structural comparison only",
            "expected_evidence": "Public observations must test this hypothesis",
        }
    )


def configured(tmp_path, *, adaptive=False):
    tools, _ = service(tmp_path, max_programs=5, max_calls=80)
    tools.identity.update(
        search_protocol=search.configuration("diverse", 5),
        tie_breaker="evidence_choice",
        enforce_debug_sequence=True,
    )
    if not adaptive:
        tools.identity["search_protocol"].update(
            schema="so101-diverse-search-v1",
            allow_prerequisite_repair=False,
            require_budget_exhaustion=True,
        )
    c.write_json(tools.root / "session.json", tools.identity)
    tools.call("explore_scene", {})
    return tools


def submit(tools, code, index, **kwargs):
    return tools.call(
        "execute_program",
        {
            "code": code,
            "hypothesis": hypothesis(index, **kwargs),
            "provenance": "Synthetic fixture, no native targets",
        },
    )[0]


def inspect(tools, candidate):
    tools.call("inspect_results", {"candidate_id": candidate})
    tools.call(
        "view_frame",
        {"candidate_id": candidate, "case_index": 0, "camera": "agentview", "frame_index": 0},
    )


def test_search_budget_and_structural_normalization():
    assert search.configuration("fix-loop", 3) is None
    with pytest.raises(ValueError, match="at least five"):
        search.configuration("diverse", 4)
    assert search.structural_digest("x = 2\nresult = x\n") == search.structural_digest(
        "y = 99\nresult = y\n"
    )
    assert search.structural_digest("result = 2\n") != search.structural_digest("result = 1 + 2\n")


def test_coarse_gate_rejects_cosmetic_changes_and_premature_refinement(tmp_path):
    tools = configured(tmp_path)
    first = submit(tools, "result = 0\n", 0)["candidate_id"]
    inspect(tools, first)
    assert "constants/names" in submit(tools, "result = 99\n", 1)["error"]
    assert (
        "must be coarse"
        in submit(tools, "result = 1 + 2\n", 1, phase="refine", parent=first)["error"]
    )
    changed = json.loads(hypothesis(1))
    changed["dimensions"] = json.loads(hypothesis(0))["dimensions"]
    result, _ = tools.call(
        "execute_program",
        {"code": "result = 1 + 2\n", "hypothesis": json.dumps(changed), "provenance": "fixture"},
    )
    assert "at least two dimensions" in result["error"]
    changed["dimensions"] = json.loads(hypothesis(1))["dimensions"]
    changed["family"] = "family 0"
    result, _ = tools.call(
        "execute_program",
        {"code": "result = 1 + 2\n", "hypothesis": json.dumps(changed), "provenance": "fixture"},
    )
    assert "different strategy family" in result["error"]
    assert len(list((tools.root / "candidates").glob("*/submission.json"))) == 1


def test_evidence_then_refinement_and_choice_among_physical_ties(tmp_path):
    tools = configured(tmp_path)
    codes = ["result = 0\n", "result = 1 + 2\n", "result = [1, 2]\n", "result = {'fixture': 1}\n"]
    ids = []
    for index, code in enumerate(codes):
        candidate = submit(tools, code, index)["candidate_id"]
        ids.append(candidate)
        if index == 0:
            tools.call("inspect_results", {"candidate_id": candidate})
            assert "View an audited frame" in submit(tools, codes[1], 1)["error"]
        inspect(tools, candidate)
    assert (
        "Complete diverse"
        in tools.call(
            "finish_session",
            {"candidate_id": ids[-1], "analysis": "Unmet physical goal; experimental preference"},
        )[0]["error"]
    )
    assert (
        "prior candidate"
        in submit(tools, "result = [3, 4]\n", 4, phase="refine", parent="absent")["error"]
    )
    last = submit(tools, "result = [3, 4]\n", 4, phase="refine", parent=ids[2])["candidate_id"]
    inspect(tools, last)
    # All physical scores tie at zero; larger/later code may now be chosen.
    finish = tools.call(
        "finish_session",
        {
            "candidate_id": last,
            "analysis": "Exploratory evidence preference only, no physical success",
        },
    )[0]
    assert finish["candidate_id"] == last and finish["verified_skill_promoted"] is False


def test_strategy_metadata_is_immutable_and_prompt_is_shared(tmp_path):
    tools = configured(tmp_path)
    first = submit(tools, "result = 0\n", 0)["candidate_id"]
    inspect(tools, first)
    assert "cannot be rewritten" in submit(tools, "result = 0\n", 1)["error"]
    prompt = debug_agent.agent_prompt(tools.root, tools.identity)
    assert "DIVERSE SEARCH" in prompt and "AST size is not preferred" in prompt
    described = tools.call("describe_task", {})[0]
    assert described["search_protocol"]["coarse_programs"] == 4
    assert "controller chooses among ties" in described["selection_rule"]


def test_search_descriptor_tampering_is_rejected_at_finish(tmp_path):
    tools = configured(tmp_path)
    candidate = submit(tools, "result = 0\n", 0)["candidate_id"]
    inspect(tools, candidate)
    path = tools.root / "candidates" / candidate / "submission.json"
    row = c.read_json(path)
    row["search_strategy"]["family"] = "modified after execution"
    c.write_json(path, row)
    result = tools.call("finish_session", {"candidate_id": candidate, "analysis": "fixture"})[0]
    assert "strategy record was modified" in result["error"]


def test_prerequisite_repair_before_four_families_and_early_engineering_handoff(tmp_path):
    tools = configured(tmp_path, adaptive=True)
    first = submit(tools, "result = 0\n", 0)["candidate_id"]
    inspect(tools, first)
    repaired = submit(tools, "result = 1\n", 0, phase="diagnose", parent=first)
    assert "candidate_id" in repaired, repaired
    inspect(tools, repaired["candidate_id"])
    # A diagnostic version does not consume another coarse family or require
    # fake structural differences in a prerequisite correction.
    second = submit(tools, "result = 2 + 3\n", 1)
    assert "candidate_id" in second, second
    inspect(tools, second["candidate_id"])
    result = tools.call(
        "finish_session",
        {
            "candidate_id": repaired["candidate_id"],
            "analysis": "Repeated prerequisite failure needs engineering review; no skill success.",
        },
    )[0]
    assert result["candidate_id"] == repaired["candidate_id"]
