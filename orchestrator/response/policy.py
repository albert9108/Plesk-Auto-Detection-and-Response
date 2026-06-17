"""Tier engine — decides whether a proposed action is auto/approval/forbidden."""

from __future__ import annotations

from pathlib import Path

import yaml

from ..alerts.models import ProposedAction, Tier

DEFAULT_POLICY = Path(__file__).resolve().parent / "policy.yaml"


class Policy:
    def __init__(self, data: dict):
        self.default_tier = Tier(data.get("default_tier", "approval"))
        self._actions = {k: Tier(v) for k, v in data.get("actions", {}).items()}
        self._forbidden = set(data.get("forbidden", []))

    @classmethod
    def load(cls, path: str | None = None) -> "Policy":
        with open(Path(path) if path else DEFAULT_POLICY, "r", encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh) or {})

    def tier_for(self, action: ProposedAction | str) -> Tier:
        name = action.name if isinstance(action, ProposedAction) else action
        if name in self._forbidden:
            return Tier.FORBIDDEN
        return self._actions.get(name, self.default_tier)
