"""
Convenience facade — the real LLM agent.
Import path: `from empire.agent.llm_agent import agent`
"""
from .llm import EmpireAgent

# Default singleton (recreated per process)
agent = EmpireAgent()
