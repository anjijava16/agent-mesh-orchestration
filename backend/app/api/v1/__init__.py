from fastapi import APIRouter

from app.api.v1 import (
    admin_celery,
    admin_litellm,
    admin_metrics,
    admin_opensearch,
    admin_postgres,
    admin_redis,
    admin_storage,
    audit,
    chat,
    files,
    health,
    settings_routes,
    # New service routers
    tiktoken_service,
    mcp_service,
    phoenix_service,
    # New CRUD routers
    mongodb_crud,
    neo4j_crud,
    pinecone_crud,
)

api_router = APIRouter()

# Core endpoints
api_router.include_router(health.router)
api_router.include_router(chat.router)
api_router.include_router(settings_routes.router)
api_router.include_router(files.router)
api_router.include_router(audit.router)

# Admin / infrastructure routers
api_router.include_router(admin_postgres.router)
api_router.include_router(admin_opensearch.router)
api_router.include_router(admin_redis.router)
api_router.include_router(admin_celery.router)
api_router.include_router(admin_storage.router)
api_router.include_router(admin_metrics.router)
api_router.include_router(admin_litellm.router)

# New service routers
api_router.include_router(tiktoken_service.router)
api_router.include_router(mcp_service.router)
api_router.include_router(phoenix_service.router)

# New CRUD routers
api_router.include_router(mongodb_crud.router)
api_router.include_router(neo4j_crud.router)
api_router.include_router(pinecone_crud.router)
