from __future__ import annotations

from fastapi.testclient import TestClient

from mcp_server.http_app import create_http_app
from orchestrator.alerts.models import Alert
from orchestrator.audit.store import NullAudit
from orchestrator.incident import IncidentHandler
from orchestrator.notify.base import ApprovalRegistry, ConsoleNotifier
from orchestrator.remote_client import HTTPToolClient
from orchestrator.response.policy import Policy
from orchestrator.servers import Inventory, ServerSpec

from .conftest import FakeClient


# ---- on-box HTTP facade (auth + dispatch) ----------------------------------

def test_http_app_requires_bearer_token():
    app = create_http_app(tools=FakeClient(banned={"1.2.3.4": ["ssh"]}), token="secret")
    c = TestClient(app)
    assert c.get("/health").status_code == 200            # health is open
    assert c.post("/tool/system_health", json={}).status_code == 401   # no token
    bad = c.post("/tool/system_health", json={}, headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401


def test_http_app_runs_tool_with_token():
    app = create_http_app(tools=FakeClient(banned={"1.2.3.4": ["ssh"]}), token="secret")
    c = TestClient(app)
    r = c.post("/tool/find_ip_in_jails", json={"ip": "1.2.3.4"},
               headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200
    assert r.json() == {"result": ["ssh"]}


def test_http_app_unknown_tool_404():
    app = create_http_app(tools=FakeClient(), token="t")
    c = TestClient(app)
    r = c.post("/tool/rm_rf", json={}, headers={"Authorization": "Bearer t"})
    assert r.status_code == 404


# ---- HTTPToolClient builds the right calls ---------------------------------

class RecordingHTTPClient(HTTPToolClient):
    def __init__(self):
        super().__init__("https://box", "tok")
        self.last = None

    def _post(self, name, params):
        self.last = (name, params)
        return {"ok": True}


def test_http_client_serializes_calls():
    c = RecordingHTTPClient()
    c.restart_service("nginx")
    assert c.last == ("restart_service", {"unit": "nginx"})
    c.unban_ip("1.1.1.1", "ssh")
    assert c.last == ("unban_ip", {"ip": "1.1.1.1", "jail": "ssh"})


# ---- inventory routing ------------------------------------------------------

def _inv():
    return Inventory([
        ServerSpec("web1", "https://b1", "t1", ["shop.com"], default=True),
        ServerSpec("web2", "https://b2", "t2", ["app.io"]),
    ])


def test_inventory_resolves_exact_then_default():
    inv = _inv()
    assert inv.resolve("app.io").name == "web2"
    assert inv.resolve("shop.com").name == "web1"
    assert inv.resolve("unknown.com").name == "web1"   # falls back to default


def test_inventory_no_default_returns_none():
    inv = Inventory([ServerSpec("only", "https://b", "t", ["x.com"])])
    assert inv.resolve("nope.com") is None


# ---- multi-server routing through the handler -------------------------------

async def test_handler_routes_per_domain():
    shop_client = FakeClient(banned={"203.0.113.5": ["plesk-apache"]})
    other_client = FakeClient()

    def client_for(alert: Alert):
        return shop_client if alert.domain == "shop.com" else other_client

    handler = IncidentHandler(
        None, ConsoleNotifier(), Policy.load(), NullAudit(), ApprovalRegistry(),
        client_for=client_for, probe_ips=["203.0.113.5"], use_ai_fallback=False,
    )
    await handler.handle(Alert(domain="shop.com", url="https://shop.com"))
    assert ("unban_ip", "203.0.113.5", "plesk-apache") in shop_client.calls
    assert other_client.calls == []   # the other box was untouched


async def test_handler_unknown_domain_notifies_and_stops():
    notifier = ConsoleNotifier()
    handler = IncidentHandler(
        None, notifier, Policy.load(), NullAudit(), ApprovalRegistry(),
        client_for=lambda alert: None, use_ai_fallback=False,
    )
    diag = await handler.handle(Alert(domain="ghost.com"))
    assert not diag.explained
    assert any("no server in the inventory" in m for m in notifier.sent)
