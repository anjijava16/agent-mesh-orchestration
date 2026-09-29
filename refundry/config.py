"""Every knob in one place, read from the environment once."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:  # pragma: no cover - dotenv is a convenience, not a need
    pass

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SEED = DATA / "seed"

HOST = os.getenv("REFUNDRY_HOST", "127.0.0.1")

# One port per process. The gateway is the only one a human talks to.
PORTS = {
    "gateway": 8080,
    "arbiter": 8000,
    "tracer": 8001,
    "witness": 8002,
    "statute": 8003,
    "sentry": 8004,
    "treasury": 8005,
    "counterparty": 8006,
    "orders": 8201,
    "catalog": 8202,
    "documents": 8203,
    "policy_kb": 8204,
    "risk": 8205,
    "case_mgmt": 8206,
    "payments": 8207,
}


def base_url(name: str) -> str:
    return f"http://{HOST}:{PORTS[name]}"


def a2a_url(name: str) -> str:
    return f"{base_url(name)}/a2a/jsonrpc"


def mcp_url(name: str) -> str:
    return f"{base_url(name)}/mcp"


def card_url(name: str) -> str:
    return f"{base_url(name)}/.well-known/agent-card.json"


@dataclass(frozen=True)
class Settings:
    # "deterministic" runs the whole network with no model at all.
    # "llm" additionally asks a model for judgement and prose, degrading back
    # to deterministic on any failure.
    reasoning: str = os.getenv("REFUNDRY_REASONING", "deterministic")

    # Jev. "auto" uses the real client when TYPESAFE_API_KEY is set and the SDK
    # is importable, and the local System One stand-in otherwise.
    jev_mode: str = os.getenv("REFUNDRY_JEV", "auto")
    typesafe_api_key: str = os.getenv("TYPESAFE_API_KEY", "")
    jev_model: str = os.getenv("REFUNDRY_JEV_MODEL", "jev-latest")

    # Business rules that the deck quotes.
    auto_approval_limit: float = float(os.getenv("REFUNDRY_AUTO_APPROVAL", "1000.00"))
    claim_window_days: int = int(os.getenv("REFUNDRY_CLAIM_WINDOW_DAYS", "30"))

    # Jev's confidence gate. Below this we ask a person even when the amount rule
    # would have let it through.
    confidence_floor: float = float(os.getenv("REFUNDRY_CONFIDENCE_FLOOR", "0.62"))

    # Networking
    a2a_timeout: float = float(os.getenv("REFUNDRY_A2A_TIMEOUT", "30"))
    external_timeout: float = float(os.getenv("REFUNDRY_EXTERNAL_TIMEOUT", "60"))
    mcp_timeout: float = float(os.getenv("REFUNDRY_MCP_TIMEOUT", "15"))

    db_path: Path = field(default_factory=lambda: Path(
        os.getenv("REFUNDRY_DB", str(DATA / "refundry.db"))))

    @property
    def deterministic(self) -> bool:
        return self.reasoning != "llm"


settings = Settings()
