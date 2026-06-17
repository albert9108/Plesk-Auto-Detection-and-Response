# Plesk Auto-Detection & Response (ADR)

An uptime-alert-driven ecosystem for Plesk that turns *"a domain is down"* into a
correlated diagnosis and a governed response — instead of you hunting through
scattered logs.

When **UptimeRobot** reports a domain down, ADR:

1. **Detects** — receives the webhook.
2. **Diagnoses** — runs a deterministic *"domain down"* playbook (no AI) that walks the
   common causes across the scattered logs/state, and falls back to a **Claude**
   investigator only when the playbook can't explain it.
3. **Responds** — proposes a remediation governed by a 3-tier policy:
   **AUTO** (act + notify), **APPROVAL** (approve/deny in chat), **FORBIDDEN** (blocked).
4. **Notifies** — across pluggable channels (Telegram, Discord, Teams) and answers
   follow-up questions as a chatbot.

> The Anthropic API key is **optional** — the playbook handles the common cases with
> no AI. Add a key only for smart fallback on unusual outages.

## Architecture

```
UptimeRobot ──webhook──► orchestrator (the brain)
                              │  playbook (no AI) → AI fallback (Claude, optional)
                              │  policy engine: AUTO / APPROVAL / FORBIDDEN
                              ▼
                         MCP server ON the Plesk box   ← thin, allowlist-only,
                         (reads logs, runs sudo-allowlisted cmds)   sudoers-backed
                              │
                         Telegram / Discord / Teams  (notify + approve + chatbot)
```

Two components:

| Component | Where it runs | Role |
|---|---|---|
| `mcp_server/` | **on the Plesk/Azure VM** (systemd, dedicated non-root user) | thin execution layer: reads allowlisted logs, runs only sudoers-allowlisted commands |
| `orchestrator/` | off-box *or* on-box | the brain: ingest, playbook, AI fallback, policy, notify, audit |

The MCP server is **transport-agnostic** (`stdio` co-located, HTTP when split), so you
can start with everything on the box and split the brain off later with no code change.

## Security model (defense in depth)

- **No root needed.** A dedicated service user + a narrow `/etc/sudoers.d/plesk-adr`
  allowlist (`mcp_server/deploy/sudoers.d/plesk-adr`).
- **Single choke point.** `mcp_server/exec/runner.py` builds argv as a list (never a
  shell), validates every parameter against a strict regex, and refuses any command or
  log path not in `mcp_server/allowlist.yaml`.
- **Independent OS backstop.** Even a logic bug can't exceed what sudoers allows.
- **Tiered autonomy.** `orchestrator/response/policy.yaml` is the single knob; unknown
  actions fail safe to APPROVAL, forbidden actions are hard-blocked.
- **Full audit trail.** Every step is recorded in SQLite (`orchestrator/audit/`).

## Quick start (local, no Plesk box, no API key)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q              # 22 tests, hermetic
python dev/demo.py     # simulates the "monitor self-ban" outage end-to-end
```

## Run the orchestrator

```bash
cp .env.example .env   # set ADR_WEBHOOK_TOKEN, notifier creds, ADR_PROBE_IPS
pip install -e .       # add ".[ai]" for the Claude fallback
adr-orchestrator       # serves on :8080
```

Point UptimeRobot's webhook alert contact at
`https://<host>:8080/webhook/uptimerobot?token=<ADR_WEBHOOK_TOKEN>`.

## Deploy the MCP server on the Plesk box

See [docs/deployment.md](docs/deployment.md) for the service user, sudoers install,
and systemd unit.

## Status

Implemented: ingestion, deterministic playbook, policy engine, executor, three
notifiers, AI fallback (graceful-degrade), audit, MCP server + tools + deploy
artifacts, and a hermetic test suite. See [docs/architecture.md](docs/architecture.md).
