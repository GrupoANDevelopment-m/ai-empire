"""
Failover — multi-server health monitoring + auto-promote.
For when a server goes down, automatically shift traffic to backup.
"""
from .health_monitor import HealthMonitor, HealthCheck, HealthStatus
from .server_pool import ServerPool, Server, ServerRole, ServerState

__all__ = [
    "HealthMonitor", "HealthCheck", "HealthStatus",
    "ServerPool", "Server", "ServerRole", "ServerState",
]
