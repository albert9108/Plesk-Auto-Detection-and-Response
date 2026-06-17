from __future__ import annotations

import asyncio

from orchestrator.alerts.models import Alert, AlertKind, Diagnosis, ProposedAction
from orchestrator.audit.store import NullAudit
from orchestrator.incident import IncidentHandler
from orchestrator.notify.base import ApprovalRegistry, ConsoleNotifier
from orchestrator.response.policy import Policy

from .conftest import FakeClient


def make_handler(client, **kw):
    return IncidentHandler(
        client, ConsoleNotifier(), Policy.load(), NullAudit(), ApprovalRegistry(),
        use_ai_fallback=False, **kw,
    )


async def test_auto_remediation_executes_immediately():
    client = FakeClient(banned={"203.0.113.5": ["plesk-apache"]})
    handler = make_handler(client, probe_ips=["203.0.113.5"])
    diag = await handler.handle(Alert(domain="example.com", url="https://example.com"))
    assert diag.explained
    assert ("unban_ip", "203.0.113.5", "plesk-apache") in client.calls


async def test_recovery_alert_notifies_and_skips_investigation():
    client = FakeClient()
    handler = make_handler(client)
    diag = await handler.handle(Alert(domain="example.com", kind=AlertKind.UP))
    assert diag.root_cause == "recovered"
    assert client.calls == []


async def test_approval_flow_executes_only_on_approve():
    client = FakeClient()
    approvals = ApprovalRegistry()
    # Custom policy makes restart_service APPROVAL-tier so we can exercise the
    # approve-then-execute path with an action the executor actually implements.
    policy = Policy({"default_tier": "approval", "actions": {"restart_service": "approval"}})
    handler = IncidentHandler(
        client, ConsoleNotifier(), policy, NullAudit(), approvals,
        use_ai_fallback=False, approval_timeout=2.0,
    )
    diag = Diagnosis(
        alert=Alert(domain="example.com"), explained=True, root_cause="needs human",
        proposed_action=ProposedAction(name="restart_service", params={"unit": "nginx"}),
    )
    task = asyncio.create_task(handler._respond("inc1", diag))
    await asyncio.sleep(0.05)  # let it post the approval request
    assert approvals.resolve("inc1", True)
    await task
    assert ("restart_service", "nginx") in client.calls  # executed only after approval


async def test_approval_denied_times_out():
    client = FakeClient()
    handler = IncidentHandler(
        client, ConsoleNotifier(), Policy.load(), NullAudit(), ApprovalRegistry(),
        use_ai_fallback=False, approval_timeout=0.1,
    )
    diag = Diagnosis(
        alert=Alert(domain="example.com"), explained=True,
        proposed_action=ProposedAction(name="unban_ip", params={"ip": "1.1.1.1", "jail": "ssh"}),
    )
    # force APPROVAL by checking a non-auto action via policy isn't needed here:
    # unban_ip is AUTO, so swap to an approval action to assert the timeout path.
    diag.proposed_action.name = "flush_jail"
    await handler._respond("inc2", diag)
    assert client.calls == []  # nothing executed on timeout


async def test_forbidden_action_blocked():
    client = FakeClient()
    handler = make_handler(client)
    diag = Diagnosis(
        alert=Alert(domain="example.com"), explained=True,
        proposed_action=ProposedAction(name="delete_data", params={}),
    )
    await handler._respond("inc3", diag)
    assert client.calls == []  # forbidden never executes
