# Architecture

## Data flow

```
UptimeRobot "domain down" ──(POST /webhook/uptimerobot?token=…)──►
  orchestrator/app.py
    └─ alerts/ingest.py  → Alert
       └─ incident.py (IncidentHandler.handle)
            1. playbooks/domain_down.py        # deterministic, no AI
            2. agent/investigator.py           # Claude fallback, only if unexplained
            3. response/policy.py              # AUTO | APPROVAL | FORBIDDEN
                 AUTO      → response/executor.py → client → MCP tool, then notify
                 APPROVAL  → notify.request_approval → wait → executor on approve
                 FORBIDDEN → block + notify
            * audit/store.py records every step
       client.py (ToolClient) ──► mcp_server (ServerTools → exec/runner.py)
```

## Modules

| Path | Responsibility |
|---|---|
| `mcp_server/exec/runner.py` | security choke point: allowlist, param validation, sudo, log-path guard |
| `mcp_server/tools.py` | high-level read/action operations over the runner |
| `mcp_server/server.py` | exposes tools over MCP (stdio/http); optional `mcp` dep |
| `mcp_server/allowlist.yaml` | commands + log paths the box may touch (mirrors sudoers) |
| `orchestrator/alerts/` | normalized `Alert`/`Diagnosis` models + UptimeRobot parser |
| `orchestrator/client.py` | `ToolClient` interface; `LocalToolClient` (in-process) |
| `orchestrator/playbooks/domain_down.py` | deterministic diagnosis (the no-AI path) |
| `orchestrator/agent/investigator.py` | Claude tool-use fallback; degrades without a key |
| `orchestrator/response/policy.{py,yaml}` | tier engine + config |
| `orchestrator/response/executor.py` | maps actions → MCP calls |
| `orchestrator/notify/` | `Notifier` interface + console/telegram/discord/teams + approvals |
| `orchestrator/incident.py` | orchestrates the whole flow |
| `orchestrator/chat/router.py` | approval callbacks + simple chatbot commands |
| `orchestrator/audit/store.py` | append-only SQLite audit log |

## The "domain down" playbook (check order)

1. **fail2ban banned our own UptimeRobot prober?** → `unban_ip` (AUTO). Most common
   false-positive.
2. **Web server (nginx/apache2) down?** → `restart_service` (AUTO).
3. **Disk full?** → `alert_only` (humans decide what to clear).
4. **Domain suspended/expired in Plesk?** → `alert_only` (APPROVAL-type business call).
5. **Recent errors in the domain's `error_log`** → gathered as evidence.

If none conclude, the gathered evidence is handed to the AI fallback; if the AI is
unavailable, the evidence is posted to chat so a human skips the log-hunting.

## Extending

- **New alert provider:** add a parser in `alerts/ingest.py` returning an `Alert`.
- **New action:** add it to `mcp_server/allowlist.yaml` (+ `sudoers.d`), a method in
  `tools.py`/`ToolClient`, an executor branch, and a tier in `policy.yaml`.
- **New chat channel:** implement the `Notifier` interface in `orchestrator/notify/`.
- **Split topology:** implement a remote MCP `ToolClient` and inject it into `create_app`.
