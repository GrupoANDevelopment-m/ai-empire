"""
Feedback Store — record outcomes of every agent run.
In-memory by default; pluggable to Postgres/Redis.
"""
from __future__ import annotations
import time
import json
import logging
import threading
from collections import defaultdict
from enum import Enum
from typing import Any
from dataclasses import dataclass, field, asdict

log = logging.getLogger("empire.learning.feedback")


class FeedbackType(str, Enum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    RATING = "rating"          # numeric 1-5
    CONVERSION = "conversion"  # lead → meeting, post → click, etc.
    REPLY = "reply"            # outreach got a reply
    BOUNCE = "bounce"          # outreach bounced
    CORRECTION = "correction"  # human corrected the output
    IMPLICIT = "implicit"      # derived from downstream actions


@dataclass
class Feedback:
    id: str
    feedback_type: FeedbackType
    subject: str          # what was being evaluated: "lead:abc", "content:xyz", "model:claude-sonnet-4-5"
    score: float          # 0.0 - 1.0 normalized
    raw_value: Any = None # original value (rating 1-5, "positive", etc.)
    context: dict = field(default_factory=dict)  # thread_id, model, prompt_hash, etc.
    created_at: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


class FeedbackStore:
    """
    Records and aggregates feedback. Powers A/B tests and model ranking.

    Usage:
        store = FeedbackStore()
        store.record(Feedback(
            id="fb-1",
            feedback_type=FeedbackType.CONVERSION,
            subject="content:post-123",
            score=0.8,
            context={"model": "claude-sonnet-4-5", "thread_id": "t1"},
        ))
        agg = store.aggregate_by("model")
    """

    def __init__(self):
        self._feedback: list[Feedback] = []
        self._lock = threading.RLock()

    def record(self, fb: Feedback) -> None:
        with self._lock:
            self._feedback.append(fb)
        log.debug(f"Recorded feedback: {fb.subject} = {fb.score}")

    def record_many(self, fbs: list[Feedback]) -> None:
        for fb in fbs:
            self.record(fb)

    def get(self, subject: str | None = None) -> list[Feedback]:
        with self._lock:
            if subject is None:
                return list(self._feedback)
            return [f for f in self._feedback if f.subject == subject]

    def aggregate_by(self, dimension: str = "model") -> dict[str, dict]:
        """
        Aggregate feedback by a context dimension (e.g. "model", "agent", "channel").
        Returns: {dimension_value: {count, avg_score, thumbs_up, thumbs_down, ...}}
        """
        with self._lock:
            groups: dict[str, list[Feedback]] = defaultdict(list)
            for fb in self._feedback:
                key = str(fb.context.get(dimension, "unknown"))
                groups[key].append(fb)

            result = {}
            for key, items in groups.items():
                count = len(items)
                avg = sum(i.score for i in items) / count if count else 0.0
                pos = sum(1 for i in items if i.score >= 0.5)
                neg = sum(1 for i in items if i.score < 0.5)
                by_type: dict[str, int] = defaultdict(int)
                for i in items:
                    by_type[i.feedback_type.value] += 1
                result[key] = {
                    "count": count,
                    "avg_score": round(avg, 4),
                    "thumbs_up": pos,
                    "thumbs_down": neg,
                    "by_type": dict(by_type),
                }
            return result

    def export(self) -> list[dict]:
        with self._lock:
            return [asdict(f) for f in self._feedback]

    def clear(self) -> None:
        with self._lock:
            self._feedback.clear()

    def __len__(self) -> int:
        return len(self._feedback)
