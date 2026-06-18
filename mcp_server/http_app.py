"""Authenticated HTTP facade for the on-box ServerTools.

Exposes each tool at `POST /tool/{name}` guarded by a bearer token, so an off-box
orchestrator can drive this box over a URL. The allowlist + sudoers still enforce
everything locally, so even an authenticated caller can only run allowlisted ops.

Run via the MCP server entrypoint with ADR_MCP_TRANSPORT=http (see server.py).
"""

from __future__ import annotations

import os

from fastapi import Body, FastAPI, Header, HTTPException

from .tools import ServerTools

# Tool name -> the ServerTools method invoked with the JSON body as kwargs.
ALLOWED_TOOLS = {
    "system_health", "service_status", "fail2ban_status", "find_ip_in_jails",
    "plesk_domain_info", "read_log", "unban_ip", "ban_ip", "restart_service",
}


def create_http_app(tools: ServerTools | None = None, token: str | None = None) -> FastAPI:
    tools = tools or ServerTools()
    token = token if token is not None else os.environ.get("ADR_MCP_TOKEN", "")

    app = FastAPI(title="Plesk-ADR on-box server")

    def check_auth(authorization: str | None) -> None:
        expected = f"Bearer {token}"
        if not token or authorization != expected:
            raise HTTPException(status_code=401, detail="missing or invalid bearer token")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.post("/tool/{name}")
    async def call_tool(
        name: str,
        params: dict = Body(default={}),
        authorization: str | None = Header(default=None),
    ) -> dict:
        check_auth(authorization)
        if name not in ALLOWED_TOOLS:
            raise HTTPException(status_code=404, detail=f"unknown tool {name!r}")
        method = getattr(tools, name)
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            result = method(**clean)
        except TypeError as exc:
            raise HTTPException(status_code=400, detail=f"bad params for {name}: {exc}")
        return {"result": result}

    return app
