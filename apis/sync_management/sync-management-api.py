# FastAPI-based Sync Management API
from fastapi import FastAPI, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List, Optional
import boto3
import uuid
import os
import json
from datetime import datetime

from models import SyncJob, DocumentStatus, JobLog, get_db
from kubernetes import client, config

app = FastAPI(title="Document Sync Management API")

# Security schemes
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
security = HTTPBearer()

# Auth for UI-based endpoints (JWT)
def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    # Verify JWT token from CI (would integrate with actual CI auth)
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    
    # TODO: Validate JWT token using CI public key
    return {"user_id": "sample_user", "permissions": ["admin"]}

# Auth for job-based endpoints (API Key)
def get_api_service(api_key: str = Depends(api_key_header)):
    if not api_key or api_key != os.environ.get("INTERNAL_API_KEY"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return {"service": "internal_job"}

# S3 client setup
s3_client = boto3.client('s3',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_KEY')
)

# K8s client setup for job management
config.load_incluster_config()
batch_v1 = client.BatchV1Api()

# Endpoints for UI
@app.get("/sync/status", tags=["UI Endpoints"])
async def get_sync_status(
    source: Optional[str] = None,
    limit: int = 10,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get status of recent sync operations"""
    query = db.query(SyncJob)
    if source:
        query = query.filter(SyncJob.source == source)
    
    jobs = query.order_by(SyncJob.created_at.desc()).limit(limit).all()
    return jobs

@app.post("/sync/start", tags=["UI Endpoints"])
async def start_sync(
    source: str,
    fresh_start: bool = False,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a new sync operation for a specific source"""
    # Check if sync is already running
    running_sync = db.query(SyncJob).filter(
        SyncJob.source == source,
        SyncJob.status.in_(["running", "pending"])
    ).first()
    
    if running_sync:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"A sync for {source} is already in progress"
        )
    
    # Create new sync job record
    sync_id = str(uuid.uuid4())
    new_sync = SyncJob(
        id=sync_id,
        source=source,
        status="pending",
        created_at=datetime.now(),
        created_by=current_user["user_id"],
        fresh_start=fresh_start
    )
    db.add(new_sync)
    db.commit()
    
    # Create Kubernetes job
    job_name = f"source-sync-{sync_id[:8]}"
    job_manifest = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": job_name},
        "spec": {
            "template": {
                "spec": {
                    "containers": [{
                        "name": "source-sync",
                        "image": "document-sync/source-sync:latest",
                        "env": [
                            {"name": "SYNC_ID", "value": sync_id},
                            {"name": "SOURCE", "value": source},
                            {"name": "FRESH_START", "value": str(fresh_start).lower()},
                            {"name": "API_KEY", "value": os.environ.get("INTERNAL_API_KEY")}
                        ]
                    }],
                    "restartPolicy": "Never"
                }
            },
            "backoffLimit": 3
        }
    }
    
    try:
        batch_v1.create_namespaced_job(namespace="document-sync", body=job_manifest)
    except Exception as e:
        # Update job status to failed
        db.query(SyncJob).filter(SyncJob.id == sync_id).update({
            "status": "failed", 
            "error_message": str(e)
        })
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start sync job: {str(e)}"
        )
    
    return {"sync_id": sync_id, "status": "pending"}

@app.post("/sync/{sync_id}/prod-ready", tags=["UI Endpoints"])
async def mark_sync_prod_ready(
    sync_id: str,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark an index collection as ready for production"""
    # Find the sync job
    sync_job = db.query(SyncJob).filter(SyncJob.id == sync_id).first()
    if not sync_job:
        raise HTTPException(status_code=404, detail="Sync job not found")
    
    if sync_job.status != "completed":
        raise HTTPException(
            status_code=400, 
            detail="Cannot mark as prod-ready: sync job is not completed"
        )
    
    # Create job to copy index to valid_index_collections
    job_name = f"index-copy-{sync_id[:8]}"
    job_manifest = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": job_name},
        "spec": {
            "template": {
                "spec": {
                    "containers": [{
                        "name": "index-copy",
                        "image": "document-sync/index-copy:latest",
                        "env": [
                            {"name": "SYNC_ID", "value": sync_id},
                            {"name": "SOURCE", "value": sync_job.source},
                            {"name": "API_KEY", "value": os.environ.get("INTERNAL_API_KEY")}
                        ]
                    }],
                    "restartPolicy": "Never"
                }
            }
        }
    }
    
    try:
        batch_v1.create_namespaced_job(namespace="document-sync", body=job_manifest)
        
        # Update sync job status
        sync_job.prod_ready = True
        sync_job.prod_ready_at = datetime.now()
        sync_job.prod_ready_by = current_user["user_id"]
        db.commit()
        
        return {"sync_id": sync_id, "status": "marked-prod-ready"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to mark as prod-ready: {str(e)}"
        )

# Endpoints for Job reporting
@app.post("/job/{sync_id}/status", tags=["Job Endpoints"])
async def update_job_status(
    sync_id: str,
    status: str,
    job_type: str,
    message: Optional[str] = None,
    error: Optional[str] = None,
    progress: Optional[float] = None,
    service = Depends(get_api_service),
    db: Session = Depends(get_db)
):
    """Update status of a sync job (used by jobs to report progress)"""
    sync_job = db.query(SyncJob).filter(SyncJob.id == sync_id).first()
    if not sync_job:
        raise HTTPException(status_code=404, detail="Sync job not found")
    
    # Add job log
    log = JobLog(
        sync_id=sync_id,
        job_type=job_type,
        status=status,
        message=message,
        error=error,
        created_at=datetime.now()
    )
    db.add(log)
    
    # Update sync job if this is a main job status update
    if job_type == "source-sync":
        sync_job.status = status
        if error:
            sync_job.error_message = error
        if progress is not None:
            sync_job.progress = progress
    
    # Trigger next job in pipeline if needed
    if status == "completed" and job_type == "source-sync":
        # Trigger DocSanitizer job
        # (code similar to start_sync but for sanitizer job)
        pass
    elif status == "completed" and job_type == "doc-sanitizer":
        # Trigger DocsEmbeddings job
        pass
    elif status == "completed" and job_type == "docs-embeddings":
        # Trigger IndexCollector job
        pass
    
    db.commit()
    return {"status": "updated"}

@app.get("/job/{sync_id}/documents", tags=["Job Endpoints"])
async def get_job_documents(
    sync_id: str,
    service = Depends(get_api_service),
    db: Session = Depends(get_db)
):
    """Get document statuses for a sync job (used by jobs)"""
    documents = db.query(DocumentStatus).filter(DocumentStatus.sync_id == sync_id).all()
    return documents

@app.post("/job/{sync_id}/document", tags=["Job Endpoints"])
async def update_document_status(
    sync_id: str,
    document_id: str,
    status: str,
    stage: str,
    path: Optional[str] = None,
    error: Optional[str] = None,
    service = Depends(get_api_service),
    db: Session = Depends(get_db)
):
    """Update document status within a sync job (used by jobs)"""
    doc = db.query(DocumentStatus).filter(
        DocumentStatus.sync_id == sync_id,
        DocumentStatus.document_id == document_id
    ).first()
    
    if not doc:
        doc = DocumentStatus(
            sync_id=sync_id,
            document_id=document_id,
            status=status,
            stage=stage,
            path=path,
            error=error,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(doc)
    else:
        doc.status = status
        doc.stage = stage
        if path:
            doc.path = path
        if error:
            doc.error = error
        doc.updated_at = datetime.now()
    
    db.commit()
    return {"status": "updated"}
