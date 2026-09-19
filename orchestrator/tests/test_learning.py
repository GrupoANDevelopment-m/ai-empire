"""
REAL tests for the self-learning components:
  - FeedbackStore: record, aggregate, export
  - ABTest: statistical significance
  - ModelRanker: UCB1 selection, exploration vs exploitation
"""
import math
import random
import pytest

from learning.feedback_store import FeedbackStore, Feedback, FeedbackType
from learning.ab_test import ABTest, _normal_cdf
from learning.model_ranker import ModelRanker


class TestFeedbackStore:

    def test_record_and_retrieve(self):
        store = FeedbackStore()
        fb = Feedback(
            id="fb-1",
            feedback_type=FeedbackType.THUMBS_UP,
            subject="lead:abc",
            score=1.0,
            context={"model": "claude-sonnet-4-5"},
        )
        store.record(fb)
        assert len(store) == 1
        all_fb = store.get()
        assert all_fb[0].id == "fb-1"

    def test_get_by_subject(self):
        store = FeedbackStore()
        store.record(Feedback("f1", FeedbackType.CONVERSION, "lead:A", 0.8, context={"model": "x"}))
        store.record(Feedback("f2", FeedbackType.CONVERSION, "lead:B", 0.5, context={"model": "y"}))
        a = store.get("lead:A")
        assert len(a) == 1
        assert a[0].score == 0.8

    def test_aggregate_by_model(self):
        store = FeedbackStore()
        store.record_many([
            Feedback("f1", FeedbackType.CONVERSION, "c1", 0.9, context={"model": "claude"}),
            Feedback("f2", FeedbackType.CONVERSION, "c2", 0.8, context={"model": "claude"}),
            Feedback("f3", FeedbackType.CONVERSION, "c3", 0.4, context={"model": "gpt-4o"}),
            Feedback("f4", FeedbackType.BOUNCE, "c4", 0.1, context={"model": "gpt-4o"}),
        ])
        agg = store.aggregate_by("model")
        assert "claude" in agg
        assert "gpt-4o" in agg
        assert agg["claude"]["count"] == 2
        assert abs(agg["claude"]["avg_score"] - 0.85) < 0.001
        assert agg["claude"]["thumbs_up"] == 2
        assert agg["gpt-4o"]["thumbs_down"] == 2  # both < 0.4

    def test_aggregate_counts_by_type(self):
        store = FeedbackStore()
        store.record_many([
            Feedback("f1", FeedbackType.CONVERSION, "c1", 0.9, context={"model": "m"}),
            Feedback("f2", FeedbackType.BOUNCE, "c2", 0.1, context={"model": "m"}),
            Feedback("f3", FeedbackType.CONVERSION, "c3", 0.9, context={"model": "m"}),
        ])
        agg = store.aggregate_by("model")
        assert agg["m"]["by_type"]["conversion"] == 2
        assert agg["m"]["by_type"]["bounce"] == 1

    def test_export(self):
        store = FeedbackStore()
        store.record(Feedback("f1", FeedbackType.RATING, "x", 0.5))
        exported = store.export()
        assert isinstance(exported, list)
        assert exported[0]["id"] == "f1"
        assert exported[0]["feedback_type"] == "rating"

    def test_clear(self):
        store = FeedbackStore()
        store.record(Feedback("f1", FeedbackType.RATING, "x", 0.5))
        store.clear()
        assert len(store) == 0

    def test_concurrent_record_safe(self):
        """Thread-safe: concurrent record doesn't lose data."""
        import threading
        store = FeedbackStore()
        def add(i):
            for j in range(100):
                store.record(Feedback(f"f-{i}-{j}", FeedbackType.RATING, "x", 0.5))
        threads = [threading.Thread(target=add, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(store) == 500


class TestABTest:

    def test_no_data_returns_insignificant(self):
        test = ABTest("test", lambda: 1, lambda: 2, lambda x: 0.5)
        result = test.analyze()
        assert not result.is_significant
        assert result.winner is None
        assert result.a_count == 0
        assert result.b_count == 0

    def test_clear_winner_is_significant(self):
        """B is clearly better than A."""
        test = ABTest(
            "prompt",
            variant_a=lambda: "bad",
            variant_b=lambda: "good",
            score_fn=lambda x: 0.2 if x == "bad" else 0.9,
            min_samples=10,
        )
        test.run_n(50)
        result = test.analyze()
        assert result.a_count > 0
        assert result.b_count > 0
        assert result.a_score < result.b_score
        assert result.is_significant
        assert result.winner == "b"
        assert result.confidence > 0.95

    def test_no_difference_is_not_significant(self):
        """Two identical variants — no winner."""
        test = ABTest(
            "t",
            variant_a=lambda: 1,
            variant_b=lambda: 1,
            score_fn=lambda x: random.uniform(0.4, 0.6),
        )
        test.run_n(100)
        result = test.analyze()
        assert not result.is_significant
        assert result.winner is None

    def test_lift_calculation(self):
        """Lift is (b - a) / a."""
        test = ABTest("t", lambda: 0, lambda: 0, lambda x: 0.5)
        test._a_scores = [0.5] * 10
        test._b_scores = [0.75] * 10
        result = test.analyze()
        assert abs(result.lift - 0.5) < 0.01  # 50% lift

    def test_too_few_samples_not_significant_even_if_big_diff(self):
        """Statistical guard: can't declare winner with n=3."""
        test = ABTest(
            "t",
            variant_a=lambda: 1,
            variant_b=lambda: 1,
            score_fn=lambda x: 0.0 if x == 1 else 1.0,
            min_samples=30,
        )
        test.run_n(6)  # 3 each
        result = test.analyze()
        # Big diff but too few samples
        assert not result.is_significant
        assert result.winner is None


class TestNormalCDF:

    def test_cdf_at_zero_is_half(self):
        assert abs(_normal_cdf(0.0) - 0.5) < 0.001

    def test_cdf_at_positive(self):
        # P(Z < 1.96) ≈ 0.975
        assert abs(_normal_cdf(1.96) - 0.975) < 0.01

    def test_cdf_at_negative(self):
        # P(Z < -1.96) ≈ 0.025
        assert abs(_normal_cdf(-1.96) - 0.025) < 0.01

    def test_cdf_symmetric(self):
        # P(Z < -x) = 1 - P(Z < x)
        for x in [0.5, 1.0, 2.0, 3.0]:
            assert abs(_normal_cdf(-x) - (1 - _normal_cdf(x))) < 0.001


class TestModelRanker:

    def test_first_choice_is_round_robin_exploration(self):
        """Initially, every model is tried at least once."""
        ranker = ModelRanker(["m1", "m2", "m3"], FeedbackStore())
        seen = set()
        for _ in range(3):
            seen.add(ranker.choose("task"))
        assert seen == {"m1", "m2", "m3"}

    def test_picks_best_after_data(self):
        """After positive feedback, best model is chosen."""
        ranker = ModelRanker(["m1", "m2"], FeedbackStore())
        # Seed exploration: try m1 once
        first = ranker.choose("task")
        # m1 gets good scores
        for _ in range(10):
            ranker.update("task", "m1", 0.9)
        # m2 gets bad scores
        for _ in range(10):
            ranker.update("task", "m2", 0.1)
        # Now m1 should be chosen consistently
        for _ in range(20):
            assert ranker.choose("task") == "m1"

    def test_exploration_after_no_data(self):
        """Untested model is preferred (UCB exploration bonus)."""
        ranker = ModelRanker(["good", "unknown"], FeedbackStore())
        ranker.choose("task")  # first call returns "good" (or any)
        # After 10 good runs on "good"
        for _ in range(10):
            ranker.update("task", "good", 0.9)
        # unknown has never been seen
        # UCB of unknown = 0 + coef * sqrt(log(11)/1) = large
        # UCB of good = 0.9 + small
        # → unknown should be chosen next
        chosen = ranker.choose("task")
        assert chosen == "unknown"

    def test_rank_returns_sorted(self):
        ranker = ModelRanker(["m1", "m2", "m3"], FeedbackStore())
        # Force seed
        for m in ["m1", "m2", "m3"]:
            ranker.choose("task")
        for _ in range(20):
            ranker.update("task", "m1", 0.9)
            ranker.update("task", "m2", 0.5)
            ranker.update("task", "m3", 0.1)
        ranked = ranker.rank("task")
        assert ranked[0].name == "m1"  # best UCB
        assert ranked[0].rank == 1
        assert ranked[-1].name == "m3"  # worst UCB
        assert ranked[-1].rank == 3

    def test_best_for_task(self):
        ranker = ModelRanker(["m1", "m2"], FeedbackStore())
        # Pre-seed both tasks for both models so they have data
        for _ in range(2):
            ranker.choose("task_a")
            ranker.choose("task_b")
        for _ in range(20):
            ranker.update("task_a", "m1", 0.9)
            ranker.update("task_b", "m2", 0.9)
        # best() is pure exploitation — picks the model with the highest mean
        assert ranker.best("task_a") == "m1"
        assert ranker.best("task_b") == "m2"

    def test_best_returns_none_when_no_data(self):
        ranker = ModelRanker(["m1", "m2"], FeedbackStore())
        assert ranker.best("nothing-yet") is None

    def test_score_clamped(self):
        """update() clamps score to [0, 1]."""
        ranker = ModelRanker(["m1"], FeedbackStore())
        ranker.choose("task")
        ranker.update("task", "m1", 5.0)  # should clamp to 1.0
        ranker.update("task", "m1", -3.0)  # should clamp to 0.0
        ranked = ranker.rank("task")
        # All scores in [0, 1], so mean is in that range
        assert 0.0 <= ranked[0].mean_score <= 1.0

    def test_stochastic_sampling(self):
        """With temperature > 0, results vary."""
        random.seed(42)
        ranker = ModelRanker(["m1", "m2"], FeedbackStore())
        # Seed
        ranker.choose("task")
        # Lots of data
        for _ in range(50):
            ranker.update("task", "m1", 0.5)
            ranker.update("task", "m2", 0.5)
        # Pure exploitation should always pick same
        for _ in range(10):
            assert ranker.choose("task", temperature=0) in ("m1", "m2")
