from cap_harness.so101.experiment_feedback import experiment_feedback


def test_comparison_before_action_is_not_proof_of_feedback_control():
    row = experiment_feedback(
        {
            "skill_evaluations": {
                "grasp_ripe_fruit_v1": {
                    "passed": False,
                    "measurements": {"grasp_verified_time_s": 2.0},
                }
            },
            "public_action_results": {
                "summarized_action_calls": 1,
                "recent_actions": [
                    {
                        "call_index": 10,
                        "tool": "so101.command_joints",
                        "steps_executed": 1,
                        "start_time_s": 3.0,
                    }
                ],
            },
            "public_visual_motion": {"recent_measurements": [{"call_index": 9}]},
        }
    )
    assert row["qualified_grasp_observed"]
    assert row["post_grasp_guarded_motion_observed"]
    assert row["passed_contracts"] == []
    assert row["visual_comparisons_followed_by_motion"] == [9]
    assert not row["visual_control_verified"]


def test_missing_grasp_does_not_claim_maneuver_failure():
    row = experiment_feedback({})
    assert not row["qualified_grasp_observed"]
    assert "prerequisites unresolved" in row["prerequisite_diagnosis"]
    assert not row["post_grasp_guarded_motion_observed"]


def test_benchmark_explains_modeled_mechanics_without_releasing_private_thresholds():
    from cap_harness.so101.harvest import SO101FruitGymHarvestEnvironment

    metadata = SO101FruitGymHarvestEnvironment.lesson_metadata()
    scope = metadata["release_model_scope"]
    assert scope["axial_torsion_fracture_modeled"] is False
    assert scope["biologically_calibrated"] is False
    for key in ("bent_load_threshold_n", "straight_load_threshold_n", "bend_trial_deg"):
        assert key not in metadata
