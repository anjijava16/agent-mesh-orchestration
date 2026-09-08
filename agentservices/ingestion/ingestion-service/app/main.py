"""
Ingestion Service - FastAPI application for file ingestion and processing.
"""
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import logging

from app.config import settings
from app.logging_config import configure_logging
from app.worker.celery_app import celery_app

configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Ingestion Service",
    description="Microservice for file ingestion and document processing",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IngestRequest(BaseModel):
    """Request model for document ingestion."""
    file_id: str
    filename: str
    user_id: str
    vector_backend: str = "opensearch"
    chunk_size: int = 512
    chunk_overlap: int = 50


class IngestResponse(BaseModel):
    """Response model for ingestion task."""
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """Response model for task status check."""
    task_id: str
    state: str
    status: Optional[str] = None
    result: Optional[dict] = None


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "ingestion-service",
        "version": "1.0.0"
    }


@app.post("/api/v1/ingest", response_model=IngestResponse)
async def ingest_document(request: IngestRequest):
    """
    Trigger document ingestion task.
    
    Backend will call this endpoint after uploading file to S3/MinIO.
    """
    try:
        task = celery_app.send_task(
            "app.worker.tasks.ingest_document",
            kwargs={
                "file_id": request.file_id,
                "filename": request.filename,
                "user_id": request.user_id,
                "vector_backend": request.vector_backend,
                "chunk_size": request.chunk_size,
                "chunk_overlap": request.chunk_overlap,
            }
        )
        
        logger.info(f"Ingestion task created: {task.id} for file {request.filename}")
        
        return IngestResponse(
            task_id=task.id,
            status="queued",
            message=f"Ingestion task queued for {request.filename}"
        )
    except Exception as e:
        logger.error(f"Failed to create ingestion task: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to queue ingestion: {str(e)}")


@app.get("/api/v1/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    Get status of an ingestion task.
    """
    try:
        result = celery_app.AsyncResult(task_id)
        
        response = TaskStatusResponse(
            task_id=task_id,
            state=result.state,
            status=result.status
        )
        
        if result.ready():
            if result.successful():
                response.result = result.result
            elif result.failed():
                response.result = {"error": str(result.info)}
        
        return response
    except Exception as e:
        logger.error(f"Failed to get task status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get task status: {str(e)}")


@app.delete("/api/v1/documents/{file_id}")
async def purge_document(file_id: str, vector_backend: str = "opensearch"):
    """
    Purge document from vector store.
    """
    try:
        task = celery_app.send_task(
            "app.worker.tasks.purge_document",
            kwargs={
                "file_id": file_id,
                "vector_backend": vector_backend,
            }
        )
        
        logger.info(f"Purge task created: {task.id} for file {file_id}")
        
        return IngestResponse(
            task_id=task.id,
            status="queued",
            message=f"Purge task queued for {file_id}"
        )
    except Exception as e:
        logger.error(f"Failed to create purge task: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to queue purge: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
