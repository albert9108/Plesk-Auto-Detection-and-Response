"""Telegram notifier — supports inline-keyboard approve/deny buttons.

Set ADR_TELEGRAM_BOT_TOKEN and ADR_TELEGRAM_CHAT_ID. Button presses arrive as
Telegram `callback_query` updates; point the bot webhook at /webhook/telegram.
"""

from __future__ import annotations

import httpx

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramNotifier:
    name = "telegram"

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

    async def _post(self, method: str, payload: dict) -> None:
        url = API.format(token=self.token, method=method)
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(url, json=payload)

    async def notify(self, text: str) -> None:
        await self._post("sendMessage", {"chat_id": self.chat_id, "text": text})

    async def request_approval(self, incident_id: str, summary: str) -> None:
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ Approve", "callback_data": f"approve:{incident_id}"},
                {"text": "❌ Deny", "callback_data": f"deny:{incident_id}"},
            ]]
        }
        await self._post(
            "sendMessage",
            {"chat_id": self.chat_id, "text": f"🔐 Approval needed\n{summary}", "reply_markup": keyboard},
        )
