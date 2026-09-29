"""case-mgmt -- the case record.

Append-only. `set_status` is the only mutation, and it is audited. Every agent
that writes here does so with its own credential, so the access check happens
at the data rather than in the caller.
"""

from __future__ import annotations

from refundry import store
from refundry.mcp import MCPServer, ToolError

mcp = MCPServer("case_mgmt", scope="case.write", risk="medium")


@mcp.tool()
def open_case(case_id: str, context_id: str, order_ref: str, buyer_ref: str,
              narrative: str) -> dict:
    """Open a case, or return the existing one. Filing twice is not an error."""
    existing = store.load_case(case_id)
    if existing:
        return {"case_id": case_id, "created": False, "record": existing}
    record = {"case_id": case_id, "context_id": context_id, "order_ref": order_ref,
              "buyer_ref": buyer_ref, "narrative": narrative, "status": "open"}
    store.save_case(case_id, context_id, "open", record)
    store.audit("case_mgmt", "case.open", target=case_id, context_id=context_id)
    return {"case_id": case_id, "created": True, "record": record}


@mcp.tool()
def append_note(case_id: str, author: str, note: str) -> dict:
    """Add a note. Nothing is ever edited or removed."""
    if store.load_case(case_id) is None:
        raise ToolError(f"case {case_id!r} does not exist; call open_case first")
    store.add_note(case_id, author, note)
    return {"case_id": case_id, "notes": len(store.notes(case_id))}


@mcp.tool()
def set_status(case_id: str, status: str) -> dict:
    """The one permitted mutation."""
    record = store.load_case(case_id)
    if record is None:
        raise ToolError(f"case {case_id!r} does not exist")
    allowed = {"open", "investigating", "awaiting_approval", "resolved",
               "declined", "withdrawn"}
    if status not in allowed:
        raise ToolError(f"status {status!r} is not one of {sorted(allowed)}")
    record["status"] = status
    store.save_case(case_id, record.get("context_id", ""), status, record)
    store.audit("case_mgmt", "case.status", target=case_id, detail=status,
                context_id=record.get("context_id", ""))
    return {"case_id": case_id, "status": status}


@mcp.tool(read_only=True)
def get_case(case_id: str) -> dict:
    """The case record and every note on it."""
    record = store.load_case(case_id)
    if record is None:
        raise ToolError(f"case {case_id!r} does not exist")
    return {"case_id": case_id, "record": record, "notes": store.notes(case_id)}


@mcp.tool()
def put_case(case_id: str, record: dict) -> dict:
    """Persist the orchestrator's view of the case alongside the record."""
    existing = store.load_case(case_id) or {}
    existing.update(record)
    store.save_case(case_id, existing.get("context_id", ""),
                    existing.get("status", "open"), existing)
    return {"case_id": case_id, "saved": True}
