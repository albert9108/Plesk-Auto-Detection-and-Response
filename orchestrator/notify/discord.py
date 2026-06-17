"""Discord notifier via an incoming webhook (ADR_DISCORD_WEBHOOK_URL).

Notification works with a plain webhook. Interactive approve/deny buttons require
a registered Discord application (components + interaction endpoint); until that is
configured we post the incident id and accept the decision via /webhook/chat or a
chat command, so approvals still work without the full app.
"""

from __future__ import annotations

import httpx


class DiscordNotifier:
    name = "discord"

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def _send(self, content: str) -> None:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(self.webhook_url, json={"content": content})

    async def notify(self, text: str) -> None:
        await self._send(text)

    async def request_approval(self, incident_id: str, summary: str) -> None:
        await self._send(
            f"🔐 **Approval needed** (`{incident_id}`)\n{summary}\n"
            f"Reply via /webhook/chat with decision approve|deny."
        )
