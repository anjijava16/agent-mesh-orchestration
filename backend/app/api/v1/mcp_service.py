"""MCP Services Management Router.

Provides endpoints for managing and monitoring MCP (Model Context Protocol) services:
- MCP Documents (port 8081)
- MCP Search (port 8082)
- MCP Memory (port 8083)
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.core.logging import get_logger

log = get_logger(__name__)
router = APIRouter(
    prefix="/services/mcp",
    tags=["services: mcp"],
    dependencies=[Depends(current_user)],
)

# MCP Service Configuration
MCP_SERVICES = {
    "documents": {
        "name": "MCP Documents",
        "port": 8081,
        "url": "http://localhost:8081",
        "description": "Document storage and retrieval service"
    },
    "search": {
        "name": "MCP Search",
        "port": 8082,
        "url": "http://localhost:8082",
        "description": "Search and query service"
    },
    "memory": {
        "name": "MCP Memory",
        "port": 8083,
        "url": "http://localhost:8083",
        "description": "Memory and context management service"
    }
}


class MCPServiceInfo(BaseModel):
    """MCP Service information model."""
    name: str
    port: int
    url: str
    status: str
    description: str
    health: dict[str, Any] | None = None


class MCPToolRequest(BaseModel):
    """Request to call an MCP tool."""
    service: str = Field(description="Service name: documents, search, or memory")
    tool_name: str = Field(description="Name of the tool to call")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


async def _check_service_health(service_url: str) -> dict[str, Any]:
    """Check health of an MCP service."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{service_url}/health")
            return {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "status_code": response.status_code,
                "data": response.json() if response.status_code == 200 else None
            }
    except httpx.ConnectError:
        return {"status": "down", "error": "Connection refused"}
    except httpx.TimeoutException:
        return {"status": "timeout", "error": "Request timeout"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@router.get("/services", summary="List all MCP services")
async def list_services() -> dict[str, Any]:
    """List all available MCP services with their configurations."""
    return {
        "services": MCP_SERVICES,
        "count": len(MCP_SERVICES)
    }


@router.get("/health", summary="Check health of all MCP services")
async def check_all_health() -> dict[str, Any]:
    """Check the health status of all MCP services."""
    results = {}
    
    for service_id, config in MCP_SERVICES.items():
        health = await _check_service_health(config["url"])
        results[service_id] = {
            "name": config["name"],
            "port": config["port"],
            "url": config["url"],
            "health": health
        }
    
    # Determine overall status
    all_healthy = all(
        r["health"]["status"] == "healthy" 
        for r in results.values()
    )
    
    log.info("mcp_health_check", all_healthy=all_healthy)
    
    return {
        "status": "all_healthy" if all_healthy else "partial_or_down",
        "services": results,
        "timestamp": httpx.AsyncClient()._transport.__class__.__name__  # Just for timestamp effect
    }


@router.get("/health/{service_id}", summary="Check health of specific MCP service")
async def check_service_health(service_id: str) -> dict[str, Any]:
    """Check the health status of a specific MCP service."""
    if service_id not in MCP_SERVICES:
        raise HTTPException(
            status_code=404,
            detail=f"Service '{service_id}' not found. Available: {list(MCP_SERVICES.keys())}"
        )
    
    config = MCP_SERVICES[service_id]
    health = await _check_service_health(config["url"])
    
    log.info("mcp_service_health", service=service_id, status=health["status"])
    
    return {
        "service_id": service_id,
        "name": config["name"],
        "port": config["port"],
        "url": config["url"],
        "description": config["description"],
        "health": health
    }


@router.get("/{service_id}/tools", summary="List tools from an MCP service")
async def list_service_tools(service_id: str) -> dict[str, Any]:
    """List available tools from a specific MCP service."""
    if service_id not in MCP_SERVICES:
        raise HTTPException(
            status_code=404,
            detail=f"Service '{service_id}' not found"
        )
    
    config = MCP_SERVICES[service_id]
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{config['url']}/tools")
            
            if response.status_code == 200:
                return {
                    "service_id": service_id,
                    "service_name": config["name"],
                    "tools": response.json()
                }
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Service returned status {response.status_code}"
                )
    
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to {config['name']} at {config['url']}"
        )
    except Exception as exc:
        log.error("list_tools_error", service=service_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/call_tool", summary="Call an MCP tool")
async def call_mcp_tool(request: MCPToolRequest) -> dict[str, Any]:
    """Call a tool on an MCP service."""
    if request.service not in MCP_SERVICES:
        raise HTTPException(
            status_code=404,
            detail=f"Service '{request.service}' not found"
        )
    
    config = MCP_SERVICES[request.service]
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{config['url']}/call_tool",
                json={
                    "tool_name": request.tool_name,
                    "arguments": request.arguments
                }
            )
            
            if response.status_code == 200:
                log.info("mcp_tool_called", 
                        service=request.service, 
                        tool=request.tool_name)
                return {
                    "service": request.service,
                    "tool_name": request.tool_name,
                    "result": response.json()
                }
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text
                )
    
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to {config['name']}"
        )
    except Exception as exc:
        log.error("call_tool_error", 
                 service=request.service,
                 tool=request.tool_name,
                 error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{service_id}/stats", summary="Get service statistics")
async def get_service_stats(service_id: str) -> dict[str, Any]:
    """Get statistics and metrics from an MCP service."""
    if service_id not in MCP_SERVICES:
        raise HTTPException(
            status_code=404,
            detail=f"Service '{service_id}' not found"
        )
    
    config = MCP_SERVICES[service_id]
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Try common stats endpoints
            endpoints_to_try = ["/stats", "/metrics", "/status"]
            
            for endpoint in endpoints_to_try:
                try:
                    response = await client.get(f"{config['url']}{endpoint}")
                    if response.status_code == 200:
                        return {
                            "service_id": service_id,
                            "service_name": config["name"],
                            "endpoint": endpoint,
                            "stats": response.json()
                        }
                except:
                    continue
            
            # If no stats endpoint found
            return {
                "service_id": service_id,
                "service_name": config["name"],
                "message": "No stats endpoint available",
                "attempted_endpoints": endpoints_to_try
            }
    
    except Exception as exc:
        log.error("get_stats_error", service=service_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
