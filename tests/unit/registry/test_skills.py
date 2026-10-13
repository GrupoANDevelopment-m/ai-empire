"""Test skill registry."""
import pytest
from pathlib import Path
from empire.registry.skills import SkillRegistry


class TestSkillRegistry:
    
    def test_register_skill(self, skill_manifest):
        registry = SkillRegistry()
        registry.register(skill_manifest)
        assert "test-skill" in registry.list()
    
    def test_get_skill(self, skill_manifest):
        registry = SkillRegistry()
        registry.register(skill_manifest)
        skill = registry.get("test-skill")
        assert skill["name"] == "test-skill"
        assert skill["version"] == "1.0.0"
    
    def test_get_unknown_skill(self):
        registry = SkillRegistry()
        with pytest.raises(KeyError):
            registry.get("nonexistent")
    
    def test_list_skills(self, skill_manifest):
        registry = SkillRegistry()
        registry.register(skill_manifest)
        registry.register({**skill_manifest, "name": "other-skill"})
        skills = registry.list()
        assert "test-skill" in skills
        assert "other-skill" in skills
    
    def test_run_tool_safely(self, skill_manifest, temp_dir):
        registry = SkillRegistry()
        registry.register(skill_manifest)
        result = registry.run_tool("test-skill", "test_tool", {"x": 5})
        # Test tool just verifies, returns success
        assert result is not None
