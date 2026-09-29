"""The Agent Card.

It is the only artefact a caller needs, and the only one you can be held to.
Treat it like a published API: skills are the menu, the version is a contract,
and the limits of the agent belong in the card rather than in a wiki.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from refundry.a2a.types import PROTOCOL_VERSION


@dataclass
class Skill:
    id: str
    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    input_modes: list[str] = field(default_factory=lambda: ["application/json"])
    output_modes: list[str] = field(default_factory=lambda: ["application/json"])

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "description": self.description,
                "tags": self.tags, "inputModes": self.input_modes,
                "outputModes": self.output_modes}


@dataclass
class AgentCard:
    name: str
    description: str
    url: str
    skills: list[Skill]
    version: str = "1.0.0"
    organization: str = "Northwind Market"
    streaming: bool = True
    push_notifications: bool = True

    def to_dict(self) -> dict:
        card = {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "provider": {"organization": self.organization},
            "supportedInterfaces": [{
                "url": self.url,
                "protocolBinding": "JSONRPC",
                "protocolVersion": PROTOCOL_VERSION,
            }],
            "capabilities": {"streaming": self.streaming,
                             "pushNotifications": self.push_notifications},
            "skills": [s.to_dict() for s in self.skills],
            "securitySchemes": {"oauth2": {"scopes": ["agent.invoke"]}},
            "defaultInputModes": ["application/json"],
            "defaultOutputModes": ["application/json"],
        }
        # A signed card proves it came from the domain it names. This is a
        # stand-in for a real EdDSA signature over the canonical form -- enough
        # to show where verification belongs, not enough to rely on.
        digest = hashlib.sha256(
            f"{self.name}:{self.version}:{self.url}".encode()).hexdigest()
        card["signature"] = {"alg": "demo-sha256", "kid": "nwk-2026-03",
                             "sig": digest}
        return card


def build_card(name: str, description: str, url: str, skills: list[Skill],
               **kwargs) -> AgentCard:
    return AgentCard(name=name, description=description, url=url,
                     skills=skills, **kwargs)
