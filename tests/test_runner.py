"""The runner is the security choke point — these tests are load-bearing."""

from __future__ import annotations

import pytest

from mcp_server.exec.runner import Allowlist, CommandNotAllowed, CommandRunner, LogPathNotAllowed


class ScriptedRunner(CommandRunner):
    def __init__(self, **kw):
        super().__init__(use_sudo=False, **kw)
        self.spawned: list[list[str]] = []

    def _spawn(self, argv):
        self.spawned.append(argv)
        return 0, "active", ""


def test_unknown_command_rejected():
    r = ScriptedRunner()
    with pytest.raises(CommandNotAllowed):
        r.run("rm_rf_everything")


def test_param_pattern_blocks_injection():
    r = ScriptedRunner()
    # a shell-injection-looking IP fails the strict pattern
    with pytest.raises(CommandNotAllowed):
        r.run("fail2ban_unban", ip="1.2.3.4; rm -rf /", jail="ssh")


def test_valid_command_builds_argv():
    r = ScriptedRunner()
    res = r.run("service_status", unit="nginx")
    assert res.argv == ["systemctl", "is-active", "nginx"]
    assert res.ok


def test_sudo_prefix_applied_when_enabled():
    r = CommandRunner(use_sudo=True)
    argv, needs_sudo = r.allowlist.build_argv("fail2ban_status", {})
    assert needs_sudo is True


def test_log_path_traversal_blocked():
    al = Allowlist.load()
    assert al.is_log_path_allowed("/var/log/nginx/error.log")
    assert not al.is_log_path_allowed("/etc/shadow")
    assert not al.is_log_path_allowed("/var/log/nginx/../../etc/shadow")


def test_read_log_outside_allowlist_raises(tmp_path):
    r = ScriptedRunner()
    secret = tmp_path / "secret"
    secret.write_text("nope")
    with pytest.raises(LogPathNotAllowed):
        r.read_log(str(secret))
