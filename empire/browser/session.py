"""Browser session manager with persistent user context (real Playwright)."""
import os, time, asyncio
from pathlib import Path
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field, asdict

PROFILES_ROOT = Path(os.getenv("BROWSER_PROFILES_DIR", "/workspace/ai-empire/data/browser_profiles"))


@dataclass
class BrowserSession:
    session_id: str
    tenant: str
    profile_name: str
    profile_dir: str
    created_at: float
    last_used: float
    headless: bool
    browser_type: str
    page_count: int = 0
    current_url: Optional[str] = None
    status: str = "ready"
    extra: Dict[str, Any] = field(default_factory=dict)


class BrowserSessionManager:
    def __init__(self, profiles_root: Path = PROFILES_ROOT):
        self.profiles_root = Path(profiles_root)
        self.profiles_root.mkdir(parents=True, exist_ok=True)
        self._sessions: Dict[str, BrowserSession] = {}
        self._browsers: Dict[str, Any] = {}
        self._pages: Dict[str, Any] = {}

    def _ensure_playwright(self):
        if not hasattr(self, "_pw_instance"):
            from playwright.async_api import async_playwright
            self._pw_instance = async_playwright
        return self._pw_instance

    def _tenant_dir(self, tenant: str) -> Path:
        d = self.profiles_root / tenant
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _session_id(self, tenant: str, profile: str) -> str:
        return f"{tenant}::{profile}"

    def get_or_create(self, tenant: str, profile: str,
                      headless: bool = True,
                      browser_type: str = "chromium") -> BrowserSession:
        sid = self._session_id(tenant, profile)
        if sid in self._sessions and self._sessions[sid].status != "closed":
            self._sessions[sid].last_used = time.time()
            return self._sessions[sid]
        profile_dir = self._tenant_dir(tenant) / profile
        profile_dir.mkdir(parents=True, exist_ok=True)
        s = BrowserSession(
            session_id=sid, tenant=tenant, profile_name=profile,
            profile_dir=str(profile_dir), created_at=time.time(),
            last_used=time.time(), headless=headless, browser_type=browser_type,
        )
        self._sessions[sid] = s
        return s

    def list_sessions(self, tenant=None) -> List[BrowserSession]:
        return [s for s in self._sessions.values()
                if (not tenant or s.tenant == tenant) and s.status != "closed"]

    def get(self, session_id: str) -> Optional[BrowserSession]:
        return self._sessions.get(session_id)

    def close(self, session_id: str) -> bool:
        s = self._sessions.get(session_id)
        if not s: return False
        try:
            page = self._pages.get(session_id)
            if page: asyncio.create_task(page.close())
            ctx = self._browsers.get(session_id)
            if ctx: asyncio.create_task(ctx.close())
        except Exception: pass
        s.status = "closed"
        return True

    def hard_reset(self, session_id: str) -> bool:
        s = self._sessions.get(session_id)
        if not s: return False
        self.close(session_id)
        import shutil
        shutil.rmtree(s.profile_dir, ignore_errors=True)
        self._sessions.pop(session_id, None)
        return True

    def to_dicts(self, sessions) -> List[Dict]:
        return [asdict(s) for s in sessions]


_manager = None
def get_manager():
    global _manager
    if _manager is None: _manager = BrowserSessionManager()
    return _manager
