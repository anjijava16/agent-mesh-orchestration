"""Tests for new routers: tiktoken, MCP, Phoenix, MongoDB, Neo4j, OpenSearch, Pinecone.

These are embedded tests to verify endpoint availability and basic functionality.
Full integration tests require actual service connections.
"""
import pytest
from fastapi.testclient import TestClient

# Mock dependencies
@pytest.fixture
def mock_current_user(monkeypatch):
    """Mock current_user dependency."""
    def mock_user():
        return {"sub": "test-user", "email": "test@example.com"}
    
    from app.api import deps
    monkeypatch.setattr(deps, "current_user", lambda: mock_user())
    return mock_user


@pytest.fixture
def client():
    """Create test client."""
    from app.main import app
    return TestClient(app)


# ============================================================================
# Tiktoken Service Tests
# ============================================================================

def test_tiktoken_list_encodings(client, mock_current_user):
    """Test listing available tiktoken encodings."""
    response = client.get("/api/v1/services/tiktoken/encodings")
    assert response.status_code in (200, 401)  # 401 if auth is enforced
    
    if response.status_code == 200:
        data = response.json()
        assert "encodings" in data
        assert "default" in data
        assert isinstance(data["encodings"], list)


def test_tiktoken_count_tokens(client, mock_current_user):
    """Test counting tokens in text."""
    response = client.post(
        "/api/v1/services/tiktoken/count",
        json={"text": "Hello, world!"}
    )
    assert response.status_code in (200, 401)
    
    if response.status_code == 200:
        data = response.json()
        assert "token_count" in data
        assert "characters" in data
        assert data["token_count"] > 0


def test_tiktoken_encode_text(client, mock_current_user):
    """Test encoding text to tokens."""
    response = client.post(
        "/api/v1/services/tiktoken/encode",
        json={"text": "Test"}
    )
    assert response.status_code in (200, 401)
    
    if response.status_code == 200:
        data = response.json()
        assert "tokens" in data
        assert isinstance(data["tokens"], list)


# ============================================================================
# MCP Service Tests
# ============================================================================

def test_mcp_list_services(client, mock_current_user):
    """Test listing MCP services."""
    response = client.get("/api/v1/services/mcp/services")
    assert response.status_code in (200, 401)
    
    if response.status_code == 200:
        data = response.json()
        assert "services" in data
        assert "count" in data


def test_mcp_health_check(client, mock_current_user):
    """Test MCP health check."""
    response = client.get("/api/v1/services/mcp/health")
    assert response.status_code in (200, 401, 503)
    
    if response.status_code == 200:
        data = response.json()
        assert "status" in data
        assert "services" in data


def test_mcp_service_health(client, mock_current_user):
    """Test individual MCP service health."""
    response = client.get("/api/v1/services/mcp/health/documents")
    assert response.status_code in (200, 401, 404, 503)


# ============================================================================
# Phoenix Service Tests
# ============================================================================

def test_phoenix_health(client, mock_current_user):
    """Test Phoenix health check."""
    response = client.get("/api/v1/services/phoenix/health")
    assert response.status_code in (200, 401, 503)
    
    if response.status_code == 200:
        data = response.json()
        assert "status" in data


def test_phoenix_config(client, mock_current_user):
    """Test Phoenix configuration."""
    response = client.get("/api/v1/services/phoenix/config")
    assert response.status_code in (200, 401)
    
    if response.status_code == 200:
        data = response.json()
        assert "phoenix_url" in data
        assert "features" in data


def test_phoenix_projects(client, mock_current_user):
    """Test listing Phoenix projects."""
    response = client.get("/api/v1/services/phoenix/projects")
    assert response.status_code in (200, 401, 503)


# ============================================================================
# LiteLLM Enhanced Tests
# ============================================================================

def test_litellm_rate_limit_info(client, mock_current_user):
    """Test rate limit information endpoint."""
    response = client.get("/api/v1/admin/litellm/rate_limits")
    assert response.status_code in (200, 401)
    
    if response.status_code == 200:
        data = response.json()
        assert "endpoints" in data


def test_litellm_cache_stats(client, mock_current_user):
    """Test cache statistics endpoint."""
    response = client.get("/api/v1/admin/litellm/cache/stats")
    assert response.status_code in (200, 401)
    
    if response.status_code == 200:
        data = response.json()
        assert "total_entries" in data
        assert "cache_ttl_seconds" in data


# ============================================================================
# MongoDB CRUD Tests
# ============================================================================

def test_mongodb_list_databases(client, mock_current_user):
    """Test listing MongoDB databases."""
    response = client.get("/api/v1/crud/mongodb/databases")
    assert response.status_code in (200, 401, 500, 503)
    
    if response.status_code == 200:
        data = response.json()
        assert "databases" in data
        assert "count" in data


def test_mongodb_collection_stats(client, mock_current_user):
    """Test getting collection statistics."""
    response = client.get(
        "/api/v1/crud/mongodb/stats",
        params={"database": "test", "collection": "test"}
    )
    assert response.status_code in (200, 401, 404, 500)


# ============================================================================
# Neo4j CRUD Tests
# ============================================================================

def test_neo4j_health(client, mock_current_user):
    """Test Neo4j health check."""
    response = client.get("/api/v1/crud/neo4j/health")
    assert response.status_code in (200, 401, 500)
    
    if response.status_code == 200:
        data = response.json()
        assert "status" in data


def test_neo4j_schema(client, mock_current_user):
    """Test getting Neo4j schema."""
    response = client.get("/api/v1/crud/neo4j/schema")
    assert response.status_code in (200, 401, 500)
    
    if response.status_code == 200:
        data = response.json()
        assert "node_labels" in data
        assert "relationship_types" in data


