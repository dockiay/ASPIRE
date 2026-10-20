"""The restricted policy can call, record and inspect the public visual tool."""

import pytest


def test_public_visual_comparison_is_recorded_without_advancing_simulation(tmp_path):
    pytest.importorskip("mujoco")
    pytest.importorskip("robosuite")
    from cap_harness.run import run_program
    from cap_harness.so101.visual_feedback import visual_feedback

    program = tmp_path / "visual.py"
    program.write_text(
        "before = get_observation()\n"
        "masks = {'agentview': before.cameras['agentview'].depth_m < 0}\n"
        "answer = so101.compare_visual_motion(before, before, masks, masks)\n"
        "assert answer['ok'] and answer['status'] == 'unknown'\n"
        "assert answer['fruit_motion'] == None\n"
        "assert get_robot_state().timestamp_s == before.timestamp_s\n"
        "result = {'comparison': answer}\n"
    )
    outcome = run_program(
        benchmark="so101", suite="so101_control", task_id=0, seed=0,
        program_path=program, output_root=tmp_path / "run", max_steps=10,
        camera_width=64, camera_height=64, capture_videos=False,
    )
    assert outcome.program_ok, outcome
    manifests = list((tmp_path / "run").rglob("manifest.json"))
    assert len(manifests) == 1
    feedback = visual_feedback(manifests[0].parent)
    assert feedback["indexed_comparison_calls"] == 1
    assert feedback["status_counts"] == {"unknown": 1}
    assert feedback["recent_measurements"][0]["fruit_motion"] is None
