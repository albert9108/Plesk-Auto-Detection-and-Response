"""Multi-server inventory + per-domain routing.

The orchestrator can manage several Plesk boxes at once. `servers.yaml` lists each
box's on-box HTTP endpoint (URL + bearer token) and which domains it hosts. On an
alert, `Inventory.resolve(domain)` picks the right box; the orchestrator then talks to
that box's `HTTPToolClient`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .client import ToolClient


@dataclass
class ServerSpec:
    name: str
    url: str
    token: str
    domains: list[str] = field(default_factory=list)
    default: bool = False


class Inventory:
    def __init__(self, servers: list[ServerSpec]):
        self.servers = servers
        self._by_domain: dict[str, ServerSpec] = {}
        self._default: ServerSpec | None = None
        for spec in servers:
            for d in spec.domains:
                self._by_domain[d.lower()] = spec
            if spec.default and self._default is None:
                self._default = spec
        self._clients: dict[str, ToolClient] = {}

    @classmethod
    def load(cls, path: str) -> "Inventory":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        servers = [
            ServerSpec(
                name=s["name"], url=s["url"].rstrip("/"), token=s.get("token", ""),
                domains=s.get("domains", []), default=bool(s.get("default", False)),
            )
            for s in data.get("servers", [])
        ]
        return cls(servers)

    def resolve(self, domain: str) -> ServerSpec | None:
        if not domain:
            return self._default
        return self._by_domain.get(domain.lower(), self._default)

    def client_for(self, domain: str) -> ToolClient | None:
        spec = self.resolve(domain)
        if spec is None:
            return None
        if spec.name not in self._clients:
            from .remote_client import HTTPToolClient

            self._clients[spec.name] = HTTPToolClient(spec.url, spec.token)
        return self._clients[spec.name]
