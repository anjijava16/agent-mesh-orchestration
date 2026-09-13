"""Neo4j Graph Database CRUD Operations Router.

Provides comprehensive graph operations for Neo4j:
- Node operations (create, read, update, delete)
- Relationship operations (create, read, delete)
- Cypher query execution
- Graph statistics and schema
- Batch operations
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import AsyncGraphDatabase, AsyncDriver
from neo4j.exceptions import Neo4jError
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)
router = APIRouter(
    prefix="/crud/neo4j",
    tags=["crud: neo4j"],
    dependencies=[Depends(current_user)],
)


def _get_neo4j_driver() -> AsyncDriver:
    """Get Neo4j async driver."""
    return AsyncGraphDatabase.driver(
        f"bolt://{settings.neo4j_host}:{settings.neo4j_port}",
        auth=(settings.neo4j_user, settings.neo4j_password)
    )


class CreateNodeRequest(BaseModel):
    """Request to create a node."""
    labels: list[str] = Field(description="Node labels")
    properties: dict[str, Any] = Field(default_factory=dict, description="Node properties")


class CreateNodesRequest(BaseModel):
    """Request to create multiple nodes."""
    nodes: list[dict[str, Any]] = Field(description="List of nodes with labels and properties")


class UpdateNodeRequest(BaseModel):
    """Request to update a node."""
    node_id: int = Field(description="Internal node ID")
    properties: dict[str, Any] = Field(description="Properties to set/update")


class CreateRelationshipRequest(BaseModel):
    """Request to create a relationship."""
    from_node_id: int = Field(description="Source node ID")
    to_node_id: int = Field(description="Target node ID")
    relationship_type: str = Field(description="Relationship type")
    properties: dict[str, Any] = Field(default_factory=dict, description="Relationship properties")


class CypherQueryRequest(BaseModel):
    """Request to execute a Cypher query."""
    query: str = Field(description="Cypher query")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Query parameters")
    limit: int = Field(default=100, ge=1, le=10000, description="Result limit")


class FindNodesRequest(BaseModel):
    """Request to find nodes."""
    labels: list[str] | None = Field(None, description="Filter by labels")
    properties: dict[str, Any] = Field(default_factory=dict, description="Filter by properties")
    limit: int = Field(default=100, ge=1, le=1000, description="Max nodes to return")


@router.get("/health", summary="Check Neo4j connection")
async def check_health() -> dict[str, Any]:
    """Check if Neo4j is reachable and healthy."""
    try:
        driver = _get_neo4j_driver()
        await driver.verify_connectivity()
        await driver.close()
        
        return {
            "status": "healthy",
            "host": settings.neo4j_host,
            "port": settings.neo4j_port
        }
    
    except Neo4jError as exc:
        return {
            "status": "unhealthy",
            "error": str(exc)
        }


@router.post("/nodes/create", summary="Create a node")
async def create_node(request: CreateNodeRequest) -> dict[str, Any]:
    """Create a new node with labels and properties."""
    try:
        driver = _get_neo4j_driver()
        
        labels_str = ":".join(request.labels)
        props_str = ", ".join([f"{k}: ${k}" for k in request.properties.keys()])
        query = f"CREATE (n:{labels_str} {{{props_str}}}) RETURN id(n) as node_id, n"
        
        async with driver.session() as session:
            result = await session.run(query, **request.properties)
            record = await result.single()
            
            node_id = record["node_id"]
            node_data = dict(record["n"])
        
        await driver.close()
        
        log.info("create_node", labels=request.labels, node_id=node_id)
        
        return {
            "created": True,
            "node_id": node_id,
            "labels": request.labels,
            "properties": node_data
        }
    
    except Neo4jError as exc:
        log.error("create_node_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Neo4j error: {exc}")


@router.post("/nodes/create_many", summary="Create multiple nodes")
async def create_many_nodes(request: CreateNodesRequest) -> dict[str, Any]:
    """Create multiple nodes at once."""
    try:
        driver = _get_neo4j_driver()
        created_ids = []
        
        async with driver.session() as session:
            for node_data in request.nodes:
                labels = node_data.get("labels", [])
                properties = node_data.get("properties", {})
                
                labels_str = ":".join(labels)
                props_str = ", ".join([f"{k}: ${k}" for k in properties.keys()])
                query = f"CREATE (n:{labels_str} {{{props_str}}}) RETURN id(n) as node_id"
                
                result = await session.run(query, **properties)
                record = await result.single()
                created_ids.append(record["node_id"])
        
        await driver.close()
        
        log.info("create_many_nodes", count=len(created_ids))
        
        return {
            "created": True,
            "count": len(created_ids),
            "node_ids": created_ids
        }
    
    except Neo4jError as exc:
        log.error("create_many_nodes_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Neo4j error: {exc}")


@router.get("/nodes/{node_id}", summary="Get node by ID")
async def get_node(node_id: int) -> dict[str, Any]:
    """Get a node by its internal ID."""
    try:
        driver = _get_neo4j_driver()
        
        query = "MATCH (n) WHERE id(n) = $node_id RETURN n, labels(n) as labels"
        
        async with driver.session() as session:
            result = await session.run(query, node_id=node_id)
            record = await result.single()
            
            if not record:
                await driver.close()
                raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
            
            node_data = dict(record["n"])
            node_labels = record["labels"]
        
        await driver.close()
        
        return {
            "found": True,
            "node_id": node_id,
            "labels": node_labels,
            "properties": node_data
        }
    
    except HTTPException:
        raise
    except Neo4jError as exc:
        log.error("get_node_error", node_id=node_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Neo4j error: {exc}")


@router.post("/nodes/find", summary="Find nodes by labels/properties")
async def find_nodes(request: FindNodesRequest) -> dict[str, Any]:
    """Find nodes matching labels and properties."""
    try:
        driver = _get_neo4j_driver()
        
        # Build query
        if request.labels:
            labels_str = ":".join(request.labels)
            match_clause = f"MATCH (n:{labels_str})"
        else:
            match_clause = "MATCH (n)"
        
        where_clauses = [f"n.{k} = ${k}" for k in request.properties.keys()]
        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        
        query = f"{match_clause} {where_clause} RETURN id(n) as node_id, n, labels(n) as labels LIMIT {request.limit}"
        
        async with driver.session() as session:
            result = await session.run(query, **request.properties)
            records = await result.data()
        
        nodes = []
        for record in records:
            nodes.append({
                "node_id": record["node_id"],
                "labels": record["labels"],
                "properties": dict(record["n"])
            })
        
        await driver.close()
        
        log.info("find_nodes", count=len(nodes))
        
        return {
            "nodes": nodes,
            "count": len(nodes)
        }
    
    except Neo4jError as exc:
        log.error("find_nodes_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Neo4j error: {exc}")


@router.put("/nodes/{node_id}", summary="Update a node")
async def update_node(node_id: int, request: UpdateNodeRequest) -> dict[str, Any]:
    """Update node properties."""
    try:
        driver = _get_neo4j_driver()
        
        set_clauses = [f"n.{k} = ${k}" for k in request.properties.keys()]
        set_clause = ", ".join(set_clauses)
        
        query = f"MATCH (n) WHERE id(n) = $node_id SET {set_clause} RETURN n"
        
        async with driver.session() as session:
            result = await session.run(query, node_id=node_id, **request.properties)
            record = await result.single()
            
            if not record:
                await driver.close()
                raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
            
            updated_node = dict(record["n"])
        
        await driver.close()
        
        log.info("update_node", node_id=node_id)
        
        return {
            "updated": True,
            "node_id": node_id,
            "properties": updated_node
        }
    
    except HTTPException:
        raise
    except Neo4jError as exc:
        log.error("update_node_error", node_id=node_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Neo4j error: {exc}")


@router.delete("/nodes/{node_id}", summary="Delete a node")
async def delete_node(
    node_id: int,
    detach: bool = Query(default=True, description="Delete relationships too")
) -> dict[str, Any]:
    """Delete a node (optionally with its relationships)."""
    try:
        driver = _get_neo4j_driver()
        
        delete_clause = "DETACH DELETE n" if detach else "DELETE n"
        query = f"MATCH (n) WHERE id(n) = $node_id {delete_clause}"
        
        async with driver.session() as session:
            await session.run(query, node_id=node_id)
        
        await driver.close()
        
        log.warning("delete_node", node_id=node_id, detach=detach)
        
        return {
            "deleted": True,
            "node_id": node_id,
            "detached": detach
        }
    
    except Neo4jError as exc:
        log.error("delete_node_error", node_id=node_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Neo4j error: {exc}")


@router.post("/relationships/create", summary="Create a relationship")
async def create_relationship(request: CreateRelationshipRequest) -> dict[str, Any]:
    """Create a relationship between two nodes."""
    try:
        driver = _get_neo4j_driver()
        
        props_str = ", ".join([f"{k}: ${k}" for k in request.properties.keys()])
        props_clause = f"{{{props_str}}}" if props_str else ""
        
        query = f"""
        MATCH (a), (b)
        WHERE id(a) = $from_id AND id(b) = $to_id
        CREATE (a)-[r:{request.relationship_type} {props_clause}]->(b)
        RETURN id(r) as rel_id, r
        """
        
        async with driver.session() as session:
            result = await session.run(
                query,
                from_id=request.from_node_id,
                to_id=request.to_node_id,
                **request.properties
            )
            record = await result.single()
            
            if not record:
                await driver.close()
                raise HTTPException(
                    status_code=404,
                    detail="One or both nodes not found"
                )
            
            rel_id = record["rel_id"]
            rel_data = dict(record["r"])
        
        await driver.close()
        
        log.info("create_relationship",
                from_node=request.from_node_id,
                to_node=request.to_node_id,
                type=request.relationship_type)
        
        return {
            "created": True,
            "relationship_id": rel_id,
            "from_node_id": request.from_node_id,
            "to_node_id": request.to_node_id,
            "type": request.relationship_type,
            "properties": rel_data
        }
    
    except HTTPException:
        raise
    except Neo4jError as exc:
        log.error("create_relationship_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Neo4j error: {exc}")


@router.get("/relationships/{node_id}", summary="Get node relationships")
async def get_node_relationships(
    node_id: int,
    direction: str = Query(default="both", regex="^(incoming|outgoing|both)$")
) -> dict[str, Any]:
    """Get all relationships for a node."""
    try:
        driver = _get_neo4j_driver()
        
        if direction == "incoming":
            pattern = "(a)-[r]->(n)"
        elif direction == "outgoing":
            pattern = "(n)-[r]->(b)"
        else:  # both
            pattern = "(n)-[r]-(other)"
        
        query = f"""
        MATCH {pattern}
        WHERE id(n) = $node_id
        RETURN id(r) as rel_id, type(r) as rel_type, r, 
               id(startNode(r)) as start_id, id(endNode(r)) as end_id
        """
        
        async with driver.session() as session:
            result = await session.run(query, node_id=node_id)
            records = await result.data()
        
        relationships = []
        for record in records:
            relationships.append({
                "relationship_id": record["rel_id"],
                "type": record["rel_type"],
                "start_node_id": record["start_id"],
                "end_node_id": record["end_id"],
                "properties": dict(record["r"])
            })
        
        await driver.close()
        
        return {
            "node_id": node_id,
            "direction": direction,
            "relationships": relationships,
            "count": len(relationships)
        }
    
    except Neo4jError as exc:
        log.error("get_relationships_error", node_id=node_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Neo4j error: {exc}")


@router.delete("/relationships/{relationship_id}", summary="Delete a relationship")
async def delete_relationship(relationship_id: int) -> dict[str, Any]:
    """Delete a relationship by its ID."""
    try:
        driver = _get_neo4j_driver()
        
        query = "MATCH ()-[r]->() WHERE id(r) = $rel_id DELETE r"
        
        async with driver.session() as session:
            await session.run(query, rel_id=relationship_id)
        
        await driver.close()
        
        log.warning("delete_relationship", relationship_id=relationship_id)
        
        return {
            "deleted": True,
            "relationship_id": relationship_id
        }
    
    except Neo4jError as exc:
        log.error("delete_relationship_error", relationship_id=relationship_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Neo4j error: {exc}")


@router.post("/cypher", summary="Execute Cypher query")
async def execute_cypher(request: CypherQueryRequest) -> dict[str, Any]:
    """Execute a custom Cypher query."""
    try:
        driver = _get_neo4j_driver()
        
        # Add LIMIT if not present in query
        query = request.query
        if "LIMIT" not in query.upper():
            query = f"{query} LIMIT {request.limit}"
        
        async with driver.session() as session:
            result = await session.run(query, **request.parameters)
            records = await result.data()
        
        await driver.close()
        
        log.info("execute_cypher", records=len(records))
        
        return {
            "results": records,
            "count": len(records),
            "query": request.query
        }
    
    except Neo4jError as exc:
        log.error("execute_cypher_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Neo4j error: {exc}")


@router.get("/schema", summary="Get database schema")
async def get_schema() -> dict[str, Any]:
    """Get Neo4j database schema information."""
    try:
        driver = _get_neo4j_driver()
        
        async with driver.session() as session:
            # Get node labels
            labels_result = await session.run("CALL db.labels()")
            labels = [record["label"] async for record in labels_result]
            
            # Get relationship types
            rels_result = await session.run("CALL db.relationshipTypes()")
            rel_types = [record["relationshipType"] async for record in rels_result]
            
            # Get property keys
            props_result = await session.run("CALL db.propertyKeys()")
            property_keys = [record["propertyKey"] async for record in props_result]
        
        await driver.close()
        
        return {
            "node_labels": labels,
            "relationship_types": rel_types,
            "property_keys": property_keys
        }
    
    except Neo4jError as exc:
        log.error("get_schema_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Neo4j error: {exc}")


@router.get("/stats", summary="Get database statistics")
async def get_stats() -> dict[str, Any]:
    """Get Neo4j database statistics."""
    try:
        driver = _get_neo4j_driver()
        
        async with driver.session() as session:
            # Count nodes
            nodes_result = await session.run("MATCH (n) RETURN count(n) as count")
            nodes_record = await nodes_result.single()
            node_count = nodes_record["count"]
            
            # Count relationships
            rels_result = await session.run("MATCH ()-[r]->() RETURN count(r) as count")
            rels_record = await rels_result.single()
            rel_count = rels_record["count"]
            
            # Count labels
            labels_result = await session.run("CALL db.labels() YIELD label RETURN count(label) as count")
            labels_record = await labels_result.single()
            label_count = labels_record["count"]
        
        await driver.close()
        
        return {
            "total_nodes": node_count,
            "total_relationships": rel_count,
            "total_labels": label_count,
            "database": "Neo4j"
        }
    
    except Neo4jError as exc:
        log.error("get_stats_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Neo4j error: {exc}")


@router.delete("/clear", summary="Clear all data (dangerous!)")
async def clear_database() -> dict[str, Any]:
    """Delete all nodes and relationships. USE WITH CAUTION!"""
    try:
        driver = _get_neo4j_driver()
        
        async with driver.session() as session:
            await session.run("MATCH (n) DETACH DELETE n")
        
        await driver.close()
        
        log.warning("clear_database", action="ALL DATA DELETED")
        
        return {
            "cleared": True,
            "message": "All nodes and relationships deleted"
        }
    
    except Neo4jError as exc:
        log.error("clear_database_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Neo4j error: {exc}")
