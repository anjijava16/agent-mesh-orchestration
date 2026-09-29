"""The Arbiter's view of its peers: a client per agent, and nothing else.

It holds cards and URLs. It does not import a single line of any specialist's
code, which is what makes the boundary real rather than decorative.
"""

from __future__ import annotations

from refundry.a2a import A2AClient
from refundry.agents.registry import SKILLS
from refundry.config import a2a_url, settings


def client_for(agent: str) -> A2AClient:
    # The hop that leaves the building gets a longer deadline, because we do not
    # control what is on the other end.
    timeout = (settings.external_timeout if agent == "counterparty"
               else settings.a2a_timeout)
    return A2AClient(a2a_url(agent), name=agent, caller="arbiter", timeout=timeout)


def skill_of(agent: str) -> str:
    return SKILLS[agent]
