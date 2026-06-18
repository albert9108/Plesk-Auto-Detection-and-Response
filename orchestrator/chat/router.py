"""Routes inbound chat events: approval decisions and simple status questions.

Approval decisions resolve pending approvals in the ApprovalRegistry. Free-text
questions get a quick deterministic answer for common asks ("status"); anything
else can be forwarded to the AI investigator's read tools (left as an extension).
"""

from __future__ import annotations

from ..client import ToolClient
from ..notify.base import ApprovalRegistry


class ChatRouter:
    def __init__(self, approvals: ApprovalRegistry, client: ToolClient | None):
        self.approvals = approvals
        self.client = client

    def decide(self, incident_id: str, decision: str) -> bool:
        """Resolve an approval. Returns True if a pending approval was matched."""
        return self.approvals.resolve(incident_id, decision.lower() in ("approve", "yes", "ok"))

    def parse_telegram_callback(self, data: str) -> tuple[str, str] | None:
        """callback_data looks like 'approve:<id>' or 'deny:<id>'."""
        if ":" not in data:
            return None
        decision, incident_id = data.split(":", 1)
        return incident_id, decision

    def answer(self, text: str) -> str:
        """Minimal conversational command handler for the team chatbot."""
        t = text.strip().lower()
        if self.client is None:
            return (
                "No default server is configured for direct queries. In multi-server "
                "mode, set `default: true` on one server in servers.yaml to enable "
                "`status`/`fail2ban` commands."
            )
        if t in ("status", "/status", "health"):
            h = self.client.system_health()
            return f"Load: {h['load']}\n\nDisk:\n{h['disk']}\n\nMemory:\n{h['memory']}"
        if t.startswith("fail2ban"):
            return self.client.fail2ban_status() or "no fail2ban output"
        return (
            "Commands: `status` (server health), `fail2ban` (jail status). "
            "For deeper questions, check the incident in chat or the audit log."
        )