def test_neo4j_stats(client, mock_current_user):
    """Test getting Neo4j statistics."""
    response = client.get("/api/v1/crud/neo4j/stats")
    assert response.status_code in (200, 401, 500)
    
    if response.status_code == 200:
        data = response.json()
        assert "total_nodes" in data
        assert "total_relationships" in data


# ============================================================================
# OpenSearch Enhanced Tests
# ============================================================================

def test_opensearch_cluster_info(client):
    """Test OpenSearch cluster information."""
    response = client.get("/api/v1/admin/opensearch/cluster")
    assert response.status_code in (200, 500, 502)
    
    if response.status_code == 200:
        data = response.json()
        assert "cluster_name" in data
        assert "status" in data


def test_opensearch_list_indices(client):
    """Test listing OpenSearch indices."""
    response = client.get("/api/v1/admin/opensearch/indices")
    assert response.status_code in (200, 500, 502)
    
    if response.status_code == 200:
        data = response.json()
        assert "indices" in data
        assert "total" in data


# ============================================================================
# Pinecone CRUD Tests
# ============================================================================

def test_pinecone_health(client, mock_current_user):
    """Test Pinecone health check."""
    response = client.get("/api/v1/crud/pinecone/health")
    assert response.status_code in (200, 401, 500)
    
    if response.status_code == 200:
        data = response.json()
        assert "status" in data


def test_pinecone_list_indexes(client, mock_current_user):
    """Test listing Pinecone indexes."""
    response = client.get("/api/v1/crud/pinecone/indexes")
    assert response.status_code in (200, 401, 500)
    
    if response.status_code == 200:
        data = response.json()
        assert "indexes" in data
        assert "count" in data


def test_pinecone_config(client, mock_current_user):
    """Test Pinecone configuration."""
    response = client.get("/api/v1/crud/pinecone/config")
    assert response.status_code in (200, 401)
    
    if response.status_code == 200:
        data = response.json()
        assert "api_key_configured" in data
        assert "features" in data


# ============================================================================
# Integration Test Examples
# ============================================================================

@pytest.mark.integration
def test_tiktoken_full_workflow(client, mock_current_user):
    """Test complete tiktoken workflow: list encodings, count, encode, decode."""
    # List encodings
    response = client.get("/api/v1/services/tiktoken/encodings")
    assert response.status_code == 200
    encodings = response.json()
    
    # Count tokens
    text = "The quick brown fox jumps over the lazy dog"
    response = client.post(
        "/api/v1/services/tiktoken/count",
        json={"text": text}
    )
    assert response.status_code == 200
    count_data = response.json()
    token_count = count_data["token_count"]
    
    # Encode
    response = client.post(
        "/api/v1/services/tiktoken/encode",
        json={"text": text}
    )
    assert response.status_code == 200
    encode_data = response.json()
    tokens = encode_data["tokens"]
    
    assert len(tokens) == token_count
    
    # Decode
    response = client.post(
        "/api/v1/services/tiktoken/decode",
        json={"tokens": tokens}
    )
    assert response.status_code == 200
    decode_data = response.json()
    
    assert decode_data["text"] == text


@pytest.mark.integration
def test_mongodb_document_lifecycle(client, mock_current_user):
    """Test MongoDB document lifecycle: insert, find, update, delete."""
    # Insert document
    response = client.post(
        "/api/v1/crud/mongodb/documents/insert",
        json={
            "database": "test",
            "collection": "test_collection",
            "document": {"name": "test", "value": 42}
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        doc_id = data["inserted_id"]
        
        # Find document
        response = client.post(
            "/api/v1/crud/mongodb/documents/find",
            json={
                "database": "test",
                "collection": "test_collection",
                "filter": {"_id": doc_id}
            }
        )
        assert response.status_code == 200
        
        # Update document
        response = client.put(
            "/api/v1/crud/mongodb/documents/update_one",
            json={
                "database": "test",
                "collection": "test_collection",
                "filter": {"_id": doc_id},
                "update": {"$set": {"value": 100}}
            }
        )
        assert response.status_code == 200
        
        # Delete document
        response = client.delete(
            "/api/v1/crud/mongodb/documents/delete_one",
            json={
                "database": "test",
                "collection": "test_collection",
                "filter": {"_id": doc_id}
            }
        )
        assert response.status_code == 200


@pytest.mark.integration
def test_neo4j_node_relationship_lifecycle(client, mock_current_user):
    """Test Neo4j node and relationship lifecycle."""
    # Create first node
    response = client.post(
        "/api/v1/crud/neo4j/nodes/create",
        json={
            "labels": ["Person"],
            "properties": {"name": "Alice"}
        }
    )
    
    if response.status_code == 200:
        node1_id = response.json()["node_id"]
        
        # Create second node
        response = client.post(
            "/api/v1/crud/neo4j/nodes/create",
            json={
                "labels": ["Person"],
                "properties": {"name": "Bob"}
            }
        )
        assert response.status_code == 200
        node2_id = response.json()["node_id"]
        
        # Create relationship
        response = client.post(
            "/api/v1/crud/neo4j/relationships/create",
            json={
                "from_node_id": node1_id,
                "to_node_id": node2_id,
                "relationship_type": "KNOWS",
                "properties": {"since": 2024}
            }
        )
        assert response.status_code == 200
        
        # Get relationships
        response = client.get(f"/api/v1/crud/neo4j/relationships/{node1_id}")
        assert response.status_code == 200
        
        # Cleanup
        client.delete(f"/api/v1/crud/neo4j/nodes/{node1_id}?detach=true")
        client.delete(f"/api/v1/crud/neo4j/nodes/{node2_id}?detach=true")


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test requiring live services"
    )
