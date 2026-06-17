from __future__ import annotations

from orchestrator.alerts.models import ProposedAction, Tier
from orchestrator.response.policy import Policy


def test_default_policy_tiers():
    p = Policy.load()
    assert p.tier_for("unban_ip") == Tier.AUTO
    assert p.tier_for("restart_service") == Tier.AUTO
    assert p.tier_for("disable_domain") == Tier.APPROVAL
    assert p.tier_for("delete_data") == Tier.FORBIDDEN


def test_unknown_action_defaults_to_approval():
    p = Policy.load()
    assert p.tier_for(ProposedAction(name="something_new")) == Tier.APPROVAL
