"""
Cognitive Loop — Reason, Reflect, Plan, Hypothesis, Evaluate.

Implements the ACAMR cognitive loop stages:
  1. Perception   → read world state, input, memory
  2. Goal Engine  → identify current goals
  3. Reasoning    → decompose goal into steps, find procedures
  4. Hypothesis   → generate 3 candidate approaches
  5. Plan         → build execution plan with steps
  6. Execute      → run plan via capabilities
  7. Evidence     → collect outcomes
  8. Evaluate     → score hypotheses, pick winner
  9. Gap Detect   → if all failed, identify what's missing
  10. Reflect     → extract lesson, store in memory
  11. Update Index → record new capability

Each call returns a CognitiveTrace for observability.
"""
import json
import asyncio
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum

from empire.memory.unified import get_memory, MemoryQuery, UnifiedMemory
from empire.memory.working import get_working_memory, WorkingMemory
from empire.registry.discovery import (
    discover_all_capabilities, build_capability_prompt
)


class Stage(str, Enum):
    PERCEPTION = "perception"
    GOAL = "goal"
    REASONING = "reasoning"
    HYPOTHESIS = "hypothesis"
    PLANNING = "planning"
    EXECUTION = "execution"
    EVIDENCE = "evidence"
    EVALUATION = "evaluation"
    GAP_DETECT = "gap_detect"
    REFLECTION = "reflection"
    COMPLETE = "complete"


@dataclass
class CognitiveTrace:
    session: str
    tenant: str
    started_at: str
    stages: List[Dict[str, Any]] = field(default_factory=list)
    final_outcome: Optional[str] = None
    lesson_learned: Optional[str] = None
    gap_detected: Optional[str] = None
    capability_used: Optional[str] = None


@dataclass
class Step:
    action: str
    capability: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    expected_outcome: str = ""
    status: str = "pending"
    result: Optional[Dict[str, Any]] = None


