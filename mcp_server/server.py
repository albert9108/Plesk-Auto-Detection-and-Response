"""MCP server entrypoint (runs ON the Plesk box).

Transport-agnostic by design:
  * stdio  — when co-located with the orchestrator ("everything on the box").
  * http   — when the brain runs off-box (authenticated + IP-allowlisted).

The `mcp` package is an optional dependency (install with `.[mcp]`); the tool
logic in tools.py works without it, which is what the test-suite exercises.
"""

from __future__ import annotations

import os

from .exec.runner import Allowlist, CommandRunner
from .tools import ServerTools


def build_tools() -> ServerTools:
    use_sudo = os.environ.get("ADR_USE_SUDO", "1") != "0"
    runner = CommandRunner(Allowlist.load(), use_sudo=use_sudo)
    return ServerTools(runner)


def build_server(tools: ServerTools | None = None):
    from mcp.server.fastmcp import FastMCP  # imported lazily; optional dependency

    tools = tools or build_tools()
    mcp = FastMCP("plesk-adr")

    @mcp.tool()
    def system_health() -> dict:
        """Return load average, disk usage and memory usage for the server."""
        return tools.system_health()

    @mcp.tool()
    def service_status(unit: str) -> dict:
        """Check whether a systemd unit (e.g. nginx, apache2, php-fpm) is active."""
        return tools.service_status(unit)

    @mcp.tool()
    def fail2ban_status(jail: str | None = None) -> str:
        """Show fail2ban status overall, or for a specific jail if given."""
        return tools.fail2ban_status(jail)

    @mcp.tool()
    def find_ip_in_jails(ip: str) -> list[str]:
        """Return the fail2ban jails that currently have the given IP banned."""
        return tools.find_ip_in_jails(ip)

    @mcp.tool()
    def plesk_domain_info(domain: str) -> str:
        """Return Plesk's info for a domain (status, hosting, suspension, expiry)."""
        return tools.plesk_domain_info(domain)

    @mcp.tool()
    def read_log(path: str, lines: int = 200, grep: str | None = None) -> str:
        """Tail an allowlisted log file, optionally filtering lines containing `grep`."""
        return tools.read_log(path, lines=lines, grep=grep)

    # --- governed actions (the orchestrator enforces tiers before calling) ---
    @mcp.tool()
    def unban_ip(ip: str, jail: str) -> dict:
        """Unban an IP from a fail2ban jail."""
        return tools.unban_ip(ip, jail)

    @mcp.tool()
    def ban_ip(ip: str, jail: str) -> dict:
        """Ban an IP in a fail2ban jail."""
        return tools.ban_ip(ip, jail)

    @mcp.tool()
    def restart_service(unit: str) -> dict:
        """Restart a systemd unit."""
        return tools.restart_service(unit)

    return mcp


def main() -> None:
    transport = os.environ.get("ADR_MCP_TRANSPORT", "stdio")
    if transport == "http":
        # Authenticated HTTP facade for an off-box orchestrator (see http_app.py).
        import uvicorn

        from .http_app import create_http_app

        host = os.environ.get("ADR_MCP_HTTP_HOST", "0.0.0.0")
        port = int(os.environ.get("ADR_MCP_HTTP_PORT", "8765"))
        uvicorn.run(create_http_app(build_tools()), host=host, port=port)
        return
    # stdio (or any FastMCP-native transport) → real MCP protocol for Claude/Inspector.
    server = build_server()
    server.run(transport=transport)


if __name__ == "__main__":
    main()
