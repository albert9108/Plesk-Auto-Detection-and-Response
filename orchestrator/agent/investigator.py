"""AI fallback investigator (Claude).

Invoked ONLY when the deterministic playbook cannot explain an outage. It is given
the evidence the playbook already gathered plus the MCP read tools, and asked to
correlate them into a root cause and (optionally) a proposed remediation.

The Anthropic SDK is an optional dependency. If it (or the API key) is missing, the
investigator degrades gracefully: it returns an "ai-unavailable" diagnosis carrying
all the collected evidence, so a human still skips the log-hunting.
"""

from __future__ import annotations

import json
import os

from ..alerts.models import Alert, Diagnosis, ProposedAction
from ..client import ToolClient

DEFAULT_MODEL = os.environ.get("ADR_AI_MODEL", "claude-sonnet-4-6")
MAX_TOOL_TURNS = 8

SYSTEM_PROMPT = """You are a Plesk site-reliability investigator. A monitored domain \
is reporting DOWN and the deterministic playbook could not explain it. Use the provided \
read-only tools to pull and correlate the relevant (scattered) logs and state on the box, \
then determine the most likely root cause. Plesk logs live in places like \
/var/log/nginx, /var/log/apache2, /var/log/plesk, and \
/var/www/vhosts/system/<domain>/logs/. Be concise and evidence-driven. When done, call \
the `finish` tool with your root_cause and, if a safe remediation exists, a proposed \
action (one of: unban_ip, restart_service, ban_ip, alert_only)."""

# Read-only tools exposed to the model. Actions are never given to the model — the
# policy engine governs those after it returns a proposal.
READ_TOOLS = [
    {"name": "system_health", "description": "Load, disk and memory.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "service_status", "description": "Is a systemd unit active?",
     "input_schema": {"type": "object", "properties": {"unit": {"type": "string"}}, "required": ["unit"]}},
    {"name": "fail2ban_status", "description": "fail2ban status, optionally for one jail.",
     "input_schema": {"type": "object", "properties": {"jail": {"type": "string"}}}},
    {"name": "plesk_domain_info", "description": "Plesk info for a domain.",
     "input_schema": {"type": "object", "properties": {"domain": {"type": "string"}}, "required": ["domain"]}},
    {"name": "read_log", "description": "Tail an allowlisted log file.",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"}, "lines": {"type": "integer"}, "grep": {"type": "string"}},
      "required": ["path"]}},
]

FINISH_TOOL = {
    "name": "finish",
    "description": "Report the final root cause and optional remediation.",
    "input_schema": {"type": "object", "properties": {
        "root_cause": {"type": "string"},
        "action": {"type": "string", "enum": ["unban_ip", "restart_service", "ban_ip", "alert_only"]},
        "params": {"type": "object"},
        "action_reason": {"type": "string"},
    }, "required": ["root_cause"]},
}


def _unavailable(alert: Alert, evidence: list[str], note: str) -> Diagnosis:
    return Diagnosis(
        alert=alert, explained=False, source="ai-unavailable",
        root_cause="", evidence=[*evidence, f"(AI fallback unavailable: {note})"],
        proposed_action=None,
    )


def investigate(alert: Alert, client: ToolClient, prior_evidence: list[str]) -> Diagnosis:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _unavailable(alert, prior_evidence, "ANTHROPIC_API_KEY not set")
    try:
        import anthropic
    except ImportError:
        return _unavailable(alert, prior_evidence, "anthropic SDK not installed")

    sdk = anthropic.Anthropic(api_key=api_key)
    evidence = list(prior_evidence)
    messages = [{
        "role": "user",
        "content": (
            f"Domain: {alert.domain or alert.monitor}\nURL: {alert.url}\n"
            f"Playbook evidence so far:\n" + "\n".join(prior_evidence)
        ),
    }]

    for _ in range(MAX_TOOL_TURNS):
        resp = sdk.messages.create(
            model=DEFAULT_MODEL, max_tokens=1024, system=SYSTEM_PROMPT,
            tools=[*READ_TOOLS, FINISH_TOOL], messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})
        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if not tool_uses:
            break

        results = []
        for tu in tool_uses:
            if tu.name == "finish":
                return _finish_to_diagnosis(alert, evidence, tu.input)
            output = _dispatch_read(client, tu.name, tu.input)
            evidence.append(f"{tu.name}({tu.input}) -> {str(output)[:300]}")
            results.append({"type": "tool_result", "tool_use_id": tu.id,
                            "content": json.dumps(output, default=str)[:4000]})
        messages.append({"role": "user", "content": results})

    return _unavailable(alert, evidence, "no conclusion within tool-turn budget")


def _dispatch_read(client: ToolClient, name: str, args: dict):
    if name == "system_health":
        return client.system_health()
    if name == "service_status":
        return client.service_status(args["unit"])
    if name == "fail2ban_status":
        return client.fail2ban_status(args.get("jail"))
    if name == "plesk_domain_info":
        return client.plesk_domain_info(args["domain"])
    if name == "read_log":
        return client.read_log(args["path"], lines=args.get("lines", 200), grep=args.get("grep"))
    return {"error": f"unknown read tool {name}"}


def _finish_to_diagnosis(alert: Alert, evidence: list[str], data: dict) -> Diagnosis:
    action = None
    if data.get("action"):
        action = ProposedAction(
            name=data["action"],
            params={k: str(v) for k, v in (data.get("params") or {}).items()},
            reason=data.get("action_reason", ""),
        )
    return Diagnosis(
        alert=alert, explained=True, source="ai",
        root_cause=data.get("root_cause", ""), evidence=evidence, proposed_action=action,
    )
