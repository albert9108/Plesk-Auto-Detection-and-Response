"""Pluggable notifier interface + a console notifier + the approval registry.

A Notifier delivers messages and renders approval prompts to one chat platform.
The same interface backs Telegram, Discord and Teams so you can run several at
once and pick a winner. Approval prompts carry an `incident_id`; when a teammate
clicks approve/deny, the platform calls back into /webhook/chat, which resolves
the matching pending approval via the ApprovalRegistry.
"""

from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable


@runtime_checkable
class Notifier(Protocol):
    name: str

    async def notify(self, text: str) -> None: ...

    async def request_approval(self, incident_id: str, summary: str) -> None: ...


class ConsoleNotifier:
    """Prints to stdout. Used in dev and tests; implements the full interface."""

    name = "console"

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def notify(self, text: str) -> None:
        self.sent.append(text)
        print(f"[notify] {text}")

    async def request_approval(self, incident_id: str, summary: str) -> None:
        msg = f"[approval:{incident_id}] {summary}\n  approve: POST /webhook/chat {{incident_id, decision:'approve'}}"
        self.sent.append(msg)
        print(msg)


class MultiNotifier:
    """Fans a message out to every configured notifier, isolating failures."""

    name = "multi"

    def __init__(self, notifiers: list[Notifier]):
        self.notifiers = notifiers

    async def notify(self, text: str) -> None:
        await asyncio.gather(*(self._safe(n.notify(text)) for n in self.notifiers))

    async def request_approval(self, incident_id: str, summary: str) -> None:
        await asyncio.gather(
            *(self._safe(n.request_approval(incident_id, summary)) for n in self.notifiers)
        )

    @staticmethod
    async def _safe(coro) -> None:
        try:
            await coro
        except Exception as exc:  # one channel failing must not block the others
            print(f"[notify] channel error: {exc!r}")


class ApprovalRegistry:
    """Tracks pending approvals so chat callbacks can resolve them."""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future] = {}

    def open(self, incident_id: str) -> asyncio.Future:
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[incident_id] = fut
        return fut

    def resolve(self, incident_id: str, approved: bool) -> bool:
        fut = self._pending.pop(incident_id, None)
        if fut and not fut.done():
            fut.set_result(approved)
            return True
        return False

    async def wait(self, incident_id: str, timeout: float) -> bool:
        fut = self._pending.get(incident_id) or self.open(incident_id)
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(incident_id, None)
            return False  # timeout => treated as denied (fail-safe)
