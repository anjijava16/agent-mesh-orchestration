"""Request-scoped dependencies.

Authentication is a seam, not an implementation. `current_user` reads a header
that your gateway (or the JWT verifier you drop in here) is expected to set.
Everything downstream takes a user id, so swapping in real auth touches this
file and nothing else.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

DbSession = Annotated[AsyncSession, Depends(get_session)]


async def current_user(
    request: Request,
    x_user_id: Annotated[str | None, Header()] = None,
) -> str:
    # Replace with JWT verification / OIDC introspection for production.
    # The contract downstream is only "a stable string identifying the caller".
    user = x_user_id or getattr(request.state, "user_id", None) or "demo-user"
    request.state.user_id = user
    return user


CurrentUser = Annotated[str, Depends(current_user)]


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


RequestId = Annotated[str, Depends(request_id)]
