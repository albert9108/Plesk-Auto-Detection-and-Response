# Plesk-ADR — Detailed Install & Usage Guide

This guide takes you from a fresh checkout to a running, alerting system on your
Azure/Plesk server. It is written for a first-time setup and is copy-paste friendly.
If you just want a quick reference, see [deployment.md](deployment.md) instead.

> **TL;DR of what you must fill in:** a webhook secret, your UptimeRobot prober IPs,
> at least one chat channel's credentials, the sudoers username/paths for your box,
> and (optionally) an Anthropic API key. Every one of these is listed in the
> [Values you must fill in](#values-you-must-fill-in) checklist at the bottom.

---

## 1. What you'll end up with

When **UptimeRobot** reports a domain down, the system connects to your server,
correlates the scattered logs, diagnoses the cause, and responds under strict rules —
notifying your team on chat throughout.

```
UptimeRobot ──webhook──► orchestrator (brain)
                            │  playbook (no AI) → Claude fallback (optional)
                            │  policy: AUTO / APPROVAL / FORBIDDEN
                            ▼
                       MCP server ON the Plesk box  (allowlist + sudoers, no root)
                            │
                       Telegram / Discord / Teams  (notify + approve + chatbot)
```

---

## 2. Prerequisites

| Need | Notes |
|---|---|
| Azure VM running **Plesk** (Linux) | Your production box. |
| **SSH access via PEM key** (non-root) | The system never needs root; it uses a narrow sudoers allowlist. |
| **Python 3.11+** on the box | `python3 --version`. |
| An **UptimeRobot** account | Free tier is fine; it sends the down/up webhook. |
| At least one of **Telegram / Discord / Teams** | For alerts + approvals. You can enable several. |
| *(Optional)* **Anthropic API key** | Only for the AI fallback on unusual outages. The playbook works without it. |

---

## 3. Decide your topology

- **Everything on the box (recommended to start):** orchestrator + MCP server both run
  on the VM. No inbound port for MCP (the brain calls it in-process). Simplest.
- **Split brain (later):** run the orchestrator off-box and reach the MCP server over
  authenticated HTTPS. Better secret hygiene/resilience; requires opening one port.

This guide installs **everything on the box**. Splitting later is a config change only.

---

## 4. Step 1 — Get the code on the box

```bash
ssh -i your-key.pem youruser@your-server
sudo mkdir -p /opt/plesk-adr
sudo chown "$USER":"$USER" /opt/plesk-adr
git clone https://github.com/albert9108/Plesk-Auto-Detection-and-Response.git /opt/plesk-adr
cd /opt/plesk-adr
```

---

## 5. Step 2 — Service user + the sudoers backstop

A dedicated, unprivileged user runs the on-box layer. The sudoers file is the
**OS-level hard limit** on what it can ever do — even a bug can't exceed it.

```bash
# 1) Create the service user (no login shell)
sudo useradd --system --shell /usr/sbin/nologin plesk-adr

# 2) Find the real binary paths ON YOUR box — they vary by distro/Plesk version
which fail2ban-client    # e.g. /usr/bin/fail2ban-client
which systemctl          # e.g. /usr/bin/systemctl
which plesk              # e.g. /usr/sbin/plesk
```

Open `mcp_server/deploy/sudoers.d/plesk-adr` and:
- Replace `plesk-adr` with your service user if you chose a different name.
- Make sure each command path matches the `which` output above.
- Confirm the `systemctl restart …` unit names match your web/PHP services
  (e.g. `nginx`, `apache2`, `plesk-php*-fpm`).

Then install and **validate** it (never trust an unvalidated sudoers file):

```bash
sudo install -m 0440 -o root -g root \
  mcp_server/deploy/sudoers.d/plesk-adr /etc/sudoers.d/plesk-adr
sudo visudo -cf /etc/sudoers.d/plesk-adr      # must print "parsed OK"
```

> **Important:** `mcp_server/deploy/sudoers.d/plesk-adr` and
> `mcp_server/allowlist.yaml` must stay in sync. The YAML is what the Python layer
> permits; the sudoers file is the independent OS guarantee. If you add an action in
> one, add it in both.

---

## 6. Step 3 — Install the MCP server + systemd

```bash
sudo -u plesk-adr python3 -m venv /opt/plesk-adr/.venv
sudo -u plesk-adr /opt/plesk-adr/.venv/bin/pip install -e "/opt/plesk-adr[mcp]"

sudo cp mcp_server/deploy/plesk-adr-mcp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now plesk-adr-mcp
systemctl status plesk-adr-mcp --no-pager        # should be "active (running)"
```

If you run **everything on the box**, the orchestrator calls the tools in-process and
you can leave the MCP transport as `stdio` (the default in the unit file).

---

## 7. Step 4 — Install + configure the orchestrator

```bash
cd /opt/plesk-adr
# add the AI fallback too with:  pip install -e ".[ai]"
sudo -u plesk-adr /opt/plesk-adr/.venv/bin/pip install -e /opt/plesk-adr
cp .env.example .env
nano .env          # fill in the values below
```

### `.env` reference — every setting

All variables use the `ADR_` prefix except `ANTHROPIC_API_KEY`. Defaults are in
`orchestrator/config.py`.

| Variable | Required? | What it is | Where to get it / example |
|---|---|---|---|
| `ADR_WEBHOOK_TOKEN` | **Yes** | Shared secret. UptimeRobot must append `?token=…`; chat callbacks must send it. | Invent a long random string: `openssl rand -hex 24` |
| `ADR_PROBE_IPS` | **Strongly recommended** | Comma-separated UptimeRobot prober IPs, used to detect the "we banned our own monitor" case. | UptimeRobot's published IP list (see Step 7). `1.2.3.4,5.6.7.8` |
| `ADR_APPROVAL_TIMEOUT` | No (default `300`) | Seconds to wait for a human on an APPROVAL action before auto-denying. | `300` |
| `ANTHROPIC_API_KEY` | No (enables AI fallback) | Claude API key for diagnosing unusual outages. | console.anthropic.com → API keys. `sk-ant-…` |
| `ADR_AI_MODEL` | No (default `claude-sonnet-4-6`) | Model for the AI fallback. | `claude-sonnet-4-6` |
| `ADR_TELEGRAM_BOT_TOKEN` | If using Telegram | Bot token from BotFather. | See Step 5. `123456:ABC-…` |
| `ADR_TELEGRAM_CHAT_ID` | If using Telegram | Target chat/group id. | See Step 5. `-1001234567890` |
| `ADR_DISCORD_WEBHOOK_URL` | If using Discord | Channel incoming-webhook URL. | See Step 5. |
| `ADR_TEAMS_WEBHOOK_URL` | If using Teams | Channel incoming-webhook URL. | See Step 5. |
| `ADR_PUBLIC_URL` | If using Teams approvals | Public base URL of the orchestrator (Teams buttons POST back here). | `https://adr.example.com` |
| `ADR_AUDIT_DB` | No (default `adr-audit.sqlite`) | Path to the audit SQLite file. | `/opt/plesk-adr/adr-audit.sqlite` |

> If **no** notifier is configured, the orchestrator falls back to console output — fine
> for testing, but you'll want at least one channel for real use.

Run it:

```bash
/opt/plesk-adr/.venv/bin/adr-orchestrator       # serves on :8080
# GET /health should return {"status":"ok"}
```

*(For production, wrap this in its own systemd unit too — mirror
`plesk-adr-mcp.service`, but `ExecStart=/opt/plesk-adr/.venv/bin/adr-orchestrator`.)*

---

## 8. Step 5 — Set up your chat channel(s)

You only need one, but you can enable all three and pick a favourite.

### Telegram (supports approve/deny buttons)
1. In Telegram, message **@BotFather** → `/newbot` → follow prompts → copy the **token**
   into `ADR_TELEGRAM_BOT_TOKEN`.
2. Add the bot to your group (or DM it). To get the **chat id**, message **@userinfobot**,
   or call `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `chat.id`. Put it in
   `ADR_TELEGRAM_CHAT_ID`.
3. For the approve/deny buttons to work, register the bot webhook to your orchestrator.
   **Include your `ADR_WEBHOOK_TOKEN`** so Telegram callbacks pass auth:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<your-host>/webhook/telegram?token=<ADR_WEBHOOK_TOKEN>"
   ```

### Discord
1. Server Settings → **Integrations → Webhooks → New Webhook** → choose the channel →
   **Copy Webhook URL** → put it in `ADR_DISCORD_WEBHOOK_URL`.
   (Notifications work immediately; approvals come back via `/webhook/chat`.)

### Microsoft Teams
1. Channel → **⋯ → Connectors → Incoming Webhook → Configure** → name it → **Create** →
   copy the URL into `ADR_TEAMS_WEBHOOK_URL`.
2. Set `ADR_PUBLIC_URL` so the Adaptive Card approve/deny buttons can POST back.

---

## 9. Step 6 — Point UptimeRobot at the orchestrator

1. UptimeRobot dashboard → **My Settings → Alert Contacts → Add Alert Contact**.
2. Type: **Webhook**.
3. URL to notify:
   ```
   https://<your-host>:8080/webhook/uptimerobot?token=<ADR_WEBHOOK_TOKEN>
   ```
4. POST value (JSON). The parser (`orchestrator/alerts/ingest.py`) accepts these fields:
   ```json
   {
     "monitorFriendlyName": "*monitorFriendlyName*",
     "monitorURL": "*monitorURL*",
     "alertType": "*alertType*"
   }
   ```
   `alertType` is `1` for **down** and `2` for **up** (recovery). UptimeRobot replaces the
   `*…*` tokens automatically.
5. Attach this alert contact to the monitors for the domains you want covered.

---

## 10. Step 7 — Fill `ADR_PROBE_IPS` (important)

The single most common false "down" is fail2ban banning UptimeRobot's own prober IP —
your site is fine, but the monitor can't reach it. To auto-fix this, the playbook needs
to know those IPs. Get UptimeRobot's current prober IP ranges from their docs/dashboard
("locations / IPs to whitelist") and list them comma-separated in `ADR_PROBE_IPS`.

When set, a down alert whose prober IP is banned is diagnosed instantly and the IP is
**auto-unbanned** (AUTO tier).

---

## 11. Step 8 — Tune the response policy

`orchestrator/response/policy.yaml` is the single knob for autonomy. Seeded defaults:

| Action | Tier | Meaning |
|---|---|---|
| `unban_ip` | **AUTO** | Acts immediately, then notifies. |
| `restart_service` | **AUTO** | Restart a hung web/PHP service. |
| `ban_ip` | **AUTO** | Ban a clearly-malicious IP. |
| `alert_only` | **AUTO** | Notify only; no change made. |
| `disable_domain`, `enable_domain`, `flush_jail` | **APPROVAL** | Posts approve/deny to chat; runs only if approved. |
| `delete_data`, `change_dns`, `modify_sudoers`, … | **FORBIDDEN** | Hard-blocked, never runs. |

- **Fail-safe:** any action not listed falls to `default_tier: approval`.
- Move actions between tiers to match your risk appetite. Start conservative.

---

## 12. Step 9 — Smoke test

```bash
# 1) Health
curl -s http://localhost:8080/health        # {"status":"ok"}

# 2) Offline end-to-end demo (no box state, no API key needed)
/opt/plesk-adr/.venv/bin/python dev/demo.py  # shows detect→diagnose→AUTO→notify

# 3) Fire a synthetic UptimeRobot "down" at the real endpoint
curl -s -X POST "http://localhost:8080/webhook/uptimerobot?token=<ADR_WEBHOOK_TOKEN>" \
  -H 'Content-Type: application/json' \
  -d '{"monitorURL":"https://yourdomain.com","monitorFriendlyName":"Test","alertType":"1"}'
```

Confirm a notification appears in your chosen chat channel and the response matches what
the playbook found.

---

## 13. Step 10 — Go live safely

1. **Playbook-only first:** leave `ANTHROPIC_API_KEY` unset and watch real alerts produce
   correct diagnoses for a while.
2. Refine `ADR_PROBE_IPS` and `policy.yaml`.
3. **Enable AUTO gradually:** keep risky actions on APPROVAL; promote to AUTO only once
   you trust them. Add the AI key last, for the unusual cases.

---

## 14. Daily usage

- **A down alert** posts: the domain, the root cause, the evidence/source, and either the
  AUTO action taken or an approve/deny prompt.
- **Approvals:** click **Approve** to execute, **Deny** (or let it time out) to skip. The
  decision is recorded in the audit log.
- **Chatbot commands** (via `orchestrator/chat/router.py`):
  - `status` → server load, disk, memory.
  - `fail2ban` → jail status.
- **Audit log:** every alert, diagnosis, decision and action is in the SQLite DB
  (`ADR_AUDIT_DB`). Inspect an incident:
  ```bash
  sqlite3 adr-audit.sqlite "SELECT ts,kind,data FROM events WHERE incident_id='<id>' ORDER BY id;"
  ```

---

## 15. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Actions fail; logs show a sudo password prompt | sudoers not matching. Re-check `/etc/sudoers.d/plesk-adr` paths vs `which …`; run `sudo -u plesk-adr sudo -n fail2ban-client status`. |
| "command not in allowlist" | The binary path in `allowlist.yaml`/sudoers differs from your box. Align both. |
| fail2ban actions do nothing | Your jail names differ. Check `fail2ban-client status`; the defaults are in `mcp_server/tools.py` (`DEFAULT_PLESK_JAILS`). |
| No chat messages | No notifier configured → it's logging to console. Set a channel's creds and restart. |
| Diagnoses but never uses AI | Expected without `ANTHROPIC_API_KEY` — it posts the collected evidence instead. Add the key + `pip install -e ".[ai]"` to enable. |
| Webhook returns 401 | `?token=` doesn't match `ADR_WEBHOOK_TOKEN`. |
| Port 8765 times out from outside (curl hangs / connection refused) | **Plesk manages `iptables` directly** — `ufw` being inactive does NOT mean the box is open. Plesk's firewall has a default `DROP` policy; port 8765 is not in its allowlist. Fix: in Plesk panel → **Tools & Settings → Firewall → Add Custom Rule** (TCP, port 8765, source = your orchestrator IP, Allow) then Apply Changes. For a quick test first: `sudo iptables -I INPUT 1 -p tcp --dport 8765 -s YOUR_IP -j ACCEPT` (not persistent). Azure NSG alone is not sufficient — both the NSG and the Plesk/iptables firewall must allow the port. |

---

## Off-box orchestrator + multiple servers (HTTP)

Run the brain on a separate machine (even your laptop, to try it) and have it manage
several Plesk boxes. Each box exposes its tools at an authenticated **URL**; the
orchestrator routes each alert to the box that hosts the down domain.

### On each Plesk box — run the on-box server in HTTP mode

```bash
# As the service user, with a STRONG per-box secret:
export ADR_MCP_TRANSPORT=http
export ADR_MCP_TOKEN="$(openssl rand -hex 24)"   # save this; the orchestrator needs it
export ADR_MCP_HTTP_PORT=8765
/opt/plesk-adr/.venv/bin/adr-mcp-server          # serves :8765

# from anywhere allowed:
curl https://box1.example.com:8765/health        # {"status":"ok"}
curl -H "Authorization: Bearer $ADR_MCP_TOKEN" \
     -X POST https://box1.example.com:8765/tool/system_health -d '{}'
```

> **Security — this URL is now reachable over the network.** Protect it with:
> 1. a **strong `ADR_MCP_TOKEN`** (the bearer token above),
> 2. **HTTPS** (terminate TLS with nginx/Caddy in front, or a real cert), and
> 3. a **firewall rule** restricting port `8765` to your orchestrator where possible.
>
> The allowlist + sudoers still apply, so even an authenticated caller can only run
> the safe, allowlisted operations — but keep the token secret.

For production, bake `ADR_MCP_TRANSPORT=http` and `ADR_MCP_TOKEN` into the systemd unit
(`mcp_server/deploy/plesk-adr-mcp.service`) instead of exporting by hand.

### On the orchestrator machine — list your servers

```bash
cp servers.yaml.example servers.yaml
nano servers.yaml          # one block per box: name, url, token, domains, default
# tell the orchestrator to use it:
echo 'ADR_SERVERS_FILE=servers.yaml' >> .env
adr-orchestrator
```

`servers.yaml`:
```yaml
servers:
  - name: web1
    url: https://box1.example.com:8765
    token: <box1's ADR_MCP_TOKEN>
    domains: [shop.com, blog.com]
    default: true          # used when a domain matches no server
  - name: web2
    url: https://box2.example.com:8765
    token: <box2's ADR_MCP_TOKEN>
    domains: [app.io]
```

When `ADR_SERVERS_FILE` is set, an alert for `shop.com` is routed to `web1`; an alert
for a domain not listed anywhere goes to the `default` server (or is reported as
"unknown server" if there's no default). Leave `ADR_SERVERS_FILE` unset to run
everything in-process on a single box.

### Trying it on your computer first

1. Run the on-box HTTP server on **one** Plesk box (steps above).
2. On your computer: `pip install -e .`, create `servers.yaml` with that one box, set
   `ADR_SERVERS_FILE`, run `adr-orchestrator`.
3. Fire a test alert for one of its domains:
   ```bash
   curl -X POST "http://localhost:8080/webhook/uptimerobot?token=<ADR_WEBHOOK_TOKEN>" \
     -H 'Content-Type: application/json' \
     -d '{"monitorURL":"https://shop.com","alertType":"1"}'
   ```
   You should see it reach `web1` and post a Teams notification.

> **Note:** for *real* UptimeRobot and Teams traffic, the orchestrator must be reachable
> from the internet (they call it). On a laptop, use the `curl` simulation above, or
> expose it temporarily with a tunnel (e.g. `cloudflared`/`ngrok`) while testing.

## Values you must fill in

| Value | Lives in | Required? |
|---|---|---|
| `ADR_WEBHOOK_TOKEN` (random secret) | `.env` + UptimeRobot webhook URL | **Yes** |
| `ADR_PROBE_IPS` (UptimeRobot prober IPs) | `.env` | Strongly recommended |
| At least one chat channel's creds (`ADR_TELEGRAM_*` / `ADR_DISCORD_WEBHOOK_URL` / `ADR_TEAMS_WEBHOOK_URL`) | `.env` | One required for real use |
| `ADR_PUBLIC_URL` (if using Teams approvals) | `.env` | Conditional |
| `ANTHROPIC_API_KEY` (+ `ADR_AI_MODEL`) | `.env` | Optional (AI fallback) |
| Service username + binary paths + service unit names | `mcp_server/deploy/sudoers.d/plesk-adr` (mirror `mcp_server/allowlist.yaml`) | **Yes** |
| Action → tier mapping | `orchestrator/response/policy.yaml` | Review before AUTO |
| UptimeRobot webhook URL + JSON body | UptimeRobot dashboard | **Yes** |
| `ADR_MCP_TOKEN` (per-box bearer secret) | each box's env / systemd unit | If off-box (HTTP) |
| Server inventory (`url` + `token` + `domains` per box) | `servers.yaml` + `ADR_SERVERS_FILE` | If off-box / multi-server |
