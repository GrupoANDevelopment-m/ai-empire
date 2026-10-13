"""Test cognitive loop (ACAMR)."""
import pytest
from empire.cognitive.loop import CognitiveLoop, ACAMRState


class TestCognitiveLoop:
    
    def test_initial_state(self):
        loop = CognitiveLoop()
        assert loop.state == ACAMRState.INITIAL
    
    def test_state_transition(self):
        loop = CognitiveLoop()
        loop.transition(ACAMRState.ANALYZE)
        assert loop.state == ACAMRState.ANALYZE
    
    def test_full_cycle(self):
        loop = CognitiveLoop()
        for state in [ACAMRState.ANALYZE, ACAMRState.CONNECT, ACAMRState.ACT, ACAMRState.MONITOR, ACAMRState.REFLECT]:
            loop.transition(state)
        assert loop.state == ACAMRState.REFLECT
    
    def test_invalid_transition(self):
        loop = CognitiveLoop()
        # Can transition from INITIAL to ANALYZE only
        with pytest.raises(ValueError):
            loop.transition(ACAMRState.ACT)  # skipping ANALYZE
    
    def test_max_iterations(self):
        loop = CognitiveLoop()
        for _ in range(loop.MAX_ITERATIONS):
            loop.transition(ACAMRState.ANALYZE)
        # Should not infinitely loop
        with pytest.raises(RuntimeError):
            loop.transition(ACAMRState.ANALYZE)
    
    def test_fast_fail_empty_goal(self):
        """Should fast-fail on empty goal."""
        loop = CognitiveLoop()
        with pytest.raises(ValueError):
            loop.run(goal="")
    
    def test_fast_fail_empty_recall(self):
        """Should fast-fail when recall is empty and goal is not in cache."""
        loop = CognitiveLoop()
        with pytest.raises(ValueError):
            loop.run(goal="test", recall=[])
