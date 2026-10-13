"""Test semantic memory (TF-IDF)."""
import pytest
from empire.memory.semantic import SemanticMemory, cosine_similarity


class TestSemanticMemory:
    
    def test_add_and_retrieve(self):
        mem = SemanticMemory()
        mem.add("doc-1", "Python is a programming language")
        mem.add("doc-2", "Java is also a programming language")
        mem.add("doc-3", "I like pizza")
        results = mem.search("What programming language?", top_k=2)
        assert len(results) == 2
        assert all(r["score"] > 0 for r in results)
        # First result should be programming-related
        assert "programming" in results[0]["text"].lower()
    
    def test_empty_memory(self):
        mem = SemanticMemory()
        results = mem.search("anything", top_k=5)
        assert results == []
    
    def test_relevance_ranking(self):
        mem = SemanticMemory()
        mem.add("a", "machine learning algorithms")
        mem.add("b", "deep learning neural networks")
        mem.add("c", "cooking recipes for pasta")
        results = mem.search("neural networks", top_k=3)
        # First result should be most relevant
        assert "neural" in results[0]["text"].lower() or "learning" in results[0]["text"].lower()
    
    def test_cosine_similarity(self):
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        assert abs(cosine_similarity(v1, v2) - 1.0) < 0.001
        
        v3 = [0.0, 1.0, 0.0]
        assert abs(cosine_similarity(v1, v3) - 0.0) < 0.001
        
        v4 = [-1.0, 0.0, 0.0]
        assert abs(cosine_similarity(v1, v4) - -1.0) < 0.001
