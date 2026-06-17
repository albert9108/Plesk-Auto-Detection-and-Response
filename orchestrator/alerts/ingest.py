"""Parse incoming webhook payloads into the normalized Alert model.

UptimeRobot's alert webhook is configurable; operators typically POST a JSON body
built from its template variables. We accept the common field names and degrade
gracefully so a slightly different template still parses.

UptimeRobot `alertType`: 1 = down, 2 = up.
"""

from __future__ import annotations

from urllib.parse import urlparse

from .models import Alert, AlertKind


def _domain_from_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"http://{url}")
    return parsed.netloc or parsed.path


def parse_uptimerobot(payload: dict) -> Alert:
    alert_type = str(payload.get("alertType", payload.get("alert_type", "1")))
    kind = AlertKind.UP if alert_type == "2" else AlertKind.DOWN

    url = str(payload.get("monitorURL") or payload.get("monitor_url") or payload.get("url") or "")
    monitor = str(payload.get("monitorFriendlyName") or payload.get("monitor") or "")
    domain = str(payload.get("domain") or "") or _domain_from_url(url)
    detail = str(payload.get("alertDetails") or payload.get("details") or "")

    return Alert(
        source="uptimerobot",
        monitor=monitor,
        domain=domain,
        url=url,
        kind=kind,
        detail=detail,
    )
