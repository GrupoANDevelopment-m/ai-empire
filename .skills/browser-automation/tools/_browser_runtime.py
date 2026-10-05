import sys
from pathlib import Path
_WORKSPACE = Path(__file__).resolve().parent.parent.parent.parent
if str(_WORKSPACE) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE))
def get_manager():
    from empire.browser.session import get_manager
    return get_manager()
def run_action_sync(session_id, action, params=None, tenant=None):
    from empire.browser.actions import run_action_sync
    return run_action_sync(session_id, action, params, tenant)
