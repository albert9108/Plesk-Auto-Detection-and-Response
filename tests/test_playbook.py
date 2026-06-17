from __future__ import annotations

from orchestrator.alerts.models import Alert
from orchestrator.playbooks import domain_down

from .conftest import FakeClient


def test_detects_self_banned_prober():
    client = FakeClient(banned={"203.0.113.5": ["plesk-apache"]})
    alert = Alert(domain="example.com", url="https://example.com")
    diag = domain_down.investigate(alert, client, probe_ips=["203.0.113.5"])
    assert diag.explained
    assert diag.proposed_action.name == "unban_ip"
    assert diag.proposed_action.params == {"ip": "203.0.113.5", "jail": "plesk-apache"}


def test_detects_down_web_service():
    client = FakeClient(services={"nginx": "failed"})
    diag = domain_down.investigate(Alert(domain="example.com"), client, probe_ips=[])
    assert diag.explained
    assert diag.proposed_action.name == "restart_service"
    assert diag.proposed_action.params["unit"] == "nginx"


def test_detects_full_disk():
    full = "Filesystem Size Used Avail Use% Mounted\n/dev/sda1 50G 50G 0 100% /"
    client = FakeClient(disk=full)
    diag = domain_down.investigate(Alert(domain="example.com"), client, probe_ips=[])
    assert diag.explained
    assert "100%" in diag.root_cause or "usage" in diag.root_cause.lower()


def test_unexplained_returns_evidence_only():
    client = FakeClient()  # everything healthy
    diag = domain_down.investigate(Alert(domain="example.com"), client, probe_ips=[])
    assert not diag.explained
    assert diag.evidence  # evidence still gathered for the AI fallback
