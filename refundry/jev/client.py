"""System One: the fast, typed decision layer.

Most of what a refund network pays a frontier model for is not reasoning. Sort
the model calls in one case by what they *return* and the majority come back as
a label from a set we wrote down in advance -- routing, triage, gating. Those
do not need a model that can write.

TypeSafe AI's **Jev** is the first model built for exactly that shape: a
frontier-intelligence function call, unstructured state in, typed probabilistic
decisions out, with calibrated confidence and no string generation at all.

    Published vendor figures (typesafe.ai, September 2026), not verified here:
      70-500 ms end to end, against 3-329 s for a frontier LLM
      $0.042 / MTok input, output free
      0% schema violations -- the label set is declared up front
      trained with RLCD for calibrated probabilities
      ~68% on TypeSafe's own four-workflow benchmark

Jev is in early access. This module therefore has two backends behind one
interface:

  "sdk"    the real `typesafe_sdk`, used when TYPESAFE_API_KEY is set and the
           package imports
  "local"  a deterministic System One *stand-in* that implements the same three
           primitives offline, so the project runs with no key and no network

The stand-in is NOT Jev and makes no claim to its accuracy. It is a lexical
scorer with a softmax over the declared labels. It exists so the architecture --
where the decisions sit, what they return, how the confidence gate behaves --
can be exercised end to end. `response.backend` always says which one ran.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any

from refundry.config import settings

# --------------------------------------------------------------------------
# The three primitives, mirroring the TypeSafe SDK
# --------------------------------------------------------------------------


@dataclass
class Choice:
    """Pick exactly one label. `criteria` maps label -> what it means."""
    instructions: str
    criteria: dict[str, str]


@dataclass
class Score:
    """An ordered level. `criteria` is the ladder, lowest first."""
    instructions: str
    criteria: list[str]


@dataclass
class Noul:
    """A single probability in [0, 1]. No label, no prose."""
    instructions: str


@dataclass
class ChoiceResult:
    choice: str
    confidence: float
    probabilities: dict[str, float]


@dataclass
class ScoreResult:
    score: float
    confidence: float
    probabilities: dict[int, float]
    legend: list[str]


@dataclass
class NoulResult:
    noul: float


@dataclass
class SystemOneResponse:
    choices: dict[str, ChoiceResult] = field(default_factory=dict)
    scores: dict[str, ScoreResult] = field(default_factory=dict)
    nouls: dict[str, NoulResult] = field(default_factory=dict)
    backend: str = "local"
    latency_ms: float = 0.0

    def summary(self) -> dict:
        return {
            "backend": self.backend,
            "latency_ms": round(self.latency_ms, 1),
            "choices": {k: {"choice": v.choice, "confidence": round(v.confidence, 3)}
                        for k, v in self.choices.items()},
            "scores": {k: round(v.score, 2) for k, v in self.scores.items()},
            "nouls": {k: round(v.noul, 3) for k, v in self.nouls.items()},
        }


# --------------------------------------------------------------------------
# The local stand-in
# --------------------------------------------------------------------------

_WORD = re.compile(r"[a-z0-9$][a-z0-9_$.-]*")
_STOP = {
    "the", "a", "an", "is", "it", "to", "of", "and", "or", "in", "on", "for",
    "with", "this", "that", "was", "are", "be", "been", "has", "have", "had",
    "not", "but", "as", "at", "by", "from", "we", "i", "my", "me", "you",
    "they", "them", "its", "his", "her", "their", "any", "all", "if", "so",
}


def _tokens(text: str) -> list[str]:
    # Trailing punctuation is stripped -- otherwise "cracked." never matches
    # "cracked" -- but interior dots and dashes are kept, so "mkt-014" and
    # "1284.00" survive as single tokens.
    out = []
    for raw in _WORD.findall(text.lower()):
        tok = raw.strip(".-_")
        if tok and tok not in _STOP and len(tok) > 1:
            out.append(tok)
    return out


def _flatten(state: Any, depth: int = 0) -> str:
    """Jev accepts strings, JSON objects and arrays of text. So does this."""
    if depth > 6:
        return ""
    if state is None:
        return ""
    if isinstance(state, str):
        return state
    if isinstance(state, (int, float, bool)):
        return str(state)
    if isinstance(state, dict):
        return " ".join(f"{k} {_flatten(v, depth + 1)}" for k, v in state.items())
    if isinstance(state, (list, tuple)):
        return " ".join(_flatten(v, depth + 1) for v in state)
    if hasattr(state, "model_dump"):
        return _flatten(state.model_dump(), depth + 1)
    return str(state)


def _affinity(state_tokens: list[str], text: str) -> float:
    """Overlap between the state and one label's description, length-normalised."""
    want = _tokens(text)
    if not want:
        return 0.0
    counts = {}
    for t in state_tokens:
        counts[t] = counts.get(t, 0) + 1
    hits = 0.0
    for t in set(want):
        if t in counts:
            # Diminishing returns on repetition, so one loud word cannot win alone.
            hits += 1.0 + 0.35 * math.log1p(counts[t] - 1)
    return hits / math.sqrt(len(set(want)))


def _softmax(raw: dict[str, float], temperature: float = 0.55) -> dict[str, float]:
    if not raw:
        return {}
    top = max(raw.values())
    exps = {k: math.exp((v - top) / temperature) for k, v in raw.items()}
    total = sum(exps.values()) or 1.0
    return {k: v / total for k, v in exps.items()}


