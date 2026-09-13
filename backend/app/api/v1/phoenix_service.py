"""Phoenix Observability Service Router.

Provides endpoints for interacting with Phoenix (Arize) observability platform:
- Trace management and querying
- Span analysis
- Project management
- Metrics and analytics
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.core.logging import get_logger

log = get_logger(__name__)
router = APIRouter(
    prefix="/services/phoenix",
    tags=["services: phoenix"],
    dependencies=[Depends(current_user)],
)

# Phoenix configuration
PHOENIX_URL = "http://localhost:6006"
PHOENIX_GRPC_URL = "http://localhost:4317"


class TraceQuery(BaseModel):
    """Query parameters for traces."""
    project_name: str | None = Field(None, description="Filter by project name")
    start_time: datetime | None = Field(None, description="Start time for trace query")
    end_time: datetime | None = Field(None, description="End time for trace query")
    limit: int = Field(100, ge=1, le=1000, description="Max number of traces to return")


class SpanQuery(BaseModel):
    """Query parameters for spans."""
    trace_id: str | None = Field(None, description="Filter by trace ID")
    span_kind: str | None = Field(None, description="Filter by span kind (LLM, CHAIN, TOOL, etc.)")
    limit: int = Field(100, ge=1, le=1000, description="Max number of spans")


async def _phoenix_request(
    method: str,
    endpoint: str,
    json_data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Make a request to Phoenix API."""
    url = f"{PHOENIX_URL}{endpoint}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method.upper() == "GET":
                response = await client.get(url, params=params)
            elif method.upper() == "POST":
                response = await client.post(url, json=json_data)
            elif method.upper() == "DELETE":
                response = await client.delete(url)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            if response.status_code in (200, 201):
                return response.json() if response.content else {"status": "success"}
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Phoenix API error: {response.text}"
                )
    
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to Phoenix at {PHOENIX_URL}"
        )
    except Exception as exc:
        log.error("phoenix_request_error", endpoint=endpoint, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/health", summary="Check Phoenix health")
async def check_health() -> dict[str, Any]:
    """Check if Phoenix service is healthy."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{PHOENIX_URL}/healthz")
            
            return {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "url": PHOENIX_URL,
                "grpc_url": PHOENIX_GRPC_URL,
                "response": response.json() if response.status_code == 200 else None
            }
    except httpx.ConnectError:
        return {
            "status": "down",
            "url": PHOENIX_URL,
            "error": "Connection refused"
        }
    except Exception as exc:
        return {
            "status": "error",
            "url": PHOENIX_URL,
            "error": str(exc)
        }


@router.get("/projects", summary="List Phoenix projects")
async def list_projects() -> dict[str, Any]:
    """List all projects in Phoenix."""
    try:
        # Phoenix GraphQL API endpoint
        query = """
        query {
            projects {
                edges {
                    node {
                        id
                        name
                        traceCount
                        spanCount
                        createdAt
                    }
                }
            }
        }
        """
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{PHOENIX_URL}/graphql",
                json={"query": query}
            )
            
            if response.status_code == 200:
                data = response.json()
                projects = data.get("data", {}).get("projects", {}).get("edges", [])
                
                return {
                    "projects": [edge["node"] for edge in projects],
                    "count": len(projects)
                }
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to fetch projects"
                )
    
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to Phoenix at {PHOENIX_URL}"
        )
    except Exception as exc:
        log.error("list_projects_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/traces/query", summary="Query traces")
async def query_traces(query: TraceQuery) -> dict[str, Any]:
    """Query traces from Phoenix with filters."""
    try:
        # Build GraphQL query
        gql_query = f"""
        query {{
            traces(first: {query.limit}) {{
                edges {{
                    node {{
                        id
                        startTime
                        endTime
                        latencyMs
                        tokenCountTotal
                        statusCode
                        project {{
                            name
                        }}
                    }}
                }}
            }}
        }}
        """
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{PHOENIX_URL}/graphql",
                json={"query": gql_query}
            )
            
            if response.status_code == 200:
                data = response.json()
                traces = data.get("data", {}).get("traces", {}).get("edges", [])
                
                log.info("query_traces", count=len(traces))
                
                return {
                    "traces": [edge["node"] for edge in traces],
                    "count": len(traces),
                    "limit": query.limit
                }
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to query traces"
                )
    
    except Exception as exc:
        log.error("query_traces_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/traces/{trace_id}", summary="Get trace details")
async def get_trace(trace_id: str) -> dict[str, Any]:
    """Get detailed information about a specific trace."""
    try:
        gql_query = f"""
        query {{
            trace(id: "{trace_id}") {{
                id
                startTime
                endTime
                latencyMs
                tokenCountTotal
                tokenCountPrompt
                tokenCountCompletion
                statusCode
                project {{
                    name
                }}
                spans {{
                    edges {{
                        node {{
                            id
                            name
                            spanKind
                            startTime
                            endTime
                            latencyMs
                            statusCode
                        }}
                    }}
                }}
            }}
        }}
        """
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{PHOENIX_URL}/graphql",
                json={"query": gql_query}
            )
            
            if response.status_code == 200:
                data = response.json()
                trace = data.get("data", {}).get("trace")
                
                if not trace:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Trace {trace_id} not found"
                    )
                
                return {"trace": trace}
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to fetch trace"
                )
    
    except HTTPException:
        raise
    except Exception as exc:
        log.error("get_trace_error", trace_id=trace_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/spans/query", summary="Query spans")
async def query_spans(query: SpanQuery) -> dict[str, Any]:
    """Query spans from Phoenix with filters."""
    try:
        # Build filter conditions
        filter_clause = ""
        if query.trace_id:
            filter_clause = f'(filter: {{traceId: "{query.trace_id}"}})'
        
        gql_query = f"""
        query {{
            spans{filter_clause} (first: {query.limit}) {{
                edges {{
                    node {{
                        id
                        name
                        spanKind
                        startTime
                        endTime
                        latencyMs
                        statusCode
                        tokenCountTotal
                        traceId
                    }}
                }}
            }}
        }}
        """
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{PHOENIX_URL}/graphql",
                json={"query": gql_query}
            )
            
            if response.status_code == 200:
                data = response.json()
                spans = data.get("data", {}).get("spans", {}).get("edges", [])
                
                log.info("query_spans", count=len(spans))
                
                return {
                    "spans": [edge["node"] for edge in spans],
                    "count": len(spans),
                    "limit": query.limit
                }
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to query spans"
                )
    
    except Exception as exc:
        log.error("query_spans_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/metrics/summary", summary="Get metrics summary")
async def get_metrics_summary(
    project_name: str | None = Query(None, description="Filter by project")
) -> dict[str, Any]:
    """Get summary metrics from Phoenix."""
    try:
        # Try to get basic metrics
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check if Phoenix has a metrics endpoint
            response = await client.get(f"{PHOENIX_URL}/metrics")
            
            if response.status_code == 200:
                return {
                    "metrics": response.text,
                    "format": "prometheus"
                }
            else:
                # Return basic info
                return {
                    "message": "Metrics endpoint not available",
                    "phoenix_url": PHOENIX_URL,
                    "alternative": "Use /projects and /traces/query for detailed analytics"
                }
    
    except Exception as exc:
        log.warning("get_metrics_error", error=str(exc))
        return {
            "message": "Could not fetch metrics",
            "error": str(exc)
        }


@router.delete("/traces/{trace_id}", summary="Delete a trace")
async def delete_trace(trace_id: str) -> dict[str, Any]:
    """Delete a specific trace from Phoenix."""
    try:
        mutation = f"""
        mutation {{
            deleteTrace(id: "{trace_id}") {{
                success
            }}
        }}
        """
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{PHOENIX_URL}/graphql",
                json={"query": mutation}
            )
            
            if response.status_code == 200:
                data = response.json()
                success = data.get("data", {}).get("deleteTrace", {}).get("success", False)
                
                log.info("delete_trace", trace_id=trace_id, success=success)
                
                return {
                    "trace_id": trace_id,
                    "deleted": success
                }
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to delete trace"
                )
    
    except Exception as exc:
        log.error("delete_trace_error", trace_id=trace_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/config", summary="Get Phoenix configuration")
async def get_config() -> dict[str, Any]:
    """Get Phoenix service configuration."""
    return {
        "phoenix_url": PHOENIX_URL,
        "grpc_endpoint": PHOENIX_GRPC_URL,
        "ui_url": PHOENIX_URL,
        "graphql_endpoint": f"{PHOENIX_URL}/graphql",
        "features": {
            "tracing": True,
            "spans": True,
            "projects": True,
            "metrics": True,
            "graphql_api": True
        }
    }
