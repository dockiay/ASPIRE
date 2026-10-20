"""Native asset import, continuous-body identity and ordered harvest predicates."""

from pathlib import Path

import numpy as np
import pytest

from cap_harness.api import CapApi
from cap_harness.registry import SO101_PUBLIC_TOOL_NAMES, ToolRegistry
from cap_harness.runtime import ProgramExecutor
from cap_harness.so101.adapter import SO101Adapter
from cap_harness.so101.fruitgym_plant import resources

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def adapter(monkeypatch):
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    if not (ROOT / "third_party/fruit_gym/ASPIRE-SOURCE.json").exists():
        pytest.skip("Prepare the pinned FruitGym resources first")
    instance = SO101Adapter(camera_width=64, camera_height=64, horizon=1000)
    instance.reset("so101_fruitgym_harvest", 0)
    first = instance.native_env._observation()
    monkeypatch.setattr(instance.native_env, "_observation", lambda: first)
    yield instance
    instance.close()


def advance(env, seconds):
    for sample in range(round(seconds / env.model.opt.timestep)):
        env.sim.step()
        env._after_physics_step()


def test_actual_meshes_textures_and_same_free_fruit_at_reset(adapter):
    env = adapter.native_env
    assert env.model.body_mass[env.fruit_body_id] == pytest.approx(0.020)
    assert env.model.mesh("fg_fruit").id >= 0
    assert env.model.mesh("fg_leaf").id >= 0
    assert env.model.texture("fg_red").id >= 0
    assert env.model.geom("plant_fg_leaf_0_0").contype == 1
    assert not env.forbidden_contacts
    assert len(env.all_fruit_geoms) == 2
    low, high = env.fruit_bounds()
    assert np.all(high > low) and 0.03 < high[2] - low[2] < 0.07
    identity = (env.fruit_body_id, env.fruit_joint_id, env.fixture_id)
    env.reset()
    assert identity == (env.fruit_body_id, env.fruit_joint_id, env.fixture_id)
    assert not adapter.check_success()
    public = adapter.get_task_metadata()["lesson"]
    assert "fruit_center_m" not in public and "fixture_release_time_s" not in public
    assert "bent_load_threshold_n" not in public


def test_waiting_beyond_old_release_timer_keeps_mesh_attached(adapter):
    env = adapter.native_env
    body = env.fruit_body_id
    advance(env, 10)
    assert env.detached_time is None
    assert env.sim.data._data.eq_active[env.fixture_id]
    assert env.model.body("lesson_fruit").id == body
    assert not adapter.check_success()
    assert not env.transport_violations


def test_public_probe_executes_without_claiming_harvest(adapter):
    registry = CapApi(adapter).register_tools(
        ToolRegistry(public_extension_allowlist=SO101_PUBLIC_TOOL_NAMES)
    )
    source = (ROOT / "examples/robosuite/so101_fruitgym_scene_probe.py").read_text()
    result = ProgramExecutor(registry).execute_program(source)
    assert result.ok, result.error
    evidence = adapter.native_env.task_evidence()
    assert evidence["stage"] == "approach_and_grasp"
    assert evidence["protocol"] == "so101-fruitgym-harvest-v2"
    assert evidence["plant_source"]["commit"] == "397abec4122f6ee5f52a3801a4cefb07a8fd6642"
    assert evidence["fruit_deleted_or_replaced"] is False
    assert evidence["task_success"] is False


def test_mechanical_release_keeps_same_body_meshes_and_visibility(adapter):
    env = adapter.native_env
    identity = (env.model.nbody, env.model.ngeom, env.fruit_body_id, env.fruit_joint_id)
    # Host-only loading test; this force is forbidden to generated robot policies.
    env.sim.data._data.xfrc_applied[env.fruit_body_id, 2] = -18.0
    for sample in range(40):
        env.sim.step()
        env._after_physics_step()
        if env.detached_time is not None:
            break
    env.sim.data._data.xfrc_applied[env.fruit_body_id] = 0
    assert env.release_event is not None
    assert not env.sim.data._data.eq_active[env.fixture_id]
    assert identity == (env.model.nbody, env.model.ngeom, env.fruit_body_id, env.fruit_joint_id)
    assert all(env.model.geom_rgba[geom, 3] > 0 for geom in env.all_fruit_geoms)
    assert (
        not adapter.check_success()
    )  # release alone, without grasp/carry/deposit, is insufficient


def test_placing_unharvested_fruit_cannot_satisfy_full_episode(adapter):
    env = adapter.native_env
    # Host-only negative test: a teleported object in the tray must not count as harvest.
    address = int(env.model.jnt_qposadr[env.fruit_joint_id])
    env.sim.data._data.eq_active[env.fixture_id] = False
    env.sim.data.qpos[address : address + 3] = [0.245, -0.16, 0.05]
    env.sim.forward()
    advance(env, 1.5)
    assert not env.ordered_stages_complete()
    assert not adapter.check_success()


@pytest.mark.parametrize(
    "times,expected",
    [
        ([1, 2, 4, 6, 7, 8], True),
        ([1, 2, None, 6, 7, 8], False),
        ([1, 3, 2, 6, 7, 8], False),
        ([1, 2, 4, 6, 8, 7], True),
        ([1, 2, 4, 6, 8, 3], False),
    ],
)
def test_ordered_stages_reject_missing_or_reversed_evidence(times, expected):
    from types import SimpleNamespace

    from cap_harness.so101.harvest import SO101FruitGymHarvestEnvironment

    fields = [
        "grasp_time",
        "detached_time",
        "free_hold_verified_time",
        "destination_ready_time",
        "deposit_started_time",
        "first_base_contact_time",
    ]
    state = SimpleNamespace(**dict(zip(fields, times)), release_event={"regime": "test"})
    assert SO101FruitGymHarvestEnvironment.ordered_stages_complete(state) == expected


def test_resource_hashes_reject_tampering(tmp_path, monkeypatch):
    import hashlib
    import json

    from cap_harness.so101 import fruitgym_plant as plant

    config = tmp_path / "manifest.json"
    config.write_text(
        json.dumps(
            {"checkout": "assets", "files": {"fruit.obj": hashlib.sha256(b"original").hexdigest()}}
        )
    )
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/fruit.obj").write_bytes(b"modified")
    monkeypatch.setattr(plant, "ROOT", tmp_path)
    monkeypatch.setattr(plant, "CONFIG", config)
    with pytest.raises(ValueError, match="missing/modified"):
        resources()
