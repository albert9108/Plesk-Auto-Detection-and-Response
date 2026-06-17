# Deployment

Two topologies are supported. Start with **everything on the box** (simplest, zero
inbound ports for the MCP server); split the brain off later by changing only the
MCP transport.

## 1. MCP server on the Plesk/Azure VM

```bash
# Dedicated, unprivileged service user
sudo useradd --system --shell /usr/sbin/nologin plesk-adr

# Code + venv
sudo mkdir -p /opt/plesk-adr && sudo chown plesk-adr:plesk-adr /opt/plesk-adr
sudo -u plesk-adr git clone <repo> /opt/plesk-adr
sudo -u plesk-adr python3 -m venv /opt/plesk-adr/.venv
sudo -u plesk-adr /opt/plesk-adr/.venv/bin/pip install -e "/opt/plesk-adr[mcp]"

# The narrow sudoers backstop — VALIDATE before trusting
sudo install -m 0440 -o root -g root \
  /opt/plesk-adr/mcp_server/deploy/sudoers.d/plesk-adr /etc/sudoers.d/plesk-adr
sudo visudo -cf /etc/sudoers.d/plesk-adr

# systemd
sudo cp /opt/plesk-adr/mcp_server/deploy/plesk-adr-mcp.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now plesk-adr-mcp
```

`mcp_server/allowlist.yaml` and `sudoers.d/plesk-adr` **must stay in sync** — the
sudoers file is the OS-level guarantee. Verify the `plesk`/`fail2ban-client`/`systemctl`
paths match your distro (`which fail2ban-client`).

## 2. Orchestrator

```bash
cp .env.example .env       # ADR_WEBHOOK_TOKEN, ADR_PROBE_IPS, notifier creds
pip install -e ".[ai]"     # omit [ai] to run playbook-only (no Claude)
adr-orchestrator           # :8080  (uvicorn factory: orchestrator.app:create_app)
```

- **Everything on the box:** run the orchestrator on the same VM; `LocalToolClient`
  calls the MCP tools in-process. No inbound port for MCP.
- **Split:** run the orchestrator off-box and point it at the MCP server over
  authenticated HTTPS (implement a remote `ToolClient`); restrict the MCP port to the
  orchestrator's IP.

## 3. UptimeRobot

Add an **Alert Contact → Webhook**. POST to
`https://<orchestrator>/webhook/uptimerobot?token=<ADR_WEBHOOK_TOKEN>` with a JSON body
including `monitorURL`, `monitorFriendlyName`, and `alertType` (1=down, 2=up).

## 4. Notifiers

Set any subset; if none are configured the orchestrator logs to the console.

- **Telegram:** `ADR_TELEGRAM_BOT_TOKEN` + `ADR_TELEGRAM_CHAT_ID`; set the bot webhook
  to `/webhook/telegram` for approve/deny buttons.
- **Discord:** `ADR_DISCORD_WEBHOOK_URL` (channel incoming webhook).
- **Teams:** `ADR_TEAMS_WEBHOOK_URL` + `ADR_PUBLIC_URL` (Adaptive Card approval buttons
  POST back to `/webhook/chat`).

## Going live safely

1. Deploy in playbook-only mode and watch diagnoses for real alerts.
2. Tune `ADR_PROBE_IPS` and `policy.yaml`.
3. Enable AUTO actions one at a time; keep risky ones on APPROVAL.
