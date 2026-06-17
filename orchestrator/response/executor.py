"""Executes a ProposedAction against the MCP client, after the policy has cleared it.

This module never decides tiers — callers must consult Policy first. It maps logical
action names to ToolClient calls; unknown actions raise rather than guess.
"""

from __future__ import annotations

from ..alerts.models import ProposedAction
from ..client import ToolClient


class UnknownAction(Exception):
    pass


def execute(action: ProposedAction, client: ToolClient) -> dict:
    name = action.name
    p = action.params

    if name == "alert_only":
        return {"action": name, "ok": True, "output": "notification only; no change made"}
    if name == "unban_ip":
        return client.unban_ip(p["ip"], p["jail"])
    if name == "ban_ip":
        return client.ban_ip(p["ip"], p["jail"])
    if name == "restart_service":
        return client.restart_service(p["unit"])

    raise UnknownAction(f"executor has no handler for action {name!r}")
