"""FastAPI application — webhook ingestion, approval callbacks, chat, health.

Endpoints:
  POST /webhook/uptimerobot   ingest a UptimeRobot alert (token-authenticated)
  POST /webhook/chat          generic approve/deny callback (Teams/Discord/manual)
  POST /webhook/telegram      Telegram bot updates (callback_query approvals + commands)
  GET  /health                liveness
"""

from __future__ import annotations

from fastapi import Body, FastAPI, Header, HTTPException, Request

from .alerts.ingest import parse_uptimerobot
from .audit.store import AuditStore
from .chat.router import ChatRouter
from .config import Settings
from .incident import IncidentHandler
from .notify.base import ApprovalRegistry, ConsoleNotifier, MultiNotifier, Notifier


def build_notifier(s: Settings) -> Notifier:
    notifiers: list[Notifier] = []
    if s.telegram_bot_token and s.telegram_chat_id:
        from .notify.telegram import TelegramNotifier

        notifiers.append(TelegramNotifier(s.telegram_bot_token, s.telegram_chat_id))
    if s.discord_webhook_url:
        from .notify.discord import DiscordNotifier

        notifiers.append(DiscordNotifier(s.discord_webhook_url))
    if s.teams_webhook_url:
        from .notify.teams import TeamsNotifier

        # The token lets Teams approve/deny buttons authenticate their callback.
        notifiers.append(TeamsNotifier(s.teams_webhook_url, s.public_url, token=s.webhook_token))
    return MultiNotifier(notifiers) if notifiers else ConsoleNotifier()


def create_app(settings: Settings | None = None, *, client=None, notifier=None) -> FastAPI:
    from .response.policy import Policy

    s = settings or Settings()
    app = FastAPI(title="Plesk-ADR Orchestrator")

    # Resolve how the brain reaches a box: multi-server inventory, or a single client.
    client_for = None
    chat_client = client
    if client is None and s.servers_file:
        from .servers import Inventory

        inventory = Inventory.load(s.servers_file)
        client_for = lambda alert: inventory.client_for(alert.domain)  # noqa: E731
        chat_client = inventory.client_for("")  # default server (may be None)
    elif client is None:
        from .client import LocalToolClient

        client = LocalToolClient()
        chat_client = client

    notifier = notifier or build_notifier(s)
    approvals = ApprovalRegistry()
    audit = AuditStore(s.audit_db)
    handler = IncidentHandler(
        client, notifier, Policy.load(), audit, approvals,
        client_for=client_for,
        probe_ips=s.probe_ip_list(), approval_timeout=s.approval_timeout,
    )
    router = ChatRouter(approvals, chat_client)

    def check_token(token: str | None, authorization: str | None = None) -> None:
        # Accept the secret via ?token= or an Authorization/X-ADR-Token header.
        if authorization and authorization.startswith("Bearer "):
            authorization = authorization[len("Bearer "):]
        if s.webhook_token not in (token, authorization):
            raise HTTPException(status_code=401, detail="bad webhook token")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.post("/webhook/uptimerobot")
    async def uptimerobot(request: Request, token: str = "",
                          authorization: str | None = Header(default=None)) -> dict:
        check_token(token, authorization)
        payload = await request.json()
        alert = parse_uptimerobot(payload)
        diag = await handler.handle(alert)
        return {"incident": True, "explained": diag.explained, "source": diag.source}

    @app.post("/webhook/chat")
    async def chat_callback(body: dict = Body(...), token: str = "",
                            authorization: str | None = Header(default=None)) -> dict:
        check_token(token, authorization)
        incident_id = body.get("incident_id", "")
        decision = body.get("decision", "")
        if incident_id and decision:
            matched = router.decide(incident_id, decision)
            return {"resolved": matched}
        if body.get("text"):
            return {"reply": router.answer(body["text"])}
        raise HTTPException(status_code=400, detail="expected incident_id+decision or text")

    @app.post("/webhook/telegram")
    async def telegram_update(update: dict = Body(...), token: str = "",
                              authorization: str | None = Header(default=None)) -> dict:
        check_token(token, authorization)
        cq = update.get("callback_query")
        if cq:
            parsed = router.parse_telegram_callback(cq.get("data", ""))
            if parsed:
                incident_id, decision = parsed
                return {"resolved": router.decide(incident_id, decision)}
        msg = update.get("message", {})
        if msg.get("text"):
            return {"reply": router.answer(msg["text"])}
        return {"ok": True}

    return app


def main() -> None:
    import uvicorn

    # Factory mode: builds the app lazily so importing this module has no side effects.
    uvicorn.run("orchestrator.app:create_app", host="0.0.0.0", port=8080, factory=True)


if __name__ == "__main__":
    main()
