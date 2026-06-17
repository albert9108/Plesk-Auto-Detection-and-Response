"""Runnable end-to-end demo with NO real Plesk box and NO API key.

Simulates the most common case — UptimeRobot reports a domain down because
fail2ban banned the monitor's own prober IP — and shows the full
detect -> diagnose -> AUTO remediate -> notify flow on the console.

    python dev/demo.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.alerts.models import Alert  # noqa: E402
from orchestrator.audit.store import NullAudit  # noqa: E402
from orchestrator.incident import IncidentHandler  # noqa: E402
from orchestrator.notify.base import ApprovalRegistry, ConsoleNotifier  # noqa: E402
from orchestrator.response.policy import Policy  # noqa: E402
from tests.conftest import FakeClient  # noqa: E402


async def main() -> None:
    probe_ip = "203.0.113.5"
    client = FakeClient(banned={probe_ip: ["plesk-apache"]})
    handler = IncidentHandler(
        client, ConsoleNotifier(), Policy.load(), NullAudit(), ApprovalRegistry(),
        probe_ips=[probe_ip], use_ai_fallback=False,
    )
    print("=== Simulating UptimeRobot 'example.com is DOWN' ===")
    diag = await handler.handle(Alert(domain="example.com", url="https://example.com"))
    print("\n=== Result ===")
    print("explained:", diag.explained, "| source:", diag.source)
    print("root cause:", diag.root_cause)
    print("actions executed:", client.calls)


if __name__ == "__main__":
    asyncio.run(main())
