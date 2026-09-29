"""The A2A server side: an executor, and the task lifecycle written out in full.

One detail costs an hour if you meet it unprepared: **the first thing an
executor publishes must be the Task object itself.** A status update that
arrives before it is rejected by the client. That is what `ctx.accept()` is for,
and the server enforces it rather than trusting each executor to remember.

Method names follow A2A 1.0 -- SendMessage, GetTask, CancelTask. Compatibility
mode also accepts the pre-1.0 spellings, and reproduces the real trap: with
compatibility on, a request that does not send `A2A-Version: 1.0` is treated
as 0.3.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from refundry import store
from refundry.a2a.card import AgentCard
from refundry.a2a.types import (
    PROTOCOL_VERSION,
    TERMINAL,
    Artifact,
    DataPart,
    TextPart,
    data_of,
    new_task,
    set_state,
    text_of,
)

METHOD_ALIASES = {
    "message/send": "SendMessage",
    "message/stream": "SendStreamingMessage",
    "tasks/get": "GetTask",
    "tasks/cancel": "CancelTask",
}


@dataclass
class RequestContext:
    """What an executor is handed, and the only way it should mutate its task."""

    task: dict
    message: dict
    agent: str
    events: list[dict] = field(default_factory=list)
    _accepted: bool = False

    # -- what came in ------------------------------------------------------

    @property
    def data(self) -> dict:
        return data_of(self.message)

    @property
    def text(self) -> str:
        return text_of(self.message)

    @property
    def task_id(self) -> str:
        return self.task["id"]

    @property
    def context_id(self) -> str:
        return self.task["contextId"]

    @property
    def is_resume(self) -> bool:
        """True when this message arrived on a task that was already waiting."""
        return self.task["status"]["state"] == "input-required"

    # -- what goes out -----------------------------------------------------

    def accept(self) -> None:
        """Publish the Task object. Must happen before any status update."""
        if self._accepted:
            return
        self._accepted = True
        self.events.append({"kind": "task", "task": self.task})
        store.put_task(self.task)

    def _update(self, state: str, text: str = "", final: bool = False) -> None:
        if not self._accepted:
            self.accept()
        set_state(self.task, state, text=text)
        store.put_task(self.task)
        self.events.append({
            "kind": "status-update",
            "taskId": self.task["id"],
            "contextId": self.task["contextId"],
            "status": self.task["status"],
            "final": final,
        })
        store.audit(self.agent, "task.state", target=state,
                    context_id=self.context_id, detail=text)

    def working(self, text: str = "") -> None:
        self._update("working", text)

    def artifact(self, name: str, data: Any, *, text: str = "") -> None:
        """Publish a result. A DataPart for the machine, a TextPart for the
        person watching -- one message serves both."""
        if not self._accepted:
            self.accept()
        parts = [DataPart(data)]
        if text:
            parts.insert(0, TextPart(text))
        art = Artifact(name, parts)
        self.task["artifacts"].append(art)
        store.put_task(self.task)
        self.events.append({"kind": "artifact-update", "taskId": self.task["id"],
                            "contextId": self.task["contextId"], "artifact": art})

    def complete(self, text: str = "") -> None:
        self._update("completed", text, final=True)

    def fail(self, text: str) -> None:
        self._update("failed", text, final=True)

    def reject(self, text: str) -> None:
        self._update("rejected", text, final=True)

    def input_required(self, text: str) -> None:
        """Stop, and wait. The task is neither finished nor failed.

        No worker is blocked by this and no connection is held open. The task
        keeps its id, and a later message on that id resumes the work.
        """
        self._update("input-required", text, final=True)


class Executor:
    """Subclass this, implement `execute`, and the lifecycle is handled."""

    skill: str = ""

    async def execute(self, ctx: RequestContext) -> None:  # pragma: no cover
        raise NotImplementedError


class A2AServer:
    def __init__(self, card: AgentCard, executor: Executor, *,
                 agent_key: str, compatibility_mode: bool = True):
        self.card = card
        self.executor = executor
        self.agent_key = agent_key
        self.compatibility_mode = compatibility_mode

    # -- dispatch ----------------------------------------------------------

    async def _send_message(self, params: dict) -> dict:
        message = params.get("message") or {}
        context_id = message.get("contextId") or params.get("contextId") or "ctx-adhoc"
        task_id = message.get("taskId") or params.get("taskId")

        if task_id:
            task = store.get_task(task_id)
            if task is None:
                raise ValueError(f"no task {task_id!r}")
            if task["status"]["state"] in TERMINAL:
                # Terminal states are final. A retry is a new task in the same
                # contextId, so the trail keeps both.
                raise ValueError(
                    f"task {task_id} is {task['status']['state']}; "
                    "start a new task in the same contextId to retry")
        else:
            task = new_task(context_id, self.agent_key)

        task.setdefault("history", []).append(message)
        ctx = RequestContext(task=task, message=message, agent=self.agent_key)
        ctx.accept()

        store.audit(self.agent_key, "a2a.received", target=self.card.name,
                    context_id=context_id, detail=text_of(message)[:200])
        try:
            await self.executor.execute(ctx)
        except Exception as exc:  # an executor must never take the server down
            traceback.print_exc()
            ctx.fail(f"{type(exc).__name__}: {exc}")

        if task["status"]["state"] == "submitted":
            ctx.complete()
        return task

    async def handle(self, msg: dict, headers: dict) -> dict:
        mid = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params") or {}

        version = headers.get("a2a-version")
        if self.compatibility_mode and method in METHOD_ALIASES and version != "1.0":
            # The real trap, reproduced: without the header you are on 0.3.
            method = METHOD_ALIASES[method]

        def ok(result: Any) -> dict:
            return {"jsonrpc": "2.0", "id": mid, "result": result}

        def err(code: int, message: str) -> dict:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": code, "message": message}}

        try:
            if method in ("SendMessage", "SendStreamingMessage"):
                return ok(await self._send_message(params))
            if method == "GetTask":
                task = store.get_task(params.get("id", ""))
                return ok(task) if task else err(-32001, "task not found")
            if method == "CancelTask":
                task = store.get_task(params.get("id", ""))
                if not task:
                    return err(-32001, "task not found")
                if task["status"]["state"] in TERMINAL:
                    return err(-32002, f"task already {task['status']['state']}")
                set_state(task, "canceled", text="canceled by caller")
                store.put_task(task)
                return ok(task)
            if method == "GetAgentCard":
                return ok(self.card.to_dict())
        except ValueError as exc:
            return err(-32602, str(exc))
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            return err(-32603, f"{type(exc).__name__}: {exc}")

        return err(-32601, f"unknown method {msg.get('method')!r}")

    # -- app ---------------------------------------------------------------

    def app(self) -> FastAPI:
        api = FastAPI(title=f"A2A · {self.card.name}", version=self.card.version)
        router = APIRouter()

        @router.get("/.well-known/agent-card.json")
        async def agent_card():
            return self.card.to_dict()

        @router.post("/a2a/jsonrpc")
        async def jsonrpc(request: Request):
            body = await request.json()
            headers = {k.lower(): v for k, v in request.headers.items()}
            return JSONResponse(await self.handle(body, headers))

        @router.get("/health")
        async def health():
            return {"agent": self.card.name, "key": self.agent_key,
                    "protocol": PROTOCOL_VERSION,
                    "skills": [s.id for s in self.card.skills], "at": time.time()}

        api.include_router(router)
        return api
