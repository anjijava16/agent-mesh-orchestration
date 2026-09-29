"""The A2A client side.

Delegating is not calling. You get back a task with a state, and the states you
have to handle are more interesting than success and failure:

    completed        the artifact is there
    input-required   it stopped and wants something -- forward, do not retry
    failed           terminal; a retry is a NEW task in the same contextId
"""

from __future__ import annotations

import itertools
from typing import Any

import httpx

from refundry import store
from refundry.a2a.types import DataPart, Message, TextPart, artifact_data
from refundry.config import settings


class A2AError(RuntimeError):
    pass


def _say(task: dict) -> str:
    """state + whatever the agent said, for the audit line."""
    msg = task["status"].get("message") or {}
    head = " ".join(p.get("text", "") for p in msg.get("parts", [])
                    if p.get("kind") == "text").strip()
    return f"{task['status']['state']}: {head}"


class A2AClient:
    """A client for one remote agent."""

    def __init__(self, url: str, *, name: str = "", caller: str = "",
                 timeout: float | None = None):
        self.url = url
        self.name = name or url
        self.caller = caller
        self.timeout = timeout or settings.a2a_timeout
        self._ids = itertools.count(1)

    async def _rpc(self, method: str, params: dict) -> Any:
        body = {"jsonrpc": "2.0", "id": next(self._ids), "method": method,
                "params": params}
        headers = {
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
            # Without this header a compatibility-mode server treats you as 0.3.
            "A2A-Version": "1.0",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            resp = await http.post(self.url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        if data.get("error"):
            raise A2AError(f"{self.name}: {data['error'].get('message')}")
        return data.get("result")

    async def fetch_card(self) -> dict:
        card_url = self.url.replace("/a2a/jsonrpc", "/.well-known/agent-card.json")
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            resp = await http.get(card_url)
            resp.raise_for_status()
            return resp.json()

    async def send(self, payload: dict, *, context_id: str, text: str = "",
                   task_id: str = "") -> dict:
        """Delegate, and return the task. Never raises on input-required --
        that is a legitimate outcome, not an error."""
        parts = [DataPart(payload)]
        if text:
            parts.insert(0, TextPart(text))
        message = Message("user", parts, task_id=task_id, context_id=context_id)
        store.audit(self.caller or "client", "a2a.send", target=self.name,
                    context_id=context_id, detail=text or payload.get("skill", ""))
        task = await self._rpc("SendMessage", {"message": message})
        store.audit(self.caller or "client", "a2a.reply", target=self.name,
                    context_id=context_id,
                    detail=_say(task)[:300])
        return task

    async def get(self, task_id: str) -> dict:
        return await self._rpc("GetTask", {"id": task_id})

    async def cancel(self, task_id: str) -> dict:
        return await self._rpc("CancelTask", {"id": task_id})

    @staticmethod
    def result(task: dict, artifact: str) -> dict:
        return artifact_data(task, artifact)

    @staticmethod
    def state(task: dict) -> str:
        return task["status"]["state"]

    @staticmethod
    def say(task: dict) -> str:
        msg = task["status"].get("message") or {}
        return " ".join(p.get("text", "") for p in msg.get("parts", [])
                        if p.get("kind") == "text").strip()
