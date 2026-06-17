"""High-level operations exposed by the MCP server.

Each method returns plain JSON-serialisable data so it can be surfaced both as an
MCP tool (server.py) and consumed in-process by the orchestrator's LocalClient.
The class holds no state beyond its CommandRunner, so it is trivial to test with a
fake runner.
"""

from __future__ import annotations

from .exec.runner import CommandRunner

# fail2ban jails that fail2ban-client exposes on a typical Plesk box.
DEFAULT_PLESK_JAILS = ["plesk-apache", "plesk-apache-badbot", "plesk-modsecurity", "ssh"]
# UptimeRobot publishes its prober IP ranges; operators paste the resolved IPs here
# (or sync them via a cron). Used to detect the "we banned our own monitor" case.
UPTIMEROBOT_PROBE_IPS: list[str] = []


class ServerTools:
    def __init__(self, runner: CommandRunner | None = None):
        self.runner = runner or CommandRunner()

    # ---- read-only diagnostics -------------------------------------------------
    def system_health(self) -> dict:
        return {
            "load": self.runner.run("load_average").stdout.strip(),
            "disk": self.runner.run("disk_usage").stdout.strip(),
            "memory": self.runner.run("memory_usage").stdout.strip(),
        }

    def top_processes(self, limit: int = 10) -> str:
        lines = self.runner.run("top_processes").stdout.splitlines()
        return "\n".join(lines[: limit + 1])

    def service_status(self, unit: str) -> dict:
        res = self.runner.run("service_status", unit=unit)
        return {"unit": unit, "active": res.stdout.strip(), "ok": res.stdout.strip() == "active"}

    def fail2ban_status(self, jail: str | None = None) -> str:
        if jail:
            return self.runner.run("fail2ban_jail_status", jail=jail).stdout
        return self.runner.run("fail2ban_status").stdout

    def find_ip_in_jails(self, ip: str, jails: list[str] | None = None) -> list[str]:
        """Return the jails that currently have `ip` banned."""
        banned_in = []
        for jail in jails or DEFAULT_PLESK_JAILS:
            res = self.runner.run("fail2ban_jail_status", jail=jail)
            if res.ok and ip in res.stdout:
                banned_in.append(jail)
        return banned_in

    def plesk_domain_info(self, domain: str) -> str:
        return self.runner.run("plesk_domain_info", domain=domain).stdout

    def read_log(self, path: str, lines: int = 200, grep: str | None = None) -> str:
        return self.runner.read_log(path, lines=lines, grep=grep)

    # ---- actions (governed by the orchestrator's policy engine) ----------------
    def unban_ip(self, ip: str, jail: str) -> dict:
        res = self.runner.run("fail2ban_unban", ip=ip, jail=jail)
        return {"action": "unban_ip", "ip": ip, "jail": jail, "ok": res.ok, "output": res.stdout or res.stderr}

    def ban_ip(self, ip: str, jail: str) -> dict:
        res = self.runner.run("fail2ban_ban", ip=ip, jail=jail)
        return {"action": "ban_ip", "ip": ip, "jail": jail, "ok": res.ok, "output": res.stdout or res.stderr}

    def restart_service(self, unit: str) -> dict:
        res = self.runner.run("service_restart", unit=unit)
        return {"action": "restart_service", "unit": unit, "ok": res.ok, "output": res.stdout or res.stderr}
