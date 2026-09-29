"""
Skill Registry — install, validate, load, and unload skills.

A "skill" is a directory containing:
  - skill.yaml    manifest (name, version, capabilities, requirements)
  - tools/        Python modules with run(inputs) function
  - prompts/      System prompt additions
  - templates/    Template files (email, copy, etc)
  - tests/        Optional pytest tests
  - README.md     Documentation

Skills can be installed from:
  - Local path (./my-skill/)
  - ZIP file upload
  - Git URL (git+https://...)
  - Built-in directory (.skills/<name>/)

All skills run in the sandbox before being marked active.
"""
import os
import re
import json
import shutil
import tempfile
import zipfile
import hashlib
import subprocess
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import yaml

from empire.registry.sandbox import (
    validate_ast, run_in_sandbox, SandboxResult,
    sha256_file, sha256_str, PROFILES,
)


# Paths
SKILLS_DIR = Path(os.getenv("EMPIRE_SKILLS_DIR", "/workspace/ai-empire/.skills"))
INSTALLED_FILE = Path(os.getenv("EMPIRE_REGISTRY_FILE", "/workspace/ai-empire/empire_registry.yaml"))


@dataclass
class SkillManifest:
    """Parsed skill.yaml manifest."""
    name: str
    version: str
    description: str = ""
    author: str = ""
    license: str = "MIT"
    scm: str = ""
    signature: str = ""
    capabilities: Dict[str, List[str]] = field(default_factory=dict)
    required_mcps: List[str] = field(default_factory=list)
    optional_mcps: List[str] = field(default_factory=list)
    required_data: List[str] = field(default_factory=list)
    sandbox_profile: str = "medium"
    network_policy_allow: List[str] = field(default_factory=list)
    network_policy_deny: List[str] = field(default_factory=list)
    self_test: List[Dict[str, Any]] = field(default_factory=list)
    source: str = ""
    installed_at: str = ""
    hash: str = ""

    @classmethod
    def from_yaml(cls, path: Path) -> "SkillManifest":
        data = yaml.safe_load(path.read_text())
        if not isinstance(data, dict):
            raise ValueError(f"invalid skill.yaml at {path}")
        name = data.get("name")
        version = data.get("version")
        if not name or not version:
            raise ValueError(f"skill.yaml must have name and version: {path}")
        return cls(
            name=name, version=version,
            description=data.get("description", ""),
            author=data.get("author", ""),
            license=data.get("license", "MIT"),
            scm=data.get("scm", ""),
            signature=data.get("signature", ""),
            capabilities=data.get("capabilities", {}),
            required_mcps=data.get("required_mcps", []),
            optional_mcps=data.get("optional_mcps", []),
            required_data=data.get("required_data", []),
            sandbox_profile=data.get("sandbox_profile", "medium"),
            network_policy_allow=data.get("network_policy", {}).get("allow", []),
            network_policy_deny=data.get("network_policy", {}).get("deny", []),
            self_test=data.get("self_test", []),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InstalledSkill:
    """A skill registered and active in the system."""
    manifest: SkillManifest
    path: Path
    enabled: bool = True
    last_self_test: Optional[str] = None
    last_self_test_ok: bool = False
    tools: List[str] = field(default_factory=list)
    prompts: List[str] = field(default_factory=list)
    templates: List[str] = field(default_factory=list)


# ─── Registry state ─────────────────────────────────────────────────────────

class SkillRegistry:
    """Manages installation, removal, and discovery of skills."""

    def __init__(self, skills_dir: Path = None, registry_file: Path = None):
        self.skills_dir = skills_dir or SKILLS_DIR
        self.registry_file = registry_file or INSTALLED_FILE
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.installed: Dict[str, InstalledSkill] = {}
        self._load_state()

    # ── persistence ──
    def _load_state(self):
        """Load installed skills from registry file."""
        if not self.registry_file.exists():
            self._scan_builtins()
            self._save_state()
            return
        try:
            data = yaml.safe_load(self.registry_file.read_text()) or {}
        except Exception:
            data = {}
        for name, entry in (data.get("skills") or {}).items():
            path = Path(entry["path"])
            if not path.exists():
                continue
            try:
                manifest = SkillManifest.from_yaml(path / "skill.yaml")
                manifest.source = entry.get("source", "")
                manifest.installed_at = entry.get("installed_at", "")
                manifest.hash = entry.get("hash", "")
                self.installed[name] = InstalledSkill(
                    manifest=manifest, path=path,
                    enabled=entry.get("enabled", True),
                    last_self_test=entry.get("last_self_test"),
                    last_self_test_ok=entry.get("last_self_test_ok", False),
                    tools=entry.get("tools", []),
                    prompts=entry.get("prompts", []),
                    templates=entry.get("templates", []),
                )
            except Exception as e:
                print(f"[registry] failed to load {name}: {e}")

    def _save_state(self):
        """Persist registry to disk."""
        data = {"version": 1, "skills": {}}
        for name, skill in self.installed.items():
            data["skills"][name] = {
                "path": str(skill.path),
                "enabled": skill.enabled,
                "last_self_test": skill.last_self_test,
                "last_self_test_ok": skill.last_self_test_ok,
                "tools": skill.tools,
                "prompts": skill.prompts,
                "templates": skill.templates,
                "source": skill.manifest.source,
                "installed_at": skill.manifest.installed_at,
                "hash": skill.manifest.hash,
            }
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        self.registry_file.write_text(yaml.safe_dump(data, allow_unicode=True))

    def _scan_builtins(self):
        """Scan .skills/ directory for built-in skills."""
        if not self.skills_dir.exists():
            return
        for entry in self.skills_dir.iterdir():
            if entry.is_dir() and (entry / "skill.yaml").exists():
                try:
                    self.installed[entry.name] = self._build_installed(
                        entry, source=f"builtin:{entry.name}"
                    )
                except Exception as e:
                    print(f"[registry] failed to load builtin {entry.name}: {e}")

    def _build_installed(self, path: Path, source: str) -> InstalledSkill:
        manifest = SkillManifest.from_yaml(path / "skill.yaml")
        manifest.source = source
        manifest.installed_at = manifest.installed_at or datetime.now(timezone.utc).isoformat()
        manifest.hash = sha256_file(path / "skill.yaml")
        # Discover files (filter out sandbox artifacts like _runner.py and tool.py)
        sandbox_artifacts = {"_runner.py", "tool.py", "__pycache__"}
        tools = sorted(
            p.name for p in (path / "tools").glob("*.py")
            if (path / "tools").is_dir() and p.name not in sandbox_artifacts
        )
        prompts = sorted(p.name for p in (path / "prompts").glob("*.md") if (path / "prompts").is_dir()) if (path / "prompts").is_dir() else []
        templates = sorted(p.name for p in (path / "templates").glob("*") if (path / "templates").is_dir()) if (path / "templates").is_dir() else []
        return InstalledSkill(
            manifest=manifest, path=path,
            tools=tools, prompts=prompts, templates=templates,
        )

    # ── public API ──
    def list(self) -> List[InstalledSkill]:
        return list(self.installed.values())

    def get(self, name: str) -> Optional[InstalledSkill]:
        return self.installed.get(name)

    def discover_available(self) -> List[Dict[str, str]]:
        """List built-in skills available to install (in .skills/)."""
        available = []
        if not self.skills_dir.exists():
            return available
        for entry in self.skills_dir.iterdir():
            if entry.is_dir() and (entry / "skill.yaml").exists():
                if entry.name not in self.installed:
                    try:
                        m = SkillManifest.from_yaml(entry / "skill.yaml")
                        available.append({"name": m.name, "version": m.version,
                                          "description": m.description,
                                          "path": str(entry)})
                    except Exception:
                        pass
        return available

    def install_from_path(self, src: Path, source: str = "local") -> InstalledSkill:
        """Install a skill from a local directory."""
        if not (src / "skill.yaml").exists():
            raise ValueError(f"no skill.yaml found in {src}")
        manifest = SkillManifest.from_yaml(src / "skill.yaml")
        dest = self.skills_dir / manifest.name
        # If src and dest are the same, skip copy
        if src.resolve() != dest.resolve():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
        else:
            dest = src
        skill = self._build_installed(dest, source=source)
        # Run self-test
        ok, msg = self.run_self_test(skill)
        skill.last_self_test = datetime.now(timezone.utc).isoformat()
        skill.last_self_test_ok = ok
        if not ok and skill.manifest.self_test:
            # Self-test failed — abort install (only if dest != src to avoid deleting source)
            if dest.resolve() != src.resolve():
                shutil.rmtree(dest, ignore_errors=True)
            raise ValueError(f"self-test failed: {msg}")
        self.installed[manifest.name] = skill
        self._save_state()
        return skill

    def install_from_zip(self, zip_data: bytes, source: str = "upload") -> InstalledSkill:
        """Install a skill from a ZIP archive."""
        tmpdir = Path(tempfile.mkdtemp(prefix="skill_zip_"))
        try:
            with zipfile.ZipFile(__import__("io").BytesIO(zip_data)) as zf:
                zf.extractall(tmpdir)
            # Find the skill.yaml (might be at root or in a subdirectory)
            candidates = list(tmpdir.rglob("skill.yaml"))
            if not candidates:
                raise ValueError("zip does not contain skill.yaml")
            skill_root = candidates[0].parent
            return self.install_from_path(skill_root, source=source)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def install_from_git(self, url: str, ref: str = "main", source: str = None) -> InstalledSkill:
        """Install a skill from a git URL."""
        if source is None:
            source = url
        tmpdir = Path(tempfile.mkdtemp(prefix="skill_git_"))
        try:
            # Try shallow clone first (fast)
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "-b", ref, url, str(tmpdir / "repo")],
                capture_output=True, timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(f"git clone failed: {result.stderr.decode()}")
            candidates = list((tmpdir / "repo").rglob("skill.yaml"))
            if not candidates:
                raise ValueError("repo does not contain skill.yaml")
            skill_root = candidates[0].parent
            return self.install_from_path(skill_root, source=source)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def uninstall(self, name: str):
        """Remove a skill."""
        skill = self.installed.get(name)
        if not skill:
            raise KeyError(name)
        if skill.manifest.source.startswith("builtin:"):
            raise ValueError(f"cannot uninstall builtin skill {name}")
        if skill.path.exists() and skill.path.is_relative_to(self.skills_dir):
            shutil.rmtree(skill.path, ignore_errors=True)
        del self.installed[name]
        self._save_state()

    def toggle(self, name: str, enabled: bool) -> InstalledSkill:
        skill = self.installed.get(name)
        if not skill:
            raise KeyError(name)
        skill.enabled = enabled
        self._save_state()
        return skill

    def run_self_test(self, skill: InstalledSkill) -> tuple[bool, str]:
        """Run the manifest's self_test cases in the sandbox."""
        if not skill.manifest.self_test:
            return True, "no self_test defined"
        from empire.registry.sandbox import PROFILES
        profile = PROFILES.get(skill.manifest.sandbox_profile, PROFILES["medium"])
        # Apply skill's network policy
        profile.network_allow = list(profile.network_allow) + list(skill.manifest.network_policy_allow)
        profile.network_deny = list(profile.network_deny) + list(skill.manifest.network_policy_deny)

        for case in skill.manifest.self_test:
            tool_name = case.get("tool")
            if not tool_name:
                continue
            tool_path = skill.path / "tools" / f"{tool_name}.py"
            if not tool_path.exists():
                return False, f"self_test references missing tool: {tool_name}"
            code = tool_path.read_text()
            inputs = case.get("input", {})
            # Use a temporary workdir so we don't pollute the skill directory
            result = run_in_sandbox(code, inputs=inputs, profile=profile,
                                    workdir=None)  # sandbox creates tmpdir
            if not result.success:
                return False, f"tool {tool_name} failed: {result.stderr[:300]}"
        return True, "all self_tests passed"

    def get_capability_summary(self) -> Dict[str, Any]:
        """Return a summary of all capabilities for system prompt injection."""
        tools = []
        prompts = []
        templates = []
        missing_mcps = set()
        for skill in self.installed.values():
            if not skill.enabled:
                continue
            for tool in skill.tools:
                tools.append({"name": tool, "skill": skill.manifest.name})
            for prompt in skill.prompts:
                prompts.append({"name": prompt, "skill": skill.manifest.name})
            for tmpl in skill.templates:
                templates.append({"name": tmpl, "skill": skill.manifest.name})
            missing_mcps.update(skill.manifest.required_mcps)
        return {
            "tools": tools,
            "prompts": prompts,
            "templates": templates,
            "skills_active": [s.manifest.name for s in self.installed.values() if s.enabled],
        }

    def get_tool_code(self, tool_name: str) -> Optional[tuple[str, str, InstalledSkill]]:
        """Find a tool's code by name. Returns (code, skill_name, skill_obj)."""
        for skill in self.installed.values():
            if not skill.enabled:
                continue
            for tool in skill.tools:
                if tool == tool_name or tool == f"{tool_name}.py":
                    path = skill.path / "tools" / tool
                    if path.exists():
                        return path.read_text(), skill.manifest.name, skill
        return None

    def reload(self, name: str) -> InstalledSkill:
        """Hot-reload a skill from disk."""
        skill = self.installed.get(name)
        if not skill:
            raise KeyError(name)
        return self.install_from_path(skill.path, source=skill.manifest.source)


# ─── Singleton ──────────────────────────────────────────────────────────────

_REGISTRY: Optional[SkillRegistry] = None


def get_registry() -> SkillRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = SkillRegistry()
    return _REGISTRY
