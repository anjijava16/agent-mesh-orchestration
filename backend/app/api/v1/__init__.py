from fastapi import APIRouter

from app.api.v1 import (
    admin_celery,
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
)

api_router = APIRouter()
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
