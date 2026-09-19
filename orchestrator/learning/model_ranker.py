"""
Model Ranker — pick the best model for a given task type
based on accumulated feedback. Multi-armed bandit style.
"""
from __future__ import annotations
import math
import random
import logging
from dataclasses import dataclass
from typing import Any
from collections import defaultdict

from .feedback_store import FeedbackStore, Feedback, FeedbackType

log = logging.getLogger("empire.learning.ranker")


@dataclass
class ModelScore:
    name: str
    count: int
    mean_score: float
    ucb: float               # upper confidence bound
    exploration_bonus: float
    rank: int


class ModelRanker:
    """
    Multi-armed bandit ranker. Balances exploitation (best model so far)
    and exploration (try under-sampled models) using UCB1.

    Usage:
        ranker = ModelRanker(["claude-sonnet-4-5", "gpt-4o", "llama3.3"], feedback_store)
        # At decision time:
        model = ranker.choose(task_type="lead_qualification")
        # After feedback:
        ranker.update("lead_qualification", "claude-sonnet-4-5", score=0.9)
    """

    def __init__(
        self,
        models: list[str],
        feedback_store: FeedbackStore,
        exploration_coef: float = 1.5,
    ):
        self.models = models
        self.store = feedback_store
        self.coef = exploration_coef

        # Per-task-type stats: {task: {model: [scores]}}
        self._stats: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

    def choose(self, task_type: str = "default", temperature: float = 0.0) -> str:
        """
        Pick the best model for this task.
        If temperature > 0, sample stochastically weighted by UCB.
        """
        stats = self._stats[task_type]
        total = sum(len(v) for v in stats.values()) + 1

        # Ensure every model has been tried at least once
        for m in self.models:
            if m not in stats:
                stats[m] = []
                return m

        scores = []
        for m in self.models:
            ms = stats.get(m, [])
            count = len(ms) if ms else 0
            mean = sum(ms) / count if count else 0.0
            bonus = self.coef * math.sqrt(math.log(total) / max(count, 1))
            ucb = mean + bonus
            scores.append((m, ucb, mean, count, bonus))

        if temperature > 0:
            # Softmax sampling weighted by UCB
            exps = [math.exp(s[1] / max(temperature, 0.01)) for s in scores]
            total_e = sum(exps)
            r = random.random() * total_e
            cum = 0
            for i, e in enumerate(exps):
                cum += e
                if cum >= r:
                    return scores[i][0]

        # Pure exploitation: pick highest UCB
        scores.sort(key=lambda s: s[1], reverse=True)
        return scores[0][0]

    def update(self, task_type: str, model: str, score: float) -> None:
        """Record an outcome for a model on a task type."""
        score = max(0.0, min(1.0, score))
        self._stats[task_type][model].append(score)
        # Also push to feedback store
        self.store.record(Feedback(
            id=f"rank-{task_type}-{model}-{len(self._stats[task_type][model])}",
            feedback_type=FeedbackType.RATING,
            subject=f"model:{model}",
            score=score,
            context={"task_type": task_type, "model": model},
        ))

    def rank(self, task_type: str = "default") -> list[ModelScore]:
        """Return sorted ranking of models for a task type."""
        stats = self._stats[task_type]
        total = sum(len(v) for v in stats.values()) + 1
        scores = []
        for m in self.models:
            ms = stats.get(m, [])
            count = len(ms)
            mean = sum(ms) / count if count else 0.0
            bonus = self.coef * math.sqrt(math.log(total) / max(count, 1))
            ucb = mean + bonus
            scores.append(ModelScore(
                name=m, count=count, mean_score=round(mean, 4),
                ucb=round(ucb, 4), exploration_bonus=round(bonus, 4),
                rank=0,
            ))
        scores.sort(key=lambda s: s.ucb, reverse=True)
        for i, s in enumerate(scores, 1):
            s.rank = i
        return scores

    def best_for_task(self, task_type: str) -> str:
        return self.choose(task_type)

    def best(self, task_type: str = "default") -> str | None:
        """
        Pure exploitation: return the model with the highest mean score for this task.
        Only considers models that have at least one data point.
        Returns None if no model has data yet.
        """
        stats = self._stats.get(task_type, {})
        candidates = [(m, sum(s) / len(s)) for m, s in stats.items() if s]
        if not candidates:
            return None
        # Tie-break by name for determinism
        candidates.sort(key=lambda x: (-x[1], x[0]))
        return candidates[0][0]
