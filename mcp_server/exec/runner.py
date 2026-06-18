"""Command runner — the single choke point for everything the MCP server executes.

Security model (defense in depth):
  1. Only logical commands declared in allowlist.yaml may run.
  2. Every substituted parameter is validated against a strict regex first.
  3. argv is built as a list and executed with shell=False — no injection surface.
  4. Log reads are restricted to allowlisted path prefixes (no traversal).
  5. `sudo` commands additionally require a matching deploy/sudoers.d rule at the
     OS level, which is an independent backstop outside this process.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_ALLOWLIST = Path(__file__).resolve().parent.parent / "allowlist.yaml"


class CommandNotAllowed(Exception):
    """Raised when a requested command or parameter violates the allowlist."""


class LogPathNotAllowed(Exception):
    """Raised when a log read targets a path outside the allowlist or is unreadable."""


@dataclass
class CommandResult:
    command: str
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class Allowlist:
    """Parsed, validated view of allowlist.yaml."""

    def __init__(self, data: dict):
        self.commands: dict[str, dict] = data.get("commands", {})
        self.log_paths: list[str] = data.get("log_paths", [])
        self._patterns: dict[str, re.Pattern] = {
            name: re.compile(pat) for name, pat in data.get("param_patterns", {}).items()
        }

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "Allowlist":
        path = Path(path) if path else DEFAULT_ALLOWLIST
        with open(path, "r", encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh) or {})

    def validate_param(self, name: str, value: str) -> str:
        pattern = self._patterns.get(name)
        if pattern is None:
            raise CommandNotAllowed(f"no validation pattern declared for parameter {name!r}")
        if not pattern.fullmatch(value):
            raise CommandNotAllowed(f"parameter {name}={value!r} fails its validation pattern")
        return value

    def build_argv(self, command: str, params: dict[str, str]) -> tuple[list[str], bool]:
        spec = self.commands.get(command)
        if spec is None:
            raise CommandNotAllowed(f"command {command!r} is not in the allowlist")
        argv: list[str] = []
        for token in spec["argv"]:
            if token.startswith("{") and token.endswith("}"):
                key = token[1:-1]
                if key not in params:
                    raise CommandNotAllowed(f"command {command!r} requires parameter {key!r}")
                argv.append(self.validate_param(key, str(params[key])))
            else:
                argv.append(token)
        return argv, bool(spec.get("sudo", False))

    def is_log_path_allowed(self, path: str) -> bool:
        resolved = os.path.realpath(path)
        for prefix in self.log_paths:
            base = os.path.realpath(prefix.rstrip("/")) if prefix.endswith("/") else prefix
            if prefix.endswith("/"):
                if resolved == base or resolved.startswith(base + os.sep):
                    return True
            elif resolved == os.path.realpath(prefix):
                return True
        return False


class CommandRunner:
    """Executes allowlisted commands. Subclass/override `_spawn` to mock in tests."""

    def __init__(self, allowlist: Allowlist | None = None, *, use_sudo: bool = True, timeout: int = 30):
        self.allowlist = allowlist or Allowlist.load()
        self.use_sudo = use_sudo
        self.timeout = timeout

    def run(self, command: str, **params: str) -> CommandResult:
        argv, needs_sudo = self.allowlist.build_argv(command, params)
        full = (["sudo", "-n", *argv] if (needs_sudo and self.use_sudo) else argv)
        rc, out, err = self._spawn(full)
        return CommandResult(command=command, argv=full, returncode=rc, stdout=out, stderr=err)

    def read_log(self, path: str, *, lines: int = 200, grep: str | None = None) -> str:
        if not self.allowlist.is_log_path_allowed(path):
            raise LogPathNotAllowed(f"log path {path!r} is not in the allowlist")
        if not os.path.isfile(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.readlines()
        except PermissionError:
            raise LogPathNotAllowed(f"permission denied reading {path!r}")
        if grep:
            content = [ln for ln in content if grep in ln]
        return "".join(content[-lines:])

    def _spawn(self, argv: list[str]) -> tuple[int, str, str]:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=self.timeout, check=False
        )
        return proc.returncode, proc.stdout, proc.stderr
