from __future__ import annotations

from fastapi import APIRouter

from app.agents.definitions import roster
from app.agents.registry import available_frameworks
from app.api.deps import CurrentUser, DbSession, RequestId
from app.config import settings
from app.db.repositories import AuditRepository, SettingsRepository
from app.llm.registry import catalogue
from app.schemas.common import SettingsIn, SettingsOut

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
async def get_settings_for_user(session: DbSession, user: CurrentUser) -> SettingsOut:
    stored = await SettingsRepository(session).get(user)
    if stored:
        return SettingsOut.model_validate(stored)
    # Fall back to the config.py defaults so the UI always has something to render.
    return SettingsOut(
        user_id=user,
        framework=settings.agent.framework.value,
        provider=settings.agent.provider.value,
        model=settings.agent.model,
        temperature=settings.agent.temperature,
        max_tokens=settings.agent.max_tokens,
        enabled_agents=[a["name"] for a in roster()],
        use_long_term_memory=settings.agent.enable_long_term_memory,
        use_hybrid_search=True,
        extra={},
    )


@router.put("", response_model=SettingsOut)
async def update_settings(
    body: SettingsIn, session: DbSession, user: CurrentUser, req_id: RequestId
) -> SettingsOut:
    payload = body.model_dump(exclude_unset=True)
    for key in ("framework", "provider"):
        if payload.get(key) is not None:
            payload[key] = payload[key].value if hasattr(payload[key], "value") else payload[key]

    saved = await SettingsRepository(session).upsert(
        user,
        framework=payload.get("framework") or settings.agent.framework.value,
        provider=payload.get("provider") or settings.agent.provider.value,
        model=payload.get("model") or settings.agent.model,
        temperature=payload.get("temperature"),
        max_tokens=payload.get("max_tokens"),
        enabled_agents=payload.get("enabled_agents"),
        use_long_term_memory=payload.get("use_long_term_memory"),
        use_hybrid_search=payload.get("use_hybrid_search"),
        extra=payload.get("extra"),
    )
    await AuditRepository(session).record(
        action="settings.update", resource_type="user_settings", resource_id=user,
        user_id=user, request_id=req_id, detail=payload,
    )
    return SettingsOut.model_validate(saved)


@router.get("/options")
async def options() -> dict:
    """Everything the settings panel needs, in one call."""
    return {
        "frameworks": available_frameworks(),
        "agents": roster(),
        **catalogue(),
        "defaults": {
            "framework": settings.agent.framework.value,
            "provider": settings.agent.provider.value,
            "model": settings.agent.model,
            "temperature": settings.agent.temperature,
            "max_tokens": settings.agent.max_tokens,
        },
    }
