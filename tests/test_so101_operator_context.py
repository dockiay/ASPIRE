"""Frozen context boundaries; models and simulation are mocked in these tests."""
import hashlib
import json

import pytest

from cap_harness.so101 import debug_agent as agent
from cap_harness.so101 import skill_learning as learning


def prompt_root(tmp_path):
    root = tmp_path / 'worker'
    (root / 'inputs').mkdir(parents=True)
    (root / 'inputs/agent-prompt.md').write_text('Registered tools only.')
    (root / 'inputs/SKILL.md').write_text('Public observations only.')
    return root


def test_optional_context_is_hashed_and_reaches_the_shared_controller_prompt(tmp_path):
    path = tmp_path / 'observations.md'
    text = 'Prior observed grasp held; removal was not verified. Reconsider the hypothesis.'
    path.write_text(text)
    context = learning.load_operator_context(path)
    assert context == {'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()}
    root = prompt_root(tmp_path)
    original = agent.agent_prompt(root, {'suite': 'so101_fruitgym_harvest'})
    assert text not in original
    supplied = agent.agent_prompt(root, {'suite': 'so101_fruitgym_harvest', 'operator_context': context})
    assert text in supplied and 'never physical success evidence' in supplied
    assert learning.load_operator_context(None) is None


@pytest.mark.parametrize('text', ['', ' \n\t'])
def test_empty_operator_context_is_rejected(tmp_path, text):
    path = tmp_path / 'empty.md'
    path.write_text(text)
    with pytest.raises(ValueError, match='must not be empty'):
        learning.load_operator_context(path)


def test_modified_context_descriptor_never_reaches_a_controller(tmp_path):
    root = prompt_root(tmp_path)
    with pytest.raises(ValueError, match='context hash mismatch'):
        agent.agent_prompt(root, {'suite': 'so101_fruitgym_harvest', 'operator_context': {'text': 'changed', 'sha256': 'old'}})


def test_context_is_frozen_and_changed_resume_stops_before_model_calls(tmp_path, monkeypatch, capsys):
    context_file = tmp_path / 'context.md'
    context_file.write_text('Public previous failure observations.')
    config = tmp_path / 'controller.json'
    config.write_text('{}')
    output = tmp_path / 'learning'
    calls = []
    monkeypatch.setattr(learning.agent, 'controller_spec', lambda _: {'type': 'fake'})
    monkeypatch.setattr(learning.d, 'runtime_identity', lambda *_: {'runtime': 'synthetic'})
    monkeypatch.setattr(learning.skills, 'snapshot', lambda _: {'sha256': 'synthetic-library', 'skills': {}})
    monkeypatch.setattr(learning, 'cases', lambda: [{'partition': 'development', 'seed': 0}, {'partition': 'development', 'seed': 1001}])
    monkeypatch.setattr(learning.d, 'build_identity', lambda *_args, **_kwargs: {'seeds': [0, 1001]})

    def initialize(root, identity):
        root.mkdir(parents=True, exist_ok=True)
        (root / 'skill-report.json').write_text(json.dumps({'proposed_new': [], 'proposed_edits': []}))
        assert identity['operator_context']['text'] == context_file.read_text()
        return root

    monkeypatch.setattr(learning.d, 'initialize', initialize)
    monkeypatch.setattr(learning.agent, 'launch', lambda *args: calls.append(args))
    monkeypatch.setattr(learning.provenance, 'audit', lambda *_: {'verdict': 'PASS'})
    monkeypatch.setattr(learning, 'verify_skills', lambda *_args: {'verdict': 'verified', 'synthetic': True})
    args = ['--output', str(output), '--contract', 'retain_ripe_fruit_v1', '--controller-config', str(config), '--context-file', str(context_file)]
    assert learning.main(args) == 0
    frozen = (output / 'learning.json').read_bytes()
    assert learning.main(args + ['--width', '1280', '--height', '960']) == 1
    assert 'identity changed' in capsys.readouterr().out.lower()
    assert len(calls) == 1 and (output / 'learning.json').read_bytes() == frozen
    context_file.write_text('Changed task context after the run.')
    assert learning.main(args) == 1
    assert 'identity changed' in capsys.readouterr().out.lower()
    assert len(calls) == 1 and (output / 'learning.json').read_bytes() == frozen


@pytest.mark.parametrize('dimensions', [(0, 480), (640, 2049), (True, 480)])
def test_invalid_camera_dimensions_stop_before_runtime(tmp_path, monkeypatch, dimensions):
    def unexpected(*_args):
        raise AssertionError('Runtime must not start with invalid dimensions')

    monkeypatch.setattr(learning.d, 'runtime_identity', unexpected)
    if type(dimensions[0]) is bool:
        with pytest.raises(SystemExit):
            learning.main(['--output', str(tmp_path), '--contract', 'retain_ripe_fruit_v1',
                           '--width', str(dimensions[0]), '--height', str(dimensions[1])])
    else:
        assert learning.main(['--output', str(tmp_path), '--contract', 'retain_ripe_fruit_v1',
                              '--width', str(dimensions[0]), '--height', str(dimensions[1])]) == 1
