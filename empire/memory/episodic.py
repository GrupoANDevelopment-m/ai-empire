"""
Episodic memory — records of past interactions, indexed by time and context.

Each episode is a tuple of (timestamp, actor, context, action, outcome, lesson).
Stored in SQLite (real DB) so it survives restarts. Append-only by design.

Used by:
  - Reflect node (looks at similar past episodes)
  - Lesson extraction
  - Debugging ("we tried X last week and it failed because Y")
"""
import time
import json
import sqlite3
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


EPISODIC_DB = Path("/workspace/ai-empire/empire_data/episodic.sqlite3")


@dataclass
class Episode:
    id: str
    timestamp: str
    tenant: str
    actor: str                       # who/what triggered this (user, agent, system)
    context: Dict[str, Any]          # input, state, goal
    action: str                      # what was attempted
    outcome: str                     # success, failure, partial
    details: Dict[str, Any] = field(default_factory=dict)
    lesson: str = ""                 # extracted lesson (empty initially)
    embedding: Optional[List[float]] = None  # filled by semantic memory
    related_episodes: List[str] = field(default_factory=list)


class EpisodicMemory:
    """SQLite-backed episodic memory store."""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or EPISODIC_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    tenant TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    context TEXT NOT NULL,
                    action TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    details TEXT DEFAULT '{}',
                    lesson TEXT DEFAULT '',
                    embedding BLOB,
                    related_episodes TEXT DEFAULT '[]'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tenant_ts ON episodes (tenant, timestamp DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_outcome ON episodes (outcome)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_action ON episodes (action)")

    def record(
        self,
        actor: str,
        context: Dict[str, Any],
        action: str,
        outcome: str,
        details: Dict[str, Any] = None,
        lesson: str = "",
        tenant: str = "default",
    ) -> Episode:
        """Record a new episode. Returns the Episode."""
        eid = f"ep-{int(time.time() * 1000)}-{hashlib.md5(action.encode()).hexdigest()[:6]}"
        ep = Episode(
            id=eid,
            timestamp=datetime.now(timezone.utc).isoformat(),
            tenant=tenant,
            actor=actor,
            context=context,
            action=action,
            outcome=outcome,
            details=details or {},
            lesson=lesson,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO episodes
                   (id, timestamp, tenant, actor, context, action, outcome, details, lesson, related_episodes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (eid, ep.timestamp, tenant, actor,
                 json.dumps(context), action, outcome,
                 json.dumps(details or {}), lesson, "[]")
            )
        return ep

    def add_lesson(self, episode_id: str, lesson: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE episodes SET lesson = ? WHERE id = ?",
                (lesson, episode_id)
            )

    def get(self, episode_id: str) -> Optional[Episode]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM episodes WHERE id = ?", (episode_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_episode(row)

    def query(
        self,
        tenant: str = None,
        outcome: str = None,
        action: str = None,
        limit: int = 50,
        since_ts: str = None,
    ) -> List[Episode]:
        sql = "SELECT * FROM episodes WHERE 1=1"
        params = []
        if tenant:
            sql += " AND tenant = ?"
            params.append(tenant)
        if outcome:
            sql += " AND outcome = ?"
            params.append(outcome)
        if action:
            sql += " AND action = ?"
            params.append(action)
        if since_ts:
            sql += " AND timestamp >= ?"
            params.append(since_ts)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_episode(r) for r in rows]

    def search_by_lesson(self, query_text: str, tenant: str = "default",
                          limit: int = 20) -> List[Episode]:
        """Naive text search in lesson/context fields."""
        sql = """SELECT * FROM episodes
                 WHERE tenant = ? AND (lesson LIKE ? OR context LIKE ? OR action LIKE ?)
                 ORDER BY timestamp DESC LIMIT ?"""
        pattern = f"%{query_text}%"
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(sql, (tenant, pattern, pattern, pattern, limit)).fetchall()
        return [self._row_to_episode(r) for r in rows]

    def stats(self, tenant: str = None) -> Dict[str, Any]:
        sql = "SELECT outcome, COUNT(*) FROM episodes"
        params = []
        if tenant:
            sql += " WHERE tenant = ?"
            params.append(tenant)
        sql += " GROUP BY outcome"
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        by_outcome = {r[0]: r[1] for r in rows}
        total = sum(by_outcome.values())
        return {
            "total_episodes": total,
            "by_outcome": by_outcome,
            "lessons_learned": sum(1 for r in conn.execute(
                "SELECT 1 FROM episodes WHERE lesson != '' AND lesson IS NOT NULL"
            ).fetchall()),
        }

    def _row_to_episode(self, row) -> Episode:
        try:
            return Episode(
                id=row[0],
                timestamp=row[1],
                tenant=row[2],
                actor=row[3],
                context=json.loads(row[4]) if row[4] else {},
                action=row[5],
                outcome=row[6],
                details=json.loads(row[7]) if row[7] else {},
                lesson=row[8] or "",
                embedding=list(row[9]) if row[9] else None,
                related_episodes=json.loads(row[10]) if row[10] else [],
            )
        except Exception as e:
            print(f"[episodic] failed to parse row: {e}")
            return None


_EPISODIC: Optional[EpisodicMemory] = None


def get_episodic() -> EpisodicMemory:
    global _EPISODIC
    if _EPISODIC is None:
        _EPISODIC = EpisodicMemory()
    return _EPISODIC
