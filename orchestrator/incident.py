"""Incident handler — the glue that runs the full detect→diagnose→respond flow.

Flow for a DOWN alert:
  1. deterministic playbook (no AI)
  2. if unexplained -> AI fallback investigator
  3. policy engine assigns a tier to any proposed action
       AUTO      -> execute, then notify
       APPROVAL  -> post approve/deny, wait, execute only if approved
       FORBIDDEN -> block, notify
  4. every step is recorded in the audit log and summarised to chat
"""

from __future__ import annotations

import uuid

from .agent import investigator as ai
from .alerts.models import Alert, AlertKind, Diagnosis, Tier
from .audit.store import AuditStore
from .client import ToolClient
from .notify.base import ApprovalRegistry, Notifier
from .playbooks import domain_down
from .response import executor
from .response.policy import Policy


class IncidentHandler:
    def __init__(
        self,
        client: ToolClient,
        notifier: Notifier,
        policy: Policy,
        audit: AuditStore,
        approvals: ApprovalRegistry,
        *,
        probe_ips: list[str] | None = None,
        approval_timeout: float = 300.0,
        use_ai_fallback: bool = True,
    ):
        self.client = client
        self.notifier = notifier
        self.policy = policy
        self.audit = audit
        self.approvals = approvals
        self.probe_ips = probe_ips or []
        self.approval_timeout = approval_timeout
        self.use_ai_fallback = use_ai_fallback

    async def handle(self, alert: Alert) -> Diagnosis:
        incident_id = uuid.uuid4().hex[:12]
        self.audit.record(incident_id, "alert", alert.model_dump())

        if alert.kind == AlertKind.UP:
            await self.notifier.notify(f"✅ Recovered: {alert.domain or alert.monitor} is back up.")
            self.audit.record(incident_id, "recovered", {"domain": alert.domain})
            return Diagnosis(alert=alert, explained=True, root_cause="recovered", source="playbook")

        # 1. deterministic playbook
        diag = domain_down.investigate(alert, self.client, probe_ips=self.probe_ips)

        # 2. AI fallback only if unexplained
        if not diag.explained and self.use_ai_fallback:
            diag = ai.investigate(alert, self.client, diag.evidence)
        self.audit.record(incident_id, "diagnosis", diag.model_dump())

        await self._respond(incident_id, diag)
        return diag

    async def _respond(self, incident_id: str, diag: Diagnosis) -> None:
        header = f"🚨 {diag.alert.domain or diag.alert.monitor} is DOWN [{incident_id}]"
        cause = diag.root_cause or "Could not determine the cause automatically."
        body = f"{header}\nCause: {cause}\nSource: {diag.source}"

        action = diag.proposed_action
        if action is None:
            await self.notifier.notify(body + "\n\nEvidence:\n" + "\n".join(diag.evidence[-8:]))
            return

        tier = self.policy.tier_for(action)
        self.audit.record(incident_id, "policy", {"action": action.model_dump(), "tier": tier.value})

        if tier == Tier.FORBIDDEN:
            await self.notifier.notify(f"{body}\n⛔ Proposed action '{action.name}' is FORBIDDEN — blocked.")
            return

        if tier == Tier.AUTO:
            result = self._execute(incident_id, action)
            await self.notifier.notify(
                f"{body}\n🤖 AUTO action '{action.name}' done: {result.get('output', result)}"
            )
            return

        # APPROVAL
        summary = f"{header}\nCause: {cause}\nProposed: {action.name} {action.params}\n{action.reason}"
        self.approvals.open(incident_id)
        await self.notifier.request_approval(incident_id, summary)
        approved = await self.approvals.wait(incident_id, self.approval_timeout)
        self.audit.record(incident_id, "approval", {"approved": approved})
        if approved:
            result = self._execute(incident_id, action)
            await self.notifier.notify(f"✅ Approved [{incident_id}] — '{action.name}': {result.get('output', result)}")
        else:
            await self.notifier.notify(f"❌ [{incident_id}] '{action.name}' denied/timed out — no change made.")

    def _execute(self, incident_id: str, action) -> dict:
        try:
            result = executor.execute(action, self.client)
        except executor.UnknownAction as exc:
            result = {"action": action.name, "ok": False, "output": f"no executor: {exc}"}
        self.audit.record(incident_id, "action", result)
        return result
