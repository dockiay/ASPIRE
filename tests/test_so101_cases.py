"""Synthetic conditions must be disjoint, deterministic and applied to native physics."""

import json
from pathlib import Path

import numpy as np
import pytest

from cap_harness.api import CapApi
from cap_harness.registry import SO101_PUBLIC_TOOL_NAMES, ToolRegistry
from cap_harness.runtime import ProgramExecutor
from cap_harness.so101.adapter import SO101Adapter
from cap_harness.so101.cases import (
    DEFAULT_CASES_PATH,
    canonical_sha256,
    detachment_case_for_seed,
    load_detachment_cases,
)


def test_partition_counts_balance_and_no_repeated_conditions():
    cases = load_detachment_cases()
    assert len(cases) == 30
    # Publishing different conditions requires an intentional protocol revision.
    assert {c.protocol_sha256 for c in cases} == {
        "d3c6f34a85e767de2f51c85f9a817f455db385993859aa0e7704dfeafa6a9a5b"
    }
    assert len({c.to_record()["case_sha256"] for c in cases}) == 30
    assert len({(c.bent_force_n, c.junction_time_constant_s) for c in cases}) == 30
    assert {c.partition for c in cases} == {"development", "validation", "evaluation"}
    for partition, count, per_force in [
        ("development", 12, 2),
        ("validation", 6, 1),
        ("evaluation", 12, 2),
    ]:
        selected = [c for c in cases if c.partition == partition]
        assert len(selected) == count
        for force in {c.bent_force_n for c in cases}:
            assert sum(c.bent_force_n == force for c in selected) == per_force


def test_seed_selection_is_independent_of_rng_order_and_json_whitespace(tmp_path):
    first = detachment_case_for_seed(101).to_record()
    np.random.seed(9865)
    np.random.random(100)
    detachment_case_for_seed(112)
    assert detachment_case_for_seed(101).to_record() == first
    alternate = tmp_path / "same-protocol.json"
    alternate.write_text(json.dumps(json.loads(DEFAULT_CASES_PATH.read_text()), sort_keys=True))
    assert detachment_case_for_seed(101, alternate).to_record() == first
    assert detachment_case_for_seed(102).to_record() != first


@pytest.mark.parametrize("seed", [0, -1, 13, 113, 200, 207, True, 101.0, "101"])
def test_unknown_or_invalid_seeds_fail_instead_of_reusing_a_scene(seed):
    with pytest.raises(ValueError, match="seed"):
        detachment_case_for_seed(seed)


@pytest.mark.parametrize(
    "fault",
    [
        "overlap",
        "missing",
        "duplicate_conditions",
        "nonfinite",
        "out_of_range",
        "wrong_partition",
        "wrong_version",
    ],
)
def test_invalid_case_protocols_are_rejected(tmp_path, fault):
    protocol = json.loads(DEFAULT_CASES_PATH.read_text())
    if fault == "overlap":
        protocol["partitions"]["validation"].append(101)
    elif fault == "missing":
        protocol["cases"].pop()
    elif fault == "duplicate_conditions":
        for key in ["bent_force_n", "junction_time_constant_s"]:
            protocol["cases"][1][key] = protocol["cases"][0][key]
    elif fault == "nonfinite":
        protocol["cases"][0]["bent_force_n"] = float("nan")
    elif fault == "out_of_range":
        protocol["cases"][0]["junction_time_constant_s"] = 0.0001
    elif fault == "wrong_partition":
        original = protocol["cases"][0]["partition"]
        protocol["cases"][0]["partition"] = (
            "validation" if original != "validation" else "development"
        )
    else:
        protocol["protocol_version"] = "unsupported"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(protocol))
    with pytest.raises(ValueError):
        load_detachment_cases(path)


@pytest.fixture
def adapter():
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    root = Path(__file__).resolve().parents[1]
    if not (root / "third_party/so_arm100/Simulation/SO101/so101_new_calib.xml").is_file():
        pytest.skip("Run bash scripts/bootstrap_so101.sh")
    instance = SO101Adapter(camera_width=48, camera_height=48, horizon=100)
    yield instance
    instance.close()


def settle(env):
    for sample_index in range(250):
        env.sim.step()
        env._after_physics_step()


def test_registered_case_reproduces_physics_and_reset_restores_it(adapter):
    # Only development scenes are executed here; reserved outcomes stay unused.
    adapter.reset("so101_strawberry_detachment_cases", 101)
    env = adapter.native_env
    case = detachment_case_for_seed(101)
    assert canonical_sha256(env.case_protocol_snapshot) == case.protocol_sha256
    assert env.bent_force_n == case.bent_force_n
    assert env.model.eq_solref[env.fixture_id, 0] == case.junction_time_constant_s
    assert env.model.body_mass[env.fruit_body_id] == pytest.approx(0.020)
    assert env.model.geom_condim[sorted(env.fruit_geoms)].tolist() == [4, 4]
    public = adapter.get_task_metadata()["lesson"]
    assert (
        not {
            "bent_load_threshold_n",
            "straight_load_threshold_n",
            "case",
            "partition",
            "junction_solref",
        }
        & public.keys()
    )
    settle(env)
    first_state = env.sim.data.qpos.copy()
    first_case = env.task_evidence()["case"]
    env.bent_force_n = 999
    env.model.eq_solref[env.fixture_id, 0] = 0.05
    env.reset()
    assert env.bent_force_n == case.bent_force_n
    assert env.model.eq_solref[env.fixture_id, 0] == case.junction_time_constant_s
    settle(env)
    np.testing.assert_allclose(env.sim.data.qpos, first_state, atol=1e-12, rtol=0)
    assert env.task_evidence()["case"] == first_case
    adapter.reset("so101_strawberry_detachment_cases", 102)
    second = adapter.native_env
    settle(second)
    assert second.case.junction_time_constant_s != case.junction_time_constant_s
    assert not np.allclose(second.sim.data.qpos, first_state, atol=1e-7, rtol=0)
    assert second.task_evidence()["case"]["case_sha256"] != first_case["case_sha256"]
    assert second.detached_time is None


def test_public_probe_runs_without_exposing_parameters(adapter):
    adapter.reset("so101_strawberry_detachment_cases", 101)
    registry = CapApi(adapter).register_tools(
        ToolRegistry(public_extension_allowlist=SO101_PUBLIC_TOOL_NAMES)
    )
    program = (
        Path(__file__).resolve().parents[1] / "examples/robosuite/so101_strawberry_case_probe.py"
    ).read_text()
    execution = ProgramExecutor(registry).execute_program(program)
    assert execution.ok, execution.error
    assert not adapter.check_success()
    assert adapter.native_env.detached_time is None
    # Preserve the original nominal lesson and its existing meaning of seed.
    adapter.reset("so101_strawberry_detachment", 13)
    assert adapter.native_env.bent_force_n == pytest.approx(3.175)
    assert "bent_load_threshold_n" in adapter.get_task_metadata()["lesson"]
