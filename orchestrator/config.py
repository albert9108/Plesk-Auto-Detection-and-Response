"""Configuration loaded from environment (.env supported)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADR_", env_file=".env", extra="ignore")

    # Webhook auth (shared secret UptimeRobot/chat callbacks must present).
    webhook_token: str = "change-me"

    # Approval timeout (seconds) before an APPROVAL-tier action is auto-denied.
    approval_timeout: float = 300.0

    # UptimeRobot prober IPs (comma-separated) used to detect self-bans.
    probe_ips: str = ""

    # Notifier credentials (any subset may be set).
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""
    teams_webhook_url: str = ""
    public_url: str = ""

    # Audit DB path.
    audit_db: str = "adr-audit.sqlite"

    def probe_ip_list(self) -> list[str]:
        return [ip.strip() for ip in self.probe_ips.split(",") if ip.strip()]
