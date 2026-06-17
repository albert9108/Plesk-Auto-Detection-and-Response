"""Shared test fixtures: a scriptable fake ToolClient."""

from __future__ import annotations

import pytest


class FakeClient:
    """In-memory ToolClient for hermetic end-to-end tests."""

    def __init__(self, **overrides):
        self.calls: list[tuple] = []
        self._banned: dict[str, list[str]] = overrides.get("banned", {})  # ip -> jails
        self._services: dict[str, str] = overrides.get("services", {})
        self._disk = overrides.get("disk", "Filesystem Size Used Avail Use% Mounted\n/dev/sda1 50G 10G 40G 20% /")
        self._domain_info = overrides.get("domain_info", "Domain: example.com\nStatus: active")
        self._logs: dict[str, str] = overrides.get("logs", {})

    def system_health(self):
        return {"load": "load 0.1", "disk": self._disk, "memory": "mem ok"}

    def service_status(self, unit):
        active = self._services.get(unit, "active")
        return {"unit": unit, "active": active, "ok": active == "active"}

    def fail2ban_status(self, jail=None):
        return "Jail list: plesk-apache, ssh"

    def find_ip_in_jails(self, ip, jails=None):
        return list(self._banned.get(ip, []))

    def plesk_domain_info(self, domain):
        return self._domain_info

    def read_log(self, path, lines=200, grep=None):
        return self._logs.get(path, "")

    def unban_ip(self, ip, jail):
        self.calls.append(("unban_ip", ip, jail))
        return {"action": "unban_ip", "ip": ip, "jail": jail, "ok": True, "output": "unbanned"}

    def ban_ip(self, ip, jail):
        self.calls.append(("ban_ip", ip, jail))
        return {"action": "ban_ip", "ip": ip, "jail": jail, "ok": True, "output": "banned"}

    def restart_service(self, unit):
        self.calls.append(("restart_service", unit))
        return {"action": "restart_service", "unit": unit, "ok": True, "output": "restarted"}


@pytest.fixture
def fake_client():
    return FakeClient
