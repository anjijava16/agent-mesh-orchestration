"""documents -- photographs, packing slips, transcripts.

Everything this server returns is **untrusted data**. It is never concatenated
into an instruction channel by any caller, and `parse_document` deliberately
quarantines any embedded instruction it finds rather than passing it upward as
text. The one process that can move money never calls this server at all.
"""

from __future__ import annotations

import re

from refundry.mcp import MCPServer, ToolError
from refundry.servers._seed import load

mcp = MCPServer("documents", scope="docs.read", risk="low")

# Crude on purpose. A real deployment uses a classifier; the architectural point
# is that the quarantine happens HERE, at the boundary, not in a prompt later.
INJECTION = re.compile(
    r"ignore (?:all )?previous|disregard (?:the )?above|system prompt|"
    r"you are now|pre-?approved|skip review|issue a \$?[\d,]+",
    re.I,
)


def _find(ref: str) -> dict:
    for d in load("documents")["documents"]:
        if d["ref"] == ref:
            return d
    raise ToolError(f"no document at {ref!r}; the case record lists the evidence refs")


def _quarantine(doc: dict) -> dict:
    embedded = doc.get("embedded_text", "")
    if embedded and INJECTION.search(embedded):
        return {
            "quarantined": True,
            "reason": "text embedded in the document addresses the reader as an agent",
            "sample": embedded[:120],
        }
    return {"quarantined": False}


@mcp.tool(read_only=True)
def parse_document(ref: str) -> dict:
    """Extract observations from one piece of evidence.

    Returns observations as DATA. Any embedded text that reads as an instruction
    is quarantined and reported, never returned as content.
    """
    doc = _find(ref)
    return {
        "ref": ref,
        "kind": doc["kind"],
        "legible": doc["legible"],
        "observations": doc["observations"],
        "injection_check": _quarantine(doc),
    }


@mcp.tool(read_only=True)
def parse_image(ref: str) -> dict:
    """Vision extraction over one photograph. Same contract as parse_document."""
    doc = _find(ref)
    if doc["kind"] != "image":
        raise ToolError(f"{ref!r} is a {doc['kind']}, not an image; use parse_document")
    return parse_document(ref)


@mcp.tool(read_only=True)
def redact(text: str) -> dict:
    """Strip anything that looks like a card number or an email before a model
    ever sees it. Redaction runs before the model, not after the log."""
    out = re.sub(r"\b(?:\d[ -]*?){13,19}\b", "[REDACTED-PAN]", text)
    out = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[REDACTED-EMAIL]", out)
    return {"text": out, "changed": out != text}
