"""OpenTelemetry + Arize Phoenix integration.

Initialises a TracerProvider that exports spans to Phoenix via OTLP gRPC.
When ``PHOENIX_ENABLED=true``, every FastAPI request, every LLM call across
all providers and frameworks, every tool invocation, and every multi-agent
handoff is recorded as a trace in Phoenix.

Instrumented frameworks:
  - FastAPI (HTTP requests)
  - httpx (outgoing HTTP: tool calls, search APIs)
  - OpenAI SDK (direct OpenAI calls)
  - Anthropic SDK (direct Anthropic calls)
  - LangChain / LangGraph (chains, agents, tools, graph nodes)
  - LiteLLM (provider-routed LLM calls)
  - Google GenAI SDK (Gemini calls)
  - Google ADK (ADK agent pipelines, workflows)
  - AWS Bedrock (boto3 bedrock-runtime calls)

Phoenix UI: http://localhost:6006/projects

Call ``setup_tracing()`` once at app startup (in main.py).
"""
from __future__ import annotations

from app.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_initialised = False


def setup_tracing() -> None:
    """Configure OpenTelemetry and instrument all frameworks.

    Safe to call multiple times — second call is a no-op.
    Does nothing if ``phoenix_enabled`` is False.
    """
    global _initialised
    if _initialised:
        return
    _initialised = True

    if not settings.phoenix_enabled:
        log.info("tracing_disabled", reason="PHOENIX_ENABLED is false")
        return

    endpoint = (
        settings.otel_exporter_otlp_endpoint
        or f"http://{settings.phoenix_host}:{settings.phoenix_grpc_port}"
    )
    project_name = settings.app_name

    log.info("tracing_init", endpoint=endpoint, project=project_name)

    try:
        _init_provider(endpoint, project_name)

        # HTTP layer
        _instrument("fastapi", _instrument_fastapi)
        _instrument("httpx", _instrument_httpx)

        # LLM provider SDKs
        _instrument("openai", _instrument_openai)
        _instrument("anthropic", _instrument_anthropic)
        _instrument("litellm", _instrument_litellm)
        _instrument("google_genai", _instrument_google_genai)

        # Agent frameworks
        _instrument("langchain", _instrument_langchain)
        _instrument("google_adk", _instrument_google_adk)
        _instrument("bedrock", _instrument_bedrock)

        log.info("tracing_ready", endpoint=endpoint, project=project_name)
    except Exception as exc:
        log.warning("tracing_init_failed", error=str(exc)[:300])

    # Opik tracing (separate from OTEL — Opik has its own SDK)
    if settings.opik_enabled:
        _setup_opik()


def _instrument(name: str, fn: callable) -> None:
    """Run an instrumentor function, logging success or skip."""
    try:
        fn()
        log.debug("instrumented", component=name)
    except Exception as exc:
        log.debug("instrument_skipped", component=name,
                  error=str(exc)[:200])


def _init_provider(endpoint: str, project_name: str) -> None:
    """Set up the global TracerProvider with OTLP gRPC exporter."""
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({
        "service.name": project_name,
        "service.version": "1.0.0",
        "deployment.environment": settings.environment,
    })

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


# ===================================================================
# HTTP layer
# ===================================================================

def _instrument_fastapi() -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    FastAPIInstrumentor.instrument()


def _instrument_httpx() -> None:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    HTTPXClientInstrumentor().instrument()


# ===================================================================
# LLM provider SDKs
# ===================================================================

def _instrument_openai() -> None:
    """OpenAI SDK — traces chat completions with prompt/response/tokens."""
    from openinference.instrumentation.openai import OpenAIInstrumentor
    OpenAIInstrumentor().instrument()


def _instrument_anthropic() -> None:
    """Anthropic SDK — traces messages API with prompt/response/tokens."""
    from openinference.instrumentation.anthropic import AnthropicInstrumentor
    AnthropicInstrumentor().instrument()


def _instrument_litellm() -> None:
    """LiteLLM — traces all provider-routed LLM calls."""
    from openinference.instrumentation.litellm import LiteLLMInstrumentor
    LiteLLMInstrumentor().instrument()


