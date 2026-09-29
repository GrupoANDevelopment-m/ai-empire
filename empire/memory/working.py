"""
Working memory — current session state and active context.

In-memory only (resets on restart). Holds:
  - Active goals
  - Current plan
  - Hypothesis state
  - Reflection state

Used by:
  - Cognitive loop (each node reads/writes working memory)
  - Reasoning engine (knows current context)
  - Reflect node (compares outcome against plan)
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
import threading


@dataclass
class Goal:
    id: str
    description: str
    priority: int = 5            # 1-10
    metric: str = ""             # measurable
    target: Any = None
    current: Any = None
    status: str = "active"        # active, paused, achieved, abandoned
    created_at: str = ""


@dataclass
class Plan:
    id: str
    goal_id: str
    steps: List[Dict[str, Any]]  # [{action, expected_outcome, status}]
    current_step: int = 0
    status: str = "planning"      # planning, executing, blocked, complete
    created_at: str = ""


@dataclass
class Hypothesis:
    id: str
    description: str
    approach: str
    confidence: float = 0.5
    evidence: List[str] = field(default_factory=list)
    status: str = "pending"      # pending, running, validated, rejected
    result: Optional[Dict[str, Any]] = None


class WorkingMemory:
    """Thread-local in-memory state."""

    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.goals: Dict[str, Goal] = {}
        self.plans: Dict[str, Plan] = {}
        self.hypotheses: Dict[str, Hypothesis] = {}
        self.context: Dict[str, Any] = {}
        self.last_reflection: Optional[str] = None
        self.lock = threading.RLock()

    def add_goal(self, description: str, priority: int = 5,
                 metric: str = "", target: Any = None) -> Goal:
        gid = f"g-{len(self.goals) + 1}"
        g = Goal(id=gid, description=description, priority=priority,
                metric=metric, target=target,
                created_at=datetime.now(timezone.utc).isoformat())
        with self.lock:
            self.goals[gid] = g
        return g

    def update_goal_progress(self, goal_id: str, current: Any, status: str = None):
        with self.lock:
            g = self.goals.get(goal_id)
            if g:
                g.current = current
                if status:
                    g.status = status

    def add_plan(self, goal_id: str, steps: List[Dict]) -> Plan:
        pid = f"p-{len(self.plans) + 1}"
        p = Plan(id=pid, goal_id=goal_id, steps=steps,
                created_at=datetime.now(timezone.utc).isoformat())
        with self.lock:
            self.plans[pid] = p
        return p

    def step_plan(self, plan_id: str, status: str = "done") -> bool:
        """Advance plan by one step. Returns True if plan completed."""
        with self.lock:
            p = self.plans.get(plan_id)
            if not p:
                return False
            if p.current_step >= len(p.steps):
                p.status = "complete"
                return True
            p.steps[p.current_step]["status"] = status
            p.current_step += 1
            if p.current_step >= len(p.steps):
                p.status = "complete"
                return True
            p.status = "executing"
            return False

    def add_hypothesis(self, description: str, approach: str,
                       confidence: float = 0.5) -> Hypothesis:
        hid = f"h-{len(self.hypotheses) + 1}"
        h = Hypothesis(id=hid, description=description, approach=approach,
                      confidence=confidence)
        with self.lock:
            self.hypotheses[hid] = h
        return h

    def record_evidence(self, hid: str, evidence: str, validated: bool = None):
        with self.lock:
            h = self.hypotheses.get(hid)
            if h:
                h.evidence.append(evidence)
                if validated is True:
                    h.status = "validated"
                    h.confidence = min(1.0, h.confidence + 0.15)
                elif validated is False:
                    h.status = "rejected"
                    h.confidence = max(0.0, h.confidence - 0.2)

    def snapshot(self) -> Dict[str, Any]:
        """Read-only snapshot of current state."""
        with self.lock:
            return {
                "session_id": self.session_id,
                "goals": [asdict(g) for g in self.goals.values()],
                "plans": [asdict(p) for p in self.plans.values()],
                "hypotheses": [asdict(h) for h in self.hypotheses.values()],
                "context": dict(self.context),
                "last_reflection": self.last_reflection,
            }

    def set_context(self, key: str, value: Any):
        with self.lock:
            self.context[key] = value

    def get_context(self, key: str, default=None):
        with self.lock:
            return self.context.get(key, default)


# Per-session registry
_sessions: Dict[str, WorkingMemory] = {}
_sessions_lock = threading.Lock()


def get_working_memory(session_id: str = "default") -> WorkingMemory:
    global _sessions
    with _sessions_lock:
        if session_id not in _sessions:
            _sessions[session_id] = WorkingMemory(session_id)
        return _sessions[session_id]


def clear_session(session_id: str):
    global _sessions
    with _sessions_lock:
        _sessions.pop(session_id, None)
