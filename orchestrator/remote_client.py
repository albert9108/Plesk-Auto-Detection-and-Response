"""HTTPToolClient — reaches an on-box server over its authenticated URL.

Implements the same `ToolClient` interface as `LocalToolClient`, so the playbook,
executor and agent are unaware whether they're talking to an in-process box or a
remote one. Every call POSTs to `{base_url}/tool/{name}` with a bearer token; the box
still enforces the allowlist + sudoers locally.

The transport (`_post`) is overridable so tests can run without a real HTTP server.
"""

from __future__ import annotations

import httpx


class RemoteToolError(RuntimeError):
    pass


class HTTPToolClient:
    def __init__(self, base_url: str, token: str, *, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _post(self, name: str, params: dict) -> dict | list | str:
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.base_url}/tool/{name}"
        resp = httpx.post(url, json=params, headers=headers, timeout=self.timeout)
        if resp.status_code != 200:
            raise RemoteToolError(f"{name} -> HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()["result"]

    # ---- ToolClient interface (params mirror mcp_server.tools.ServerTools) ----
    def system_health(self) -> dict:
        return self._post("system_health", {})

    def service_status(self, unit: str) -> dict:
        return self._post("service_status", {"unit": unit})

    def fail2ban_status(self, jail: str | None = None) -> str:
        return self._post("fail2ban_status", {"jail": jail})

    def find_ip_in_jails(self, ip: str, jails: list[str] | None = None) -> list[str]:
        return self._post("find_ip_in_jails", {"ip": ip, "jails": jails})

    def plesk_domain_info(self, domain: str) -> str:
        return self._post("plesk_domain_info", {"domain": domain})

    def read_log(self, path: str, lines: int = 200, grep: str | None = None) -> str:
        return self._post("read_log", {"path": path, "lines": lines, "grep": grep})

    def unban_ip(self, ip: str, jail: str) -> dict:
        return self._post("unban_ip", {"ip": ip, "jail": jail})

    def ban_ip(self, ip: str, jail: str) -> dict:
        return self._post("ban_ip", {"ip": ip, "jail": jail})

    def restart_service(self, unit: str) -> dict:
        return self._post("restart_service", {"unit": unit})
