from __future__ import annotations

from fastapi.testclient import TestClient

from orchestrator.alerts.ingest import parse_uptimerobot
from orchestrator.alerts.models import AlertKind
from orchestrator.app import create_app
from orchestrator.config import Settings

from .conftest import FakeClient


def test_parse_uptimerobot_down():
    alert = parse_uptimerobot({
        "monitorFriendlyName": "Example", "monitorURL": "https://example.com/", "alertType": "1",
    })
    assert alert.kind == AlertKind.DOWN
    assert alert.domain == "example.com"


def test_parse_uptimerobot_up():
    alert = parse_uptimerobot({"monitorURL": "https://x.io", "alertType": "2"})
    assert alert.kind == AlertKind.UP


def test_webhook_rejects_bad_token(tmp_path):
    s = Settings(webhook_token="secret", audit_db=str(tmp_path / "a.sqlite"))
    app = create_app(s, client=FakeClient())
    c = TestClient(app)
    r = c.post("/webhook/uptimerobot?token=wrong", json={})
    assert r.status_code == 401


def test_webhook_runs_incident_and_auto_remediates(tmp_path):
    s = Settings(webhook_token="secret", audit_db=str(tmp_path / "a.sqlite"), probe_ips="203.0.113.5")
    client = FakeClient(banned={"203.0.113.5": ["plesk-apache"]})
    app = create_app(s, client=client)
    c = TestClient(app)
    r = c.post(
        "/webhook/uptimerobot?token=secret",
        json={"monitorURL": "https://example.com", "alertType": "1"},
    )
    assert r.status_code == 200
    assert r.json()["explained"] is True
    assert ("unban_ip", "203.0.113.5", "plesk-apache") in client.calls


def test_chat_approval_callback(tmp_path):
    s = Settings(webhook_token="secret", audit_db=str(tmp_path / "a.sqlite"))
    app = create_app(s, client=FakeClient())
    c = TestClient(app)
    # no pending approval -> resolved False, but endpoint works
    r = c.post("/webhook/chat", json={"incident_id": "nope", "decision": "approve"})
    assert r.status_code == 200
    assert r.json() == {"resolved": False}
