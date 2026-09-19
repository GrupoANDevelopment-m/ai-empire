"""
A/B Test — compare two model/prompt variants head-to-head.
Uses frequentist statistics (two-proportion z-test) for significance.
"""
from __future__ import annotations
import math
import time
import random
import logging
from typing import Callable, Any
from dataclasses import dataclass, field
from collections import defaultdict

log = logging.getLogger("empire.learning.abtest")


@dataclass
class ABResult:
    variant_a: str
    variant_b: str
    a_count: int
    b_count: int
    a_score: float
    b_score: float
    lift: float                  # (b - a) / a
    p_value: float               # two-sided p-value
    is_significant: bool         # p < 0.05
    winner: str | None           # "a" | "b" | None
    confidence: float            # 1 - p_value


class ABTest:
    """
    A/B test between two variants (models, prompts, strategies, etc.).

    Usage:
        test = ABTest(
            name="prompt-v2",
            variant_a=lambda: call_llm("Write a cold email: PROMPT_V1"),
            variant_b=lambda: call_llm("Write a cold email: PROMPT_V2"),
            score_fn=lambda output: llm_judge(output),  # 0-1
        )
        test.run_n(100)
        result = test.analyze()
        print(result.winner, result.confidence)
    """

    def __init__(
        self,
        name: str,
        variant_a: Callable[[], Any],
        variant_b: Callable[[], Any],
        score_fn: Callable[[Any], float],
        min_samples: int = 30,
    ):
        self.name = name
        self.variant_a = variant_a
        self.variant_b = variant_b
        self.score_fn = score_fn
        self.min_samples = min_samples

        self._a_scores: list[float] = []
        self._b_scores: list[float] = []

    def run_one(self) -> tuple[str, float]:
        """Run a single trial. Returns (variant, score)."""
        if random.random() < 0.5:
            output = self.variant_a()
            score = self.score_fn(output)
            self._a_scores.append(score)
            return "a", score
        else:
            output = self.variant_b()
            score = self.score_fn(output)
            self._b_scores.append(score)
            return "b", score

    def run_n(self, n: int) -> None:
        for _ in range(n):
            self.run_one()

    def analyze(self) -> ABResult:
        """Compute statistical analysis."""
        a_n = len(self._a_scores)
        b_n = len(self._b_scores)
        a_mean = sum(self._a_scores) / a_n if a_n else 0.0
        b_mean = sum(self._b_scores) / b_n if b_n else 0.0
        lift = (b_mean - a_mean) / a_mean if a_mean > 0 else 0.0

        # Two-sample z-test for difference of means (large-sample approximation)
        p_value = 1.0
        is_sig = False
        if a_n >= 5 and b_n >= 5:
            a_var = sum((x - a_mean) ** 2 for x in self._a_scores) / (a_n - 1) if a_n > 1 else 0
            b_var = sum((x - b_mean) ** 2 for x in self._b_scores) / (b_n - 1) if b_n > 1 else 0
            se = math.sqrt(a_var / a_n + b_var / b_n) if (a_n + b_n) > 0 else 1
            if se > 0:
                z = (b_mean - a_mean) / se
                # Two-tailed p-value (approximation)
                p_value = 2 * (1 - _normal_cdf(abs(z)))
                is_sig = p_value < 0.05 and (a_n + b_n) >= self.min_samples

        winner = None
        if is_sig:
            winner = "b" if b_mean > a_mean else "a"

        return ABResult(
            variant_a=f"{self.name}-A",
            variant_b=f"{self.name}-B",
            a_count=a_n,
            b_count=b_n,
            a_score=round(a_mean, 4),
            b_score=round(b_mean, 4),
            lift=round(lift, 4),
            p_value=round(p_value, 4),
            is_significant=is_sig,
            winner=winner,
            confidence=round(1 - p_value, 4),
        )


def _normal_cdf(x: float) -> float:
    """Approximation of the standard normal CDF (Abramowitz & Stegun 7.1.26)."""
    # Constants
    a1, a2, a3, a4, a5 = (
        0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    )
    p = 0.3275911
    sign = 1 if x >= 0 else -1
    x = abs(x) / math.sqrt(2)
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
    return 0.5 * (1.0 + sign * y)
