"""Plesk-ADR orchestrator — the brain.

Receives UptimeRobot "domain down" webhooks, runs a deterministic diagnostic
playbook (no AI), falls back to a Claude investigator only when the playbook
cannot explain the outage, governs remediation through tiered policy, and
notifies the team across pluggable chat channels.
"""

__version__ = "0.1.0"