def _confidence(probs: dict[str, float]) -> float:
    """Margin between the top two. A two-horse race is not confident, whatever
    the top probability says."""
    if not probs:
        return 0.0
    ranked = sorted(probs.values(), reverse=True)
    if len(ranked) == 1:
        return ranked[0]
    return round(min(1.0, ranked[0] - ranked[1] + ranked[0] * 0.25), 4)


class _LocalSystemOne:
    """A deterministic System One stand-in. Same shape, not the same model."""

    name = "local"

    def system_one(self, state: Any, questions: dict[str, Any]) -> SystemOneResponse:
        started = time.perf_counter()
        blob = _flatten(state)
        toks = _tokens(blob)
        out = SystemOneResponse(backend="local")

        for key, q in questions.items():
            if isinstance(q, Choice):
                raw = {
                    label: _affinity(toks, f"{label} {desc}")
                    for label, desc in q.criteria.items()
                }
                # The question itself nudges nothing; only the criteria do. If
                # nothing matched, fall back to a flat distribution rather than
                # inventing a winner.
                if max(raw.values(), default=0.0) == 0.0:
                    n = len(q.criteria) or 1
                    probs = {k: 1.0 / n for k in q.criteria}
                else:
                    probs = _softmax(raw)
                pick = max(probs, key=probs.get)
                out.choices[key] = ChoiceResult(
                    choice=pick,
                    confidence=_confidence(probs),
                    probabilities={k: round(v, 4) for k, v in probs.items()},
                )

            elif isinstance(q, Score):
                raw = {str(i): _affinity(toks, level)
                       for i, level in enumerate(q.criteria)}
                probs = (_softmax(raw) if max(raw.values(), default=0.0) > 0
                         else {k: 1.0 / len(raw) for k in raw})
                expected = sum(int(i) * p for i, p in probs.items())
                out.scores[key] = ScoreResult(
                    score=round(expected, 4),
                    confidence=_confidence(probs),
                    probabilities={int(i): round(p, 4) for i, p in probs.items()},
                    legend=list(q.criteria),
                )

            elif isinstance(q, Noul):
                hit = _affinity(toks, q.instructions)
                out.nouls[key] = NoulResult(
                    noul=round(1.0 / (1.0 + math.exp(-(hit - 1.1) * 1.6)), 4))

        out.latency_ms = (time.perf_counter() - started) * 1000
        return out


class _SDKSystemOne:
    """The real thing, when a key and the package are both present."""

    name = "sdk"

    def __init__(self, client: Any, model: str):
        self._client = client
        self._model = model

    def system_one(self, state: Any, questions: dict[str, Any]) -> SystemOneResponse:
        import typesafe_sdk as ts  # noqa: F401  (imported for its types)

        started = time.perf_counter()
        native: dict[str, Any] = {}
        for key, q in questions.items():
            if isinstance(q, Choice):
                native[key] = ts.Choice(instructions=q.instructions,
                                        criteria=q.criteria)
            elif isinstance(q, Score):
                native[key] = ts.Score(instructions=q.instructions,
                                       criteria=q.criteria)
            elif isinstance(q, Noul):
                native[key] = ts.Noul(instructions=q.instructions)

        raw = self._client.system_one(_flatten(state), native)
        out = SystemOneResponse(backend="sdk")
        for key in questions:
            if key in getattr(raw, "choices", {}):
                r = raw.choices[key]
                out.choices[key] = ChoiceResult(r.choice, float(r.confidence),
                                                dict(r.probabilities))
            elif key in getattr(raw, "scores", {}):
                r = raw.scores[key]
                out.scores[key] = ScoreResult(float(r.score), float(r.confidence),
                                              dict(r.probabilities), list(r.legend))
            elif key in getattr(raw, "nouls", {}):
                out.nouls[key] = NoulResult(float(raw.nouls[key].noul))
        out.latency_ms = (time.perf_counter() - started) * 1000
        return out


# --------------------------------------------------------------------------
# The facade the rest of the project uses
# --------------------------------------------------------------------------


class JevClient:
    def __init__(self, mode: str | None = None):
        self.mode = mode or settings.jev_mode
        self._impl = self._build()

    def _build(self):
        if self.mode == "local":
            return _LocalSystemOne()
        if self.mode in ("auto", "sdk"):
            if settings.typesafe_api_key:
                try:
                    from typesafe_sdk import TypeSafeClient

                    return _SDKSystemOne(TypeSafeClient(), settings.jev_model)
                except Exception as exc:
                    if self.mode == "sdk":
                        raise RuntimeError(
                            "REFUNDRY_JEV=sdk but the client would not start: "
                            f"{exc}") from exc
            elif self.mode == "sdk":
                raise RuntimeError("REFUNDRY_JEV=sdk but TYPESAFE_API_KEY is unset")
        return _LocalSystemOne()

    @property
    def backend(self) -> str:
        return self._impl.name

    def system_one(self, state: Any, questions: dict[str, Any]) -> SystemOneResponse:
        return self._impl.system_one(state, questions)

    # -- convenience -------------------------------------------------------

    def choose(self, state: Any, instructions: str,
               criteria: dict[str, str]) -> ChoiceResult:
        return self.system_one(state, {"_": Choice(instructions, criteria)}).choices["_"]

    def likely(self, state: Any, instructions: str) -> float:
        return self.system_one(state, {"_": Noul(instructions)}).nouls["_"].noul


jev = JevClient()
