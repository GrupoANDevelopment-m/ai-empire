"""Test browser session manager."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from empire.browser.session import BrowserSessionManager, BrowserSession


class TestBrowserSessionManager:
    
    def test_init(self, temp_dir):
        mgr = BrowserSessionManager(profile_dir=temp_dir)
        assert mgr.profile_dir == temp_dir
    
    def test_create_session(self, temp_dir):
        mgr = BrowserSessionManager(profile_dir=temp_dir)
        session = mgr.create_session(tenant_id="t1", profile="default")
        assert session.tenant_id == "t1"
        assert session.profile == "default"
    
    def test_list_sessions(self, temp_dir):
        mgr = BrowserSessionManager(profile_dir=temp_dir)
        s1 = mgr.create_session(tenant_id="t1", profile="default")
        s2 = mgr.create_session(tenant_id="t1", profile="alt")
        sessions = mgr.list_sessions()
        assert len(sessions) == 2
    
    def test_get_session(self, temp_dir):
        mgr = BrowserSessionManager(profile_dir=temp_dir)
        s1 = mgr.create_session(tenant_id="t1", profile="default")
        found = mgr.get_session(s1.id)
        assert found.id == s1.id
    
    def test_close_session(self, temp_dir):
        mgr = BrowserSessionManager(profile_dir=temp_dir)
        s1 = mgr.create_session(tenant_id="t1", profile="default")
        mgr.close_session(s1.id)
        with pytest.raises(KeyError):
            mgr.get_session(s1.id)
    
    def test_tenant_isolation(self, temp_dir):
        """Sessions should be isolated per tenant."""
        mgr = BrowserSessionManager(profile_dir=temp_dir)
        s1 = mgr.create_session(tenant_id="tenant-a", profile="default")
        s2 = mgr.create_session(tenant_id="tenant-b", profile="default")
        assert s1.profile_path != s2.profile_path
        assert "tenant-a" in str(s1.profile_path)
        assert "tenant-b" in str(s2.profile_path)
