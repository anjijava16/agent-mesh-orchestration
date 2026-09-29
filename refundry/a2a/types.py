"""A2A wire types.

A task is not a return value. It has an identity, a lifecycle, and the ability
to stop and wait for a human — which is the whole difference between this and
an HTTP call that happens to take a while.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Literal

TaskState = Literal[
    "submitted", "working", "input-required",
    "completed", "failed", "canceled", "rejected",
]

TERMINAL: set[str] = {"completed", "failed", "canceled", "rejected"}

PROTOCOL_VERSION = "1.0"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def TextPart(text: str) -> dict:
    return {"kind": "text", "text": text}


def DataPart(data: Any) -> dict:
    return {"kind": "data", "data": data}


def Message(role: str, parts: list[dict], *, task_id: str = "",
            context_id: str = "") -> dict:
    msg = {"role": role, "parts": parts, "messageId": str(uuid.uuid4()),
           "kind": "message"}
    if task_id:
        msg["taskId"] = task_id
    if context_id:
        msg["contextId"] = context_id
    return msg


def Artifact(name: str, parts: list[dict], *, description: str = "") -> dict:
    return {"artifactId": str(uuid.uuid4()), "name": name, "parts": parts,
            "description": description}


def new_task(context_id: str, agent: str, *, task_id: str = "") -> dict:
    return {
        "id": task_id or str(uuid.uuid4()),
        "contextId": context_id,
        "agent": agent,
        "kind": "task",
        "status": {"state": "submitted", "timestamp": _now()},
        "artifacts": [],
        "history": [],
    }


def set_state(task: dict, state: TaskState, *, text: str = "") -> dict:
    task["status"] = {"state": state, "timestamp": _now()}
    if text:
        task["status"]["message"] = Message(
            "agent", [TextPart(text)],
            task_id=task["id"], context_id=task["contextId"])
    return task


def data_of(message: dict | None) -> dict:
    """The first DataPart of a message, which is where the machine-readable
    half of every exchange lives."""
    if not message:
        return {}
    for part in message.get("parts", []):
        if part.get("kind") == "data":
            return part.get("data") or {}
    return {}


def text_of(message: dict | None) -> str:
    if not message:
        return ""
    return " ".join(p.get("text", "") for p in message.get("parts", [])
                    if p.get("kind") == "text").strip()


def artifact_data(task: dict, name: str) -> dict:
    """The most recent artifact with this name.

    A task accumulates artifacts across a pause and a resume -- Treasury
    publishes `draft` before it stops and `result` after it restarts, and the
    Arbiter republishes `case` each time. Reading the FIRST match would hand
    back the pre-pause state, so this reads the last.
    """
    for art in reversed(task.get("artifacts", [])):
        if art.get("name") == name:
            for part in art.get("parts", []):
                if part.get("kind") == "data":
                    return part.get("data") or {}
    return {}
