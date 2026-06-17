"""On-box MCP execution layer for Plesk-ADR.

A thin, auditable server that reads allowlisted logs locally and runs only
allowlisted (sudoers-backed) commands. The Claude "brain" / orchestrator
connects to it; this layer never makes decisions, it only executes within
hard limits.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
