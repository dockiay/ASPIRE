"""Seed-selected cases with evaluator-only parameters and unchanged robot physics."""

from __future__ import annotations

import json

from cap_harness.so101.cases import (
    DEFAULT_CASES_PATH,
    PROTOCOL_VERSION,
    canonical_sha256,
    detachment_case_for_seed,
)
from cap_harness.so101.detachment import (
    BEND_TRIAL_DEG,
    STRAIGHT_FORCE_SAMPLES_N,
    SO101StrawberryDetachmentEnvironment,
)


class SO101StrawberryDetachmentCasesEnvironment(SO101StrawberryDetachmentEnvironment):
    task_name = "so101_strawberry_detachment_cases"

    def __init__(self, *, seed: int, **kwargs) -> None:
        # Fail unknown seeds before loading native assets or allocating a renderer.
        self.case = detachment_case_for_seed(seed)
        self.case_protocol_snapshot = json.loads(DEFAULT_CASES_PATH.read_text(encoding="utf-8"))
        if canonical_sha256(self.case_protocol_snapshot) != self.case.protocol_sha256:
            raise ValueError("Case protocol changed while constructing the environment")
        super().__init__(**kwargs)
        self._apply_case_parameters()

    def _apply_case_parameters(self) -> None:
        self.bent_force_n = self.case.bent_force_n
        self.straight_force_n = sum(STRAIGHT_FORCE_SAMPLES_N) / len(STRAIGHT_FORCE_SAMPLES_N)
        self.bend_trial_deg = BEND_TRIAL_DEG
        fixture_id = self.model.equality("fruit_fixture").id
        self.model.eq_solref[fixture_id] = [self.case.junction_time_constant_s, 1]
        self.model.eq_solimp[fixture_id] = [0.9, 0.9, 0.001, 0.5, 2]

    def _reset_task_state(self) -> None:
        self._apply_case_parameters()
        super()._reset_task_state()

    @classmethod
    def lesson_metadata(cls) -> dict:
        metadata = super().lesson_metadata()
        # These are evaluator parameters, not measurements available to the policy.
        for key in ("bent_load_threshold_n", "straight_load_threshold_n", "bend_trial_deg"):
            metadata.pop(key)
        return {
            **metadata,
            "scene_variation": "fixed geometry; hidden junction load and compliance",
            "case_protocol_version": PROTOCOL_VERSION,
        }

    def task_evidence(self) -> dict:
        return {**super().task_evidence(), "case": self.case.to_record()}
