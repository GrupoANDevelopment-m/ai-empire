"""
Procedural memory — knowledge about HOW to do things.

Stores procedures, playbooks, learned strategies. Versioned.

Used by:
  - Reasoning engine (uses procedures to break down goals)
  - Lesson extraction (turns outcomes into procedures)
  - Self-improvement (procedures evolve with experience)
"""
import time
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


PROCEDURAL_DIR = Path("/workspace/ai-empire/empire_data/procedural")
PROCEDURAL_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Procedure:
    id: str
    name: str
    trigger: str                    # when to use this procedure (regex or text match)
    steps: List[str]                # ordered steps
    rationale: str = ""             # why this works
    confidence: float = 0.5         # 0-1, increases with successful uses
    uses: int = 0                   # how many times applied
    successes: int = 0
    failures: int = 0
    version: int = 1
    parent_id: Optional[str] = None  # for evolution
    tenant: str = "default"
    source: str = ""                # "manual", "lesson-extraction", "forge"
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProceduralMemory:
    """JSON-backed procedural memory with versioning."""

    def __init__(self, store_dir: Path = None):
        self.store_dir = store_dir or PROCEDURAL_DIR
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.procedures: Dict[str, Procedure] = {}
        self._load()

    def _load(self):
        meta_file = self.store_dir / "procedures.json"
        if meta_file.exists():
            try:
                data = json.loads(meta_file.read_text())
                for p in data.get("procedures", []):
                    self.procedures[p["id"]] = Procedure(**p)
            except Exception as e:
                print(f"[procedural] failed to load: {e}")

    def _save(self):
        meta = {"version": 1, "procedures": [asdict(p) for p in self.procedures.values()]}
        (self.store_dir / "procedures.json").write_text(json.dumps(meta, indent=2, default=str))

    def add(
        self,
        name: str,
        trigger: str,
        steps: List[str],
        rationale: str = "",
        source: str = "manual",
        tenant: str = "default",
        parent_id: Optional[str] = None,
    ) -> Procedure:
        """Add a new procedure (or new version of existing)."""
        pid = f"pr-{hashlib.md5(f'{name}:{tenant}'.encode()).hexdigest()[:10]}"
        # If existing, bump version
        existing = self.procedures.get(pid)
        if existing:
            new_version = existing.version + 1
            new_id = f"{pid}-v{new_version}"
            proc = Procedure(
                id=new_id, name=name, trigger=trigger, steps=steps,
                rationale=rationale, version=new_version,
                parent_id=existing.id, tenant=tenant, source=source,
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
        else:
            proc = Procedure(
                id=pid, name=name, trigger=trigger, steps=steps,
                rationale=rationale, version=1,
                parent_id=parent_id, tenant=tenant, source=source,
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
        self.procedures[proc.id] = proc
        self._save()
        return proc

    def record_outcome(self, proc_id: str, success: bool):
        proc = self.procedures.get(proc_id)
        if not proc:
            return
        proc.uses += 1
        if success:
            proc.successes += 1
        else:
            proc.failures += 1
        # Update confidence: P(success) with smoothing
        total = proc.successes + proc.failures
        proc.confidence = (proc.successes + 1) / (total + 2)
        proc.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()

    def get(self, proc_id: str) -> Optional[Procedure]:
        return self.procedures.get(proc_id)

    def find_by_trigger(self, query: str, tenant: str = "default") -> List[Procedure]:
        """Find procedures whose trigger matches the query."""
        import re
        results = []
        for p in self.procedures.values():
            if p.tenant != tenant:
                continue
            try:
                if re.search(p.trigger, query, re.IGNORECASE):
                    results.append(p)
            except re.error:
                if p.trigger.lower() in query.lower():
                    results.append(p)
        # Sort by confidence
        return sorted(results, key=lambda p: p.confidence, reverse=True)

    def list(self, tenant: str = None) -> List[Procedure]:
        items = list(self.procedures.values())
        if tenant:
            items = [p for p in items if p.tenant == tenant]
        return sorted(items, key=lambda p: p.confidence, reverse=True)

    def delete(self, proc_id: str):
        if proc_id in self.procedures:
            del self.procedures[proc_id]
            self._save()

    def stats(self) -> Dict[str, Any]:
        items = list(self.procedures.values())
        return {
            "procedure_count": len(items),
            "total_uses": sum(p.uses for p in items),
            "high_confidence": sum(1 for p in items if p.confidence > 0.7),
            "low_confidence": sum(1 for p in items if p.confidence < 0.4),
            "by_tenant": {p.tenant: 1 for p in items},
        }


_PROCEDURAL: Optional[ProceduralMemory] = None


def get_procedural() -> ProceduralMemory:
    global _PROCEDURAL
    if _PROCEDURAL is None:
        _PROCEDURAL = ProceduralMemory()
    return _PROCEDURAL
