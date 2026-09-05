from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.db.repositories import AuditRepository
from app.schemas.common import AuditOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=dict)
async def search_audit(
    session: DbSession,
    user: CurrentUser,
    action: str | None = None,
    resource_type: str | None = None,
    outcome: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    scope: str = Query("self", pattern="^(self|all)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """Audit trail. `scope=all` is where an authorisation check belongs once you
    wire real auth - the query itself is already scoped by user by default."""
    rows, total = await AuditRepository(session).search(
        user_id=None if scope == "all" else user,
        action=action,
        resource_type=resource_type,
        outcome=outcome,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return {"items": [AuditOut.model_validate(r) for r in rows], "total": total,
            "limit": limit, "offset": offset}


@router.get("/actions")
async def known_actions() -> dict:
    return {
        "actions": [
            "chat.turn", "settings.update", "file.upload", "file.delete",
            "memory.forget", "conversation.delete",
        ]
    }