def _instrument_google_genai() -> None:
    """Google GenAI SDK — traces Gemini generate_content calls."""
    from openinference.instrumentation.google_genai import (
        GoogleGenAIInstrumentor,
    )
    GoogleGenAIInstrumentor().instrument()


# ===================================================================
# Agent frameworks
# ===================================================================

def _instrument_langchain() -> None:
    """LangChain / LangGraph — traces chains, agents, tools, graph nodes.

    This hooks into langchain-core which is shared by LangGraph, DeepAgents,
    and all LangChain partner packages (langchain-openai, langchain-anthropic,
    langchain-google-genai).  Every chain.invoke(), graph.astream(), and
    tool call gets a span with input/output.
    """
    from openinference.instrumentation.langchain import LangChainInstrumentor
    LangChainInstrumentor().instrument()


def _instrument_google_adk() -> None:
    """Google ADK — traces ADK agent pipelines, workflow nodes, and tool calls.

    Covers both the declarative pipeline runtime (SequentialAgent/ParallelAgent/
    LoopAgent) and the graph Workflow runtime (JoinNode, conditional routing).
    """
    from openinference.instrumentation.google_adk import GoogleADKInstrumentor
    GoogleADKInstrumentor().instrument()


def _instrument_bedrock() -> None:
    """AWS Bedrock — traces invoke_model, converse, and invoke_agent calls
    via boto3 bedrock-runtime client.  Covers Strands Agents when they route
    through Bedrock models.
    """
    from openinference.instrumentation.bedrock import BedrockInstrumentor
    BedrockInstrumentor().instrument()


# ===================================================================
# Opik (Comet AI Observability)
# ===================================================================

def _setup_opik() -> None:
    """Configure the Opik Python SDK to send traces to self-hosted Opik.

    Opik has its own tracing SDK that instruments LangChain, OpenAI, and
    LiteLLM natively.  This runs alongside the OTEL/Phoenix instrumentation
    so traces go to both platforms.
    """
    try:
        import os
        import opik

        opik_url = settings.opik_url or "http://opik-backend:8080"

        # Set env vars before configure — Opik reads these.
        os.environ["OPIK_URL_OVERRIDE"] = opik_url
        os.environ["OPIK_PROJECT_NAME"] = settings.app_name
        os.environ["OPIK_WORKSPACE"] = "default"

        # Configure with explicit URL — don't rely on use_local detection.
        opik.configure(
            url=opik_url,
            use_local=True,
        )

        # Instrument OpenAI SDK
        _instrument("opik_openai", _opik_instrument_openai)
        # Instrument LiteLLM
        _instrument("opik_litellm", _opik_instrument_litellm)
        # Instrument LangChain/LangGraph
        _instrument("opik_langchain", _opik_instrument_langchain)

        log.info("opik_tracing_ready", url=opik_url,
                 project=settings.app_name)
    except Exception as exc:
        log.warning("opik_init_failed", error=str(exc)[:300])


def _opik_instrument_openai() -> None:
    """Verify Opik OpenAI integration is available.

    Opik's track_openai wraps individual client instances, not the module.
    The actual wrapping happens in each runtime when it creates an OpenAI
    client.  Here we just confirm the import works.
    """
    from opik.integrations.openai import track_openai  # noqa: F401


def _opik_instrument_litellm() -> None:
    """Enable Opik callback for LiteLLM globally.

    track_litellm() registers a LiteLLM callback that sends every
    completion call to Opik — this covers all runtimes that use LiteLLM
    (ADK, Strands, MS Agent Framework).
    """
    from opik.integrations.litellm import track_litellm
    track_litellm(project_name=settings.app_name)


def _opik_instrument_langchain() -> None:
    """Register Opik as a global LangChain callback.

    The OpikTracer callback captures all LangChain/LangGraph chain runs,
    agent steps, and tool calls and sends them to Opik.
    """
    from opik.integrations.langchain import OpikTracer
    import langchain_core.callbacks.manager as cb_manager

    opik_tracer = OpikTracer(project_name=settings.app_name)
    # Add to the global callback list so every chain.invoke() is traced.
    if not any(isinstance(cb, OpikTracer)
               for cb in cb_manager.get_callback_manager().handlers):
        cb_manager.get_callback_manager().add_handler(opik_tracer)
