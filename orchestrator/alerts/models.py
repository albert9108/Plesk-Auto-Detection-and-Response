"""Normalized domain model shared across the orchestrator."""

from __future__ import annotations

import time
from enum import Enum

from pydantic import BaseModel, Field


class AlertKind(str, Enum):
    DOWN = "down"
    UP = "up"


class Alert(BaseModel):
    """A monitoring alert normalized from any provider (currently UptimeRobot)."""

    source: str = "uptimerobot"
    monitor: str = ""
    domain: str = ""
    url: str = ""
    kind: AlertKind = AlertKind.DOWN
    detail: str = ""
    ts: float = Field(default_factory=time.time)


class Tier(str, Enum):
    AUTO = "auto"          # act immediately, then notify
    APPROVAL = "approval"  # post approve/deny to chat, act only on approval
    FORBIDDEN = "forbidden"  # never; hard-blocked


class ProposedAction(BaseModel):
    """A remediation the playbook/agent wants to take, before policy is applied."""

    name: str                      # logical action, e.g. "unban_ip"
    params: dict[str, str] = {}
    reason: str = ""


class Diagnosis(BaseModel):
    """Result of investigating an alert."""

    alert: Alert
    explained: bool = False
    root_cause: str = ""
    evidence: list[str] = []       # human-readable lines of what was checked/found
    proposed_action: ProposedAction | None = None
    source: str = "playbook"       # "playbook" | "ai" | "ai-unavailable"
