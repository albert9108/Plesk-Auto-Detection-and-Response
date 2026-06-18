"""Microsoft Teams notifier via an Incoming Webhook (ADR_TEAMS_WEBHOOK_URL).

Notifications post a MessageCard. Approval renders an Adaptive Card with
Action.Http buttons that POST the decision to /webhook/chat (set ADR_PUBLIC_URL so
the buttons target a reachable endpoint).
"""

from __future__ import annotations

import os

import httpx


class TeamsNotifier:
    name = "teams"

    def __init__(self, webhook_url: str, public_url: str | None = None, token: str = ""):
        self.webhook_url = webhook_url
        self.public_url = (public_url or os.environ.get("ADR_PUBLIC_URL", "")).rstrip("/")
        self.token = token

    async def _send(self, card: dict) -> None:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(self.webhook_url, json=card)

    async def notify(self, text: str) -> None:
        await self._send(
            {"@type": "MessageCard", "@context": "https://schema.org/extensions",
             "summary": "Plesk-ADR", "text": text}
        )

    async def request_approval(self, incident_id: str, summary: str) -> None:
        target = f"{self.public_url}/webhook/chat"
        if self.token:
            target += f"?token={self.token}"
        actions = []
        for label, decision in (("✅ Approve", "approve"), ("❌ Deny", "deny")):
            actions.append({
                "@type": "HttpPOST", "name": label,
                "target": target,
                "body": f'{{"incident_id":"{incident_id}","decision":"{decision}"}}',
            })
        await self._send({
            "@type": "MessageCard", "@context": "https://schema.org/extensions",
            "summary": "Approval needed", "title": "🔐 Approval needed",
            "text": summary, "potentialAction": actions,
        })