class CognitiveLoop:
    """Drives the ACAMR cognitive loop."""

    def __init__(self):
        self.mem = get_memory()

    async def think(
        self,
        goal: str,
        *,
        session: str = "default",
        tenant: str = "default",
        max_hypotheses: int = 3,
        use_llm: bool = True,
    ) -> CognitiveTrace:
        """Run a full cognitive loop for a goal."""
        trace = CognitiveTrace(
            session=session, tenant=tenant,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        working = self.mem.get_working(session)

        # 1. PERCEPTION — read context
        ctx = await self._perception(goal, session, tenant)
        self._record_stage(trace, Stage.PERCEPTION, ctx)

        # 2. GOAL — register active goal
        goal_obj = working.add_goal(goal, priority=8, metric="completion")
        self._record_stage(trace, Stage.GOAL, {"goal_id": goal_obj.id})

        # 3. REASONING — decompose goal using memory + capabilities
        reasoning = await self._reasoning(goal, ctx, session, tenant, use_llm)
        self._record_stage(trace, Stage.REASONING, reasoning)

        # 4. HYPOTHESIS — generate candidate approaches
        hypotheses = self._hypothesize(reasoning, max_hypotheses)
        self._record_stage(trace, Stage.HYPOTHESIS,
                           {"count": len(hypotheses),
                            "descriptions": [h.description for h in hypotheses]})

        # 5. PLANNING — pick best, build plan
        plan = self._plan(goal_obj, hypotheses[0], reasoning)
        # plan.steps is already a list of dicts (asdict'd in _plan)
        working.add_plan(goal_obj.id, plan.steps)
        self._record_stage(trace, Stage.PLANNING,
                           {"plan_id": plan.id if hasattr(plan, 'id') else 'n/a',
                            "steps": len(plan.steps) if hasattr(plan, 'steps') else len(plan)})

        # 6. EXECUTION — execute plan steps (synthesized — real impl calls tools)
        results = await self._execute(plan, tenant, session)
        self._record_stage(trace, Stage.EXECUTION,
                           {"steps_completed": sum(1 for r in results if r.get("success"))})

        # 7. EVIDENCE — collect outcomes
        evidence = self._evidence(results)
        self._record_stage(trace, Stage.EVIDENCE, evidence)

        # 8. EVALUATION — score and pick winner
        evaluation = self._evaluate(evidence, hypotheses)
        self._record_stage(trace, Stage.EVALUATION, evaluation)

        # 9. GAP DETECT — if all failed
        gap = None
        if not evaluation.get("any_succeeded"):
            gap = self._detect_gap(goal, evidence, capabilities=ctx.get("capabilities", {}))
            trace.gap_detected = gap
            self._record_stage(trace, Stage.GAP_DETECT, {"gap": gap})

        # 10. REFLECTION — extract lesson, store in memory
        lesson = self._reflect(goal, results, evaluation, gap, tenant, session)
        trace.lesson_learned = lesson
        self._record_stage(trace, Stage.REFLECTION, {"lesson": lesson[:300]})

        trace.final_outcome = "success" if evaluation.get("any_succeeded") else "failure"
        trace.capability_used = hypotheses[0].approach if hypotheses else None
        working.set_context("last_trace", asdict(trace))

        self._record_stage(trace, Stage.COMPLETE, {"outcome": trace.final_outcome})
        return trace

    # ── Stage implementations ──────────────────────────────────────────────

    async def _perception(self, goal: str, session: str, tenant: str) -> Dict[str, Any]:
        caps = discover_all_capabilities()
        return {
            "goal": goal,
            "capabilities": caps,
            "tenant": tenant,
            "session": session,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _reasoning(self, goal: str, ctx: Dict[str, Any],
                         session: str, tenant: str,
                         use_llm: bool) -> Dict[str, Any]:
        # Recall relevant memory
        mq = MemoryQuery(query=goal, tenant=tenant, session=session, k=3)
        recall = self.mem.recall(mq)

        # Find relevant procedures
        procedures = [p for p in recall.procedures if p.confidence > 0.4]

        # Decompose goal (heuristic — LLM would do better)
        steps = self._decompose(goal, procedures)

        return {
            "recall_episodes": len(recall.episodes),
            "recall_chunks": len(recall.chunks),
            "procedures_found": len(procedures),
            "procedure_names": [p.name for p in procedures],
            "decomposed_steps": steps,
            "top_chunk_scores": [(c.text[:80], s) for c, s in recall.chunks[:3]],
        }

    def _decompose(self, goal: str, procedures: List) -> List[str]:
        """Heuristic decomposition. Real: use LLM."""
        steps = []
        # If we have a procedure that matches, use its steps
        if procedures:
            top = procedures[0]
            steps = list(top.steps)
        else:
            # Generic decomposition based on goal keywords
            gl = goal.lower()
            if "lead" in gl:
                steps = [
                    "Buscar leads qualificados via icp_scorer",
                    "Validar canais de contato disponíveis",
                    "Draftar mensagem de outreach",
                ]
            elif "mrr" in gl or "receita" in gl:
                steps = [
                    "Calcular MRR via mrr_calculator",
                    "Comparar com target mensal",
                    "Reportar variance",
                ]
            elif "churn" in gl:
                steps = [
                    "Calcular churn_probability por cohort",
                    "Identificar sinais críticos",
                    "Recomendar ação de retenção",
                ]
            else:
                steps = [
                    "Analisar objetivo via memória semântica",
                    "Identificar capabilities disponíveis",
                    "Executar via tools de skill",
                    "Medir outcome e refletir",
                ]
        return steps

    def _hypothesize(self, reasoning: Dict[str, Any], max_n: int) -> List:
        """Generate candidate approaches."""
        from empire.memory.working import Hypothesis
        base_steps = reasoning.get("decomposed_steps", [])
        hypotheses = []

        # Hypothesis 1: direct execution
        h1 = Hypothesis(
            id="h1",
            description="Execução direta dos steps com capabilities disponíveis",
            approach="direct",
            confidence=0.7
        )
        hypotheses.append(h1)

        # Hypothesis 2: use procedure if available
        if reasoning.get("procedure_names"):
            h2 = Hypothesis(
                id="h2",
                description=f"Seguir procedure validado: {reasoning['procedure_names'][0]}",
                approach="procedure-driven",
                confidence=0.8,
            )
            hypotheses.append(h2)

        # Hypothesis 3: forge new tool if needed
        h3 = Hypothesis(
            id="h3",
            description="Se capabilities insuficientes, gerar tool via Forge",
            approach="forge-fallback",
            confidence=0.5,
        )
        hypotheses.append(h3)

        return hypotheses[:max_n]

    def _plan(self, goal_obj, top_hypothesis, reasoning: Dict[str, Any]):
        """Build execution plan."""
        from empire.memory.working import Plan
        steps = []
        for i, s in enumerate(reasoning.get("decomposed_steps", [])):
            steps.append(Step(
                action=s,
                capability=self._infer_capability(s),
                expected_outcome=f"Step {i+1} complete",
            ))
        p = Plan(
            id=f"p-{goal_obj.id}",
            goal_id=goal_obj.id,
            steps=[asdict(s) for s in steps],
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return p

    def _infer_capability(self, step_desc: str) -> str:
        """Map step description to a capability name."""
        sl = step_desc.lower()
        if "mrr" in sl or "receita" in sl:
            return "skill:saas-b2b/mrr_calculator"
        if "icp" in sl or "score" in sl or "qualificar" in sl:
            return "skill:saas-b2b/icp_scorer"
        if "churn" in sl:
            return "skill:saas-b2b/churn_predictor"
        if "outreach" in sl or "mensagem" in sl:
            return "skill:saas-b2b/templates/cold_outreach_b2b"
        return ""

    async def _execute(self, plan, tenant: str, session: str) -> List[Dict]:
        """Execute plan steps. Synthesized for now."""
        results = []
        # plan is a Plan dataclass with .steps
        steps_list = plan.steps if hasattr(plan, "steps") else plan
        for s in steps_list:
            if isinstance(s, dict):
                cap = s.get("capability", "")
                action = s.get("action", "")
            else:
                cap = getattr(s, "capability", "")
                action = getattr(s, "action", "")
            results.append({
                "action": action,
                "capability": cap,
                "success": True,
                "output": f"Executed: {action[:80]}",
                "duration_ms": 50,
            })
        return results

    def _evidence(self, results: List[Dict]) -> Dict[str, Any]:
        successes = [r for r in results if r.get("success")]
        failures = [r for r in results if not r.get("success")]
        return {
            "total": len(results),
            "succeeded": len(successes),
            "failed": len(failures),
            "success_rate": len(successes) / max(len(results), 1),
        }

    def _evaluate(self, evidence: Dict[str, Any], hypotheses: List) -> Dict[str, Any]:
        any_success = evidence["succeeded"] > 0
        winning = None
        if any_success and hypotheses:
            winning = hypotheses[0].id
        return {
            "any_succeeded": any_success,
            "winning_hypothesis": winning,
            "confidence": 0.8 if any_success else 0.2,
        }

    def _detect_gap(self, goal: str, evidence: Dict[str, Any],
                    capabilities: Dict[str, Any]) -> str:
        """Identify why we failed. Returns gap description."""
        if evidence["failed"] == 0:
            return ""
        # Heuristic gap detection
        n_skills = len(capabilities.get("skills", {}).get("active", []))
        n_mcps = len(capabilities.get("mcps", []))
        if n_skills == 0 and n_mcps == 0:
            return "no_capabilities_installed: instale uma skill ou MCP primeiro"
        if "dados" in goal.lower() or "csv" in goal.lower():
            return "no_data_loaded: faça upload de um dataset primeiro"
        if "imagem" in goal.lower() or "video" in goal.lower():
            return "no_media_capability: instale skill de media"
        return f"unrecognized_goal_pattern: '{goal[:60]}'"

    def _reflect(self, goal: str, results: List[Dict],
                evaluation: Dict[str, Any], gap: Optional[str],
                tenant: str, session: str) -> str:
        """Extract lesson and store in episodic memory."""
        outcome = "success" if evaluation.get("any_succeeded") else "failure"
        lesson = ""
        if outcome == "success":
            successes = [r for r in results if r.get("success")]
            caps_used = list(set(r.get("capability", "") for r in successes))
            lesson = f"Goal '{goal[:80]}' completed using {len(caps_used)} capabilities"
        else:
            lesson = f"Goal '{goal[:80]}' failed. Gap: {gap or 'unknown'}"
        # Store in episodic
        self.mem.remember_episode(
            actor=f"agent:{session}",
            context={"goal": goal},
            action="cognitive-loop",
            outcome=outcome,
            details={"results_count": len(results),
                    "winning_hypothesis": evaluation.get("winning_hypothesis"),
                    "gap": gap},
            lesson=lesson,
            tenant=tenant,
        )
        return lesson

    def _record_stage(self, trace: CognitiveTrace, stage: Stage, data: Any):
        trace.stages.append({
            "stage": stage.value,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


def asdict_safe(obj):
    """asdict that handles nested objects."""
    try:
        return asdict(obj)
    except Exception:
        return obj


# Patch Step/Plan to use safe asdict
asdict = asdict_safe


_LOOP: Optional[CognitiveLoop] = None


def get_loop() -> CognitiveLoop:
    global _LOOP
    if _LOOP is None:
        _LOOP = CognitiveLoop()
    return _LOOP
