"""Browser automation — persistent user sessions via Playwright."""
from empire.browser.session import BrowserSessionManager, BrowserSession
from empire.browser.actions import execute_action, list_action_types
__all__ = ["BrowserSessionManager", "BrowserSession", "execute_action", "list_action_types"]
