"""Framework selection.

`config.py` sets the default. A request body or a stored user setting can
override it. Runtimes are cached because building one is cheap but not free,
and because ADK's session service holds a connection pool.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import AgentRuntime
from app.agents.frameworks.adk_runtime import GoogleADKRuntime
from app.agents.frameworks.adk_workflow_runtime import GoogleADKWorkflowRuntime
from app.agents.frameworks.claude_sdk_runtime import ClaudeAgentSDKRuntime
from app.agents.frameworks.deepagents_runtime import DeepAgentsRuntime
from app.agents.frameworks.langgraph_runtime import LangGraphRuntime
from app.agents.frameworks.ms_agent_runtime import MSAgentFrameworkRuntime
from app.agents.frameworks.strands_runtime import StrandsAgentsRuntime
from app.config import AgentFramework, settings
from app.core.errors import ValidationError

_RUNTIME_CLASSES: dict[AgentFramework, type[AgentRuntime]] = {
    AgentFramework.GOOGLE_ADK: GoogleADKRuntime,
    AgentFramework.GOOGLE_ADK_WORKFLOW: GoogleADKWorkflowRuntime,
    AgentFramework.LANGGRAPH: LangGraphRuntime,
    AgentFramework.DEEPAGENTS: DeepAgentsRuntime,
    AgentFramework.CLAUDE_AGENT_SDK: ClaudeAgentSDKRuntime,
    AgentFramework.MS_AGENT_FRAMEWORK: MSAgentFrameworkRuntime,
    AgentFramework.STRANDS_AGENTS: StrandsAgentsRuntime,
}

_cache: dict[AgentFramework, AgentRuntime] = {}


def get_runtime(framework: AgentFramework | str | None = None) -> AgentRuntime:
    if framework is None:
        framework = settings.agent.framework
    if isinstance(framework, str):
        try:
            framework = AgentFramework(framework)
        except ValueError as exc:
            raise ValidationError(
                f"Unknown framework '{framework}'",
                details={"supported": [f.value for f in AgentFramework]},
            ) from exc
    if framework not in _cache:
        _cache[framework] = _RUNTIME_CLASSES[framework]()
    return _cache[framework]


def available_frameworks() -> list[dict[str, Any]]:
    out = []
    for framework, cls in _RUNTIME_CLASSES.items():
        installed, reason = _probe(framework)
        out.append(
            {
                "id": framework.value,
                "display_name": cls.display_name,
                "description": cls.description,
                "installed": installed,
                "note": reason,
                "is_default": framework == settings.agent.framework,
            }
        )
    return out


def _probe(framework: AgentFramework) -> tuple[bool, str]:
    import importlib.util

    module = {
        AgentFramework.GOOGLE_ADK: "google.adk",
        AgentFramework.GOOGLE_ADK_WORKFLOW: "google.adk",
        AgentFramework.LANGGRAPH: "langgraph",
        AgentFramework.DEEPAGENTS: "deepagents",
        AgentFramework.CLAUDE_AGENT_SDK: "claude_agent_sdk",
        AgentFramework.MS_AGENT_FRAMEWORK: "agent_framework",
        AgentFramework.STRANDS_AGENTS: "strands",
    }[framework]
    try:
        found = importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        found = False
    if not found:
        return False, f"Python package '{module}' is not installed in this image."
    if framework is AgentFramework.CLAUDE_AGENT_SDK and not settings.anthropic_api_key:
        return True, "Installed, but ANTHROPIC_API_KEY is unset."
    return True, ""
