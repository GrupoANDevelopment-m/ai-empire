"""
Unified memory facade — combines all 4 memory types.

Provides high-level operations like:
  - remember() — store in appropriate memory
  - recall() — search across all memory types
  - reflect() — extract lessons from recent episodes
  - consolidate() — promote short-term to long-term
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from empire.memory.episodic import get_episodic, Episode
from empire.memory.semantic import get_semantic, Chunk
from empire.memory.procedural import get_procedural, Procedure
from empire.memory.working import get_working_memory, WorkingMemory


@dataclass
class MemoryQuery:
    query: str
    tenant: str = "default"
    session: str = "default"
    k: int = 5
    include_episodic: bool = True
    include_semantic: bool = True
    include_procedural: bool = True


@dataclass
class MemoryResult:
    episodes: List[Episode]
    chunks: List[tuple]  # [(Chunk, score)]
    procedures: List[Procedure]
    working: Dict[str, Any]


class UnifiedMemory:
    """Façade over all 4 memory systems."""

    def __init__(self):
        self.episodic = get_episodic()
        self.semantic = get_semantic()
        self.procedural = get_procedural()
        self.working: Dict[str, WorkingMemory] = {}

    def get_working(self, session: str = "default") -> WorkingMemory:
        if session not in self.working:
            self.working[session] = get_working_memory(session)
        return self.working[session]

    def remember_episode(self, actor: str, context: Dict[str, Any],
                        action: str, outcome: str,
                        details: Dict[str, Any] = None,
                        lesson: str = "", tenant: str = "default") -> Episode:
        """Store in episodic memory."""
        ep = self.episodic.record(actor, context, action, outcome,
                                  details, lesson, tenant)
        # Index in semantic too (for similarity search)
        if lesson:
            self.semantic.add(
                f"{action} -> {outcome}. {lesson}",
                metadata={"outcome": outcome, "action": action},
                source="episode", source_id=ep.id, tenant=tenant
            )
        return ep

    def remember_knowledge(self, text: str, *,
                          source: str = "manual",
                          source_id: str = "",
                          metadata: Dict[str, Any] = None,
                          tenant: str = "default") -> Chunk:
        """Store in semantic memory."""
        return self.semantic.add(text, metadata=metadata or {},
                                 source=source, source_id=source_id,
                                 tenant=tenant)

    def remember_procedure(self, name: str, trigger: str, steps: List[str],
                          rationale: str = "", source: str = "manual",
                          tenant: str = "default") -> Procedure:
        """Store in procedural memory."""
        return self.procedural.add(name, trigger, steps, rationale,
                                    source, tenant)

    def recall(self, mq: MemoryQuery) -> MemoryResult:
        """Search across all memory types."""
        episodes = []
        chunks = []
        procedures = []

        if mq.include_episodic:
            # Search episodes by lesson + context text
            episodes = self.episodic.search_by_lesson(
                mq.query, tenant=mq.tenant, limit=mq.k
            )

        if mq.include_semantic:
            chunks = self.semantic.search(
                mq.query, k=mq.k, tenant=mq.tenant
            )

        if mq.include_procedural:
            procedures = self.procedural.find_by_trigger(mq.query, mq.tenant)

        working = self.get_working(mq.session).snapshot()

        return MemoryResult(
            episodes=episodes,
            chunks=chunks,
            procedures=procedures,
            working=working,
        )

    def reflect(self, session: str = "default", tenant: str = "default") -> str:
        """
        Reflect on recent episodes. Extract lesson if pattern emerges.

        This is the ACAMR "Lesson Extraction" stage.
        """
        recent = self.episodic.query(tenant=tenant, limit=20)
        failures = [e for e in recent if e.outcome == "failure"]
        if len(failures) < 3:
            return ""

        # Find common pattern
        from collections import Counter
        actions = Counter(e.action for e in failures)
        most_common = actions.most_common(1)
        if not most_common:
            return ""
        action, count = most_common
        if count < 3:
            return ""

        # Generate lesson
        failure_details = [e for e in failures if e.action == action]
        lessons = [e.lesson for e in failure_details if e.lesson]
        if lessons:
            lesson = lessons[0]
        else:
            # Build lesson from details
            detail_strs = []
            for e in failure_details[:3]:
                d = e.details.get("error", "") or e.details.get("reason", "")
                if d:
                    detail_strs.append(d[:100])
            lesson = (
                f"Falhas repetidas em '{action}' ({count}x). "
                f"Causas comuns: {'; '.join(detail_strs)[:300]}"
            )

        # Store lesson as new procedure
        proc = self.remember_procedure(
            name=f"Avoid: {action}",
            trigger=action,
            steps=[f"Avoid common cause: {lesson[:200]}"],
            rationale=f"Learned from {count} failures",
            source="lesson-extraction",
            tenant=tenant,
        )

        # Add lesson to source episodes
        for e in failure_details:
            self.episodic.add_lesson(e.id, lesson)

        # Index lesson in semantic
        self.remember_knowledge(
            f"Lesson about '{action}': {lesson}",
            source="reflection", source_id=proc.id, tenant=tenant
        )

        return lesson

    def consolidate(self, session: str = "default", tenant: str = "default") -> int:
        """
        Promote episodic lessons into semantic + procedural memory.
        Returns count of items consolidated.
        """
        # Find episodes with lessons that haven't been promoted
        episodes_with_lessons = [
            e for e in self.episodic.query(tenant=tenant, limit=100)
            if e.lesson
        ]
        promoted = 0
        for ep in episodes_with_lessons:
            # Check if already in semantic
            existing = self.semantic.search(ep.lesson, k=1, tenant=tenant)
            if existing and existing[0][1] > 0.85:
                continue
            self.remember_knowledge(
                ep.lesson,
                source="consolidated-episode",
                source_id=ep.id,
                tenant=tenant,
            )
            promoted += 1
        return promoted

    def stats(self, tenant: str = "default") -> Dict[str, Any]:
        return {
            "episodic": self.episodic.stats(tenant=tenant),
            "semantic": self.semantic.stats(),
            "procedural": self.procedural.stats(),
            "working_sessions": len(self.working),
        }


_UNIFIED: Optional[UnifiedMemory] = None


def get_memory() -> UnifiedMemory:
    global _UNIFIED
    if _UNIFIED is None:
        _UNIFIED = UnifiedMemory()
    return _UNIFIED
