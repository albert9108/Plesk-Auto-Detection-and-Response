"""Deterministic 'domain down' playbook — runs first, uses no AI.

It walks a bounded set of checks against the MCP read tools and stops at the first
that explains the outage, emitting a structured Diagnosis (+ proposed remediation).
If nothing explains it, `explained=False` and the gathered evidence is handed to the
AI fallback. The check order is cheapest/most-common first.
"""

from __future__ import annotations

from ..alerts.models import Alert, Diagnosis, ProposedAction
from ..client import ToolClient

# Service units checked for a web outage on a typical Plesk box.
WEB_UNITS = ["nginx", "apache2"]
PHP_FPM_HINT = "plesk-php-fpm"


def _evidence(d: Diagnosis, line: str) -> None:
    d.evidence.append(line)


def investigate(alert: Alert, client: ToolClient, *, probe_ips: list[str] | None = None) -> Diagnosis:
    d = Diagnosis(alert=alert, source="playbook")
    domain = alert.domain or alert.monitor
    probe_ips = probe_ips or []

    # 1. fail2ban banned our own UptimeRobot prober? (very common false-positive)
    for ip in probe_ips:
        jails = client.find_ip_in_jails(ip)
        if jails:
            _evidence(d, f"UptimeRobot prober {ip} is banned in fail2ban jails: {', '.join(jails)}")
            d.explained = True
            d.root_cause = (
                f"The uptime monitor's own IP ({ip}) was banned by fail2ban in "
                f"{jails[0]}, so probes fail even though the site is up."
            )
            d.proposed_action = ProposedAction(
                name="unban_ip",
                params={"ip": ip, "jail": jails[0]},
                reason="Unban the monitoring prober to restore reachability checks.",
            )
            return d
        _evidence(d, f"prober {ip} not banned")

    # 2. Web server down?
    for unit in WEB_UNITS:
        st = client.service_status(unit)
        _evidence(d, f"service {unit}: {st.get('active')}")
        if not st.get("ok") and st.get("active") not in (None, "active"):
            # Only treat as cause if the unit exists but is not active.
            if st.get("active") in ("inactive", "failed", "deactivating"):
                d.explained = True
                d.root_cause = f"Web server '{unit}' is {st.get('active')}, so all sites are down."
                d.proposed_action = ProposedAction(
                    name="restart_service",
                    params={"unit": unit},
                    reason=f"Restart the {unit} web server to restore service.",
                )
                return d

    # 3. Disk full? (a frequent cause of 500s / failed restarts)
    health = client.system_health()
    _evidence(d, f"disk:\n{health.get('disk', '')}")
    if _disk_is_full(health.get("disk", "")):
        d.explained = True
        d.root_cause = "A filesystem is at/near 100% usage, which breaks request handling."
        # Freeing disk is environment-specific → route to humans (APPROVAL tier).
        d.proposed_action = ProposedAction(
            name="alert_only",
            params={},
            reason="Disk full needs human judgement on what to clear.",
        )
        return d

    # 4. Domain suspended / expired in Plesk?
    if domain:
        info = client.plesk_domain_info(domain)
        _evidence(d, f"plesk domain info for {domain}:\n{info[:1000]}")
        low = info.lower()
        if "suspend" in low or "disabled" in low:
            d.explained = True
            d.root_cause = f"Plesk reports domain '{domain}' as suspended/disabled."
            d.proposed_action = ProposedAction(
                name="alert_only",
                params={},
                reason="Un-suspending a domain is an APPROVAL-tier business decision.",
            )
            return d

    # 5. Recent errors in the domain's web log (collect as evidence for the fallback)
    if domain:
        log = f"/var/www/vhosts/system/{domain}/logs/error_log"
        tail = client.read_log(log, lines=40)
        if tail:
            _evidence(d, f"recent {log}:\n{tail}")

    # Nothing conclusive → hand evidence to the AI fallback.
    d.explained = False
    d.root_cause = ""
    return d


def _disk_is_full(df_output: str, threshold: int = 97) -> bool:
    for line in df_output.splitlines()[1:]:
        for token in line.split():
            if token.endswith("%"):
                try:
                    if int(token[:-1]) >= threshold:
                        return True
                except ValueError:
                    pass
    return False
