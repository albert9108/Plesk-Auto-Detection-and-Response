"""How the orchestrator reaches the on-box MCP execution layer.

`ToolClient` is the narrow interface the playbook, executor and agent depend on.
Two implementations are intended:

  * LocalToolClient — calls the MCP ServerTools in-process. Used in the
    "everything on the box" topology and throughout the test-suite (inject a
    fake CommandRunner and you have a hermetic end-to-end harness).
  * A remote MCP client over authenticated HTTPS for the split topology. It
    implements the same methods; swapping it in requires no playbook changes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ToolClient(Protocol):
    def system_health(self) -> dict: ...
    def service_status(self, unit: str) -> dict: ...
    def fail2ban_status(self, jail: str | None = None) -> str: ...
    def find_ip_in_jails(self, ip: str, jails: list[str] | None = None) -> list[str]: ...
    def plesk_domain_info(self, domain: str) -> str: ...
    def read_log(self, path: str, lines: int = 200, grep: str | None = None) -> str: ...
    def unban_ip(self, ip: str, jail: str) -> dict: ...
    def ban_ip(self, ip: str, jail: str) -> dict: ...
    def restart_service(self, unit: str) -> dict: ...


class LocalToolClient:
    """Adapts the in-process MCP ServerTools to the ToolClient interface."""

    def __init__(self, tools=None):
        if tools is None:
            from mcp_server.tools import ServerTools

            tools = ServerTools()
        self._t = tools

    def __getattr__(self, name):
        # Delegate every ToolClient method straight to ServerTools.
        return getattr(self._t, name)
