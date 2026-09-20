"""
tests/test_signal_lifecycle.py — Unit Tests for Signal Lifecycle Management & State Machine
"""

import pytest
from app.learning.signal_lifecycle import SignalLifecycle, SignalStatus, SignalType


class TestSignalLifecycle:

    def test_status_progression_to_active(self):
        # 4 supporting channels, 0 negative, contrast 2.5 -> ACTIVE
        status = SignalLifecycle.evaluate_status(
            pos_support=4,
            neg_penalty=0,
            contrast_score=2.5
        )
        assert status == SignalStatus.ACTIVE

    def test_status_progression_to_validated(self):
        # 3 supporting channels, 0 negative, contrast 1.6 -> VALIDATED
        status = SignalLifecycle.evaluate_status(
            pos_support=3,
            neg_penalty=0,
            contrast_score=1.6
        )
        assert status == SignalStatus.VALIDATED

    def test_status_progression_to_candidate(self):
        # 2 supporting channels, 0 negative, contrast 0.8 -> CANDIDATE
        status = SignalLifecycle.evaluate_status(
            pos_support=2,
            neg_penalty=0,
            contrast_score=0.8
        )
        assert status == SignalStatus.CANDIDATE

    def test_status_observed_single_channel_support(self):
        # Only 1 channel support -> OBSERVED (Anti-overfitting: never promote single-channel features)
        status = SignalLifecycle.evaluate_status(
            pos_support=1,
            neg_penalty=0,
            contrast_score=3.0
        )
        assert status == SignalStatus.OBSERVED

    def test_deprecation_on_high_negative_ratio(self):
        # 3 positive channels, 2 negative channels (total 5, neg_ratio = 40% >= 15%) -> DEPRECATED
        status = SignalLifecycle.evaluate_status(
            pos_support=3,
            neg_penalty=2,
            contrast_score=0.5
        )
        assert status == SignalStatus.DEPRECATED

    def test_confidence_computation_bounds(self):
        conf_zero = SignalLifecycle.compute_confidence(pos_support=0, neg_penalty=0, contrast_score=0.0)
        assert conf_zero == 0.0

        conf_high = SignalLifecycle.compute_confidence(pos_support=5, neg_penalty=0, contrast_score=4.0)
        assert 0.8 <= conf_high <= 1.0

        conf_polluted = SignalLifecycle.compute_confidence(pos_support=5, neg_penalty=5, contrast_score=1.0)
        assert conf_polluted < conf_high
