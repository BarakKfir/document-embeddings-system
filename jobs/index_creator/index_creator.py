#!/usr/bin/env python3
# IndexCreator Job - Creates OpenSearch indices from embedded documents
import os
import sys
import json
import requests
import logging
import boto3
import uuid
from datetime import datetime
import time
import hashlib
import opensearchpy
from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.helpers import bulk
import concurrent.futures

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('index-creator')

# Environment variables
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'staging')
REGION = os.environ.get('REGION', 'us')
SOURCE = os.environ.get('SOURCE')
API_KEY = os.environ.get('API_KEY')
API_BASE_URL = os.environ.get('API_BASE_URL', 'http://index-management-api:8000')
S3_BUCKET = os.environ.get('S3_BUCKET', 'document-embeddings')
OPENSEARCH_HOST = os.environ.get('OPENSEARCH_HOST')
OPENSEARCH_PORT = int(os.environ.get('OPENSEARCH_PORT', '9200'))
OPENSEARCH_USER = os.environ.get('OPENSEARCH_USER')
OPENSEARCH_PASSWORD = os.environ.get('OPENSEARCH_PASSWORD')
USE_SSL = os.environ.get('USE_SSL', 'true').lower() == 'true'
VECTOR_DIMENSIONS = int(os.environ.get('VECTOR_DIMENSIONS', '1536'))  # OpenAI ada-002 dimensions

# Initialize S3 client
s3_client = boto3.client('s3',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_KEY')
)

# Initialize OpenSearch client
def get_opensearch_client():
    """Create and return an OpenSearch client"""
    try:
        # Configure OpenSearch connection
        os_config = {
            'hosts': [{'host': OPENSEARCH_HOST, 'port': OPENSEARCH_PORT}],
            'http_auth': (OPENSEARCH_USER, OPENSEARCH_PASSWORD) if OPENSEARCH_USER else None,
            'use_ssl': USE_SSL,
            'verify_certs': False,
            'connection_class': RequestsHttpConnection,
            'timeout': 120
        }
        
        return OpenSearch(**os_config)
    except Exception as e:
        logger.error(f"Failed to initialize OpenSearch client: {str(e)}")
        raise

# API client for status reporting
def report_status(job_id, status, message=None, error=None):
    """Report job status to the Index Management API"""
    url = f"{API_BASE_URL}/job/{job_id}/status"
    data = {
        "status": status,
        "message": message,
        "error": error
    }
    headers = {"X-API-Key": API_KEY}
    
    try:
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to report status: {str(e)}")
        return False

def get_collection_path():
    """Determine the collection path based on environment"""
    if ENVIRONMENT == 'staging':
        collection_type = 'index_collections'
    else:  # production
        collection_type = 'valid_index_collections'
    
    # List S3 objects to find the latest collection
    try:
        prefix = f"{collection_type}/{SOURCE}/"
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix=prefix,
            Delimiter='/'
        )
        
        if 'CommonPrefixes' not in response:
            raise Exception(f"No collection folders found for source {SOURCE}")
        
        # Find the most recent collection by date in folder name
        collection_folders = []
        for prefix_obj in response['CommonPrefixes']:
            folder_prefix = prefix_obj['Prefix']
            collection_folder = folder_prefix.split('/')[-2]
            if '_' in collection_folder:
                collection_folders.append(folder_prefix)
        
        if not collection_folders:
            raise Exception(f"No valid collection folders found for source {SOURCE}")
        
        # Sort folders by date (assuming format: <uuid>_<date>)
        collection_folders.sort(reverse=True)
        return collection_folders[0]
    except Exception as e:
        logger.error(f"Error finding latest collection: {str(e)}")
        raise

def create_index_mapping():
    """Create the OpenSearch index mapping with vector search capabilities"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    index_name = f"{SOURCE.lower()}-{timestamp}"
    
    # Define the index mapping
    mapping = {
        "settings": {
            "number_of_shards": 5,
            "number_of_replicas": 1,
            "index": {
                "refresh_interval": "1s"
            }
        },
        "mappings": {
            "properties": {
                "document_id": {"type": "keyword"},
                "chunk_id": {"type": "keyword"},
                "source": {"type": "keyword"},
                "sync_id": {"type": "keyword"},
                "text": {"type": "text"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": VECTOR_DIMENSIONS
                },
                "metadata": {
                    "type": "object",
                    "dynamic": True
                },
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"}
            }
        }
    }
    
    return index_name, mapping

def process_document(client, index_name, document_path):
    """Process a single document and index all its chunks"""
    try:
        # Get document from S3
        response = s3_client.get_object(
            Bucket=S3_BUCKET,
            Key=document_path
        )
        document = json.loads(response['Body'].read().decode('utf-8'))
        
        # Prepare document chunks for indexing
        actions = []
        
        for chunk in document.get('chunks', []):
            action = {
                "_index": index_name,
                "_id": chunk.get('chunk_id'),
                "_source": {
                    "document_id": document.get('document_id'),
                    "chunk_id": chunk.get('chunk_id'),
                    "source": document.get('source', SOURCE),
                    "sync_id": document.get('sync_id'),
                    "text": chunk.get('text', ''),
                    "embedding": chunk.get('embedding', []),
                    "metadata": document.get('metadata', {}),
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
            }
            actions.append(action)
        
        if actions:
            # Use bulk helper to index the chunks
            success, failed = bulk(client, actions, stats_only=True)
            return success, failed
        return 0, 0
    except Exception as e:
        logger.error(f"Error processing document {document_path}: {str(e)}")
        return 0, 1

def main():
    """Main entry point"""
    # Create a unique job ID
    job_id = str(uuid.uuid4())
    
    logger.info(f"Starting index creation job for {SOURCE} in {ENVIRONMENT} ({REGION}) with job ID {job_id}")
    
    # Report initial status
    report_status(job_id, "running", f"Starting index creation for {SOURCE}")
    
    try:
        # Get OpenSearch client
        client = get_opensearch_client()
        
        # Create index with proper mapping
        index_name, mapping = create_index_mapping()
        
        logger.info(f"Creating index: {index_name}")
        client.indices.create(index=index_name, body=mapping)
        
        # Get the collection path
        collection_path = get_collection_path()
        logger.info(f"Using collection: {collection_path}")
        
        # List all embedded documents in the collection
        document_paths = []
        paginator = s3_client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=collection_path):
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    if key.endswith('.json') and not key.endswith('metadata.json'):
                        document_paths.append(key)
        
        total_documents = len(document_paths)
        logger.info(f"Found {total_documents} documents to index")
        
        # Update status
        report_status(job_id, "running", f"Indexing {total_documents} documents in {index_name}")
        
        # Process documents in parallel using thread pool
        success_count = 0
        failure_count = 0
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # Submit document processing tasks
            future_to_path = {
                executor.submit(process_document, client, index_name, path): path
                for path in document_paths
            }
            
            # Process results as they complete
            completed = 0
            for future in concurrent.futures.as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    success, failed = future.result()
                    success_count += success
                    failure_count += failed
                except Exception as e:
                    logger.error(f"Document processing failed for {path}: {str(e)}")
                    failure_count += 1
                
                completed += 1
                if completed % 100 == 0 or completed == total_documents:
                    progress = completed / total_documents * 100
                    logger.info(f"Progress: {completed}/{total_documents} documents ({progress:.1f}%)")
                    report_status(
                        job_id, 
                        "running", 
                        f"Indexed {completed}/{total_documents} documents, {success_count} chunks created"
                    )
        
        # Refresh the index to make documents searchable
        client.indices.refresh(index=index_name)
        
        # Get document count in the index
        stats = client.indices.stats(index=index_name)
        doc_count = stats['_all']['primaries']['docs']['count']
        index_size = stats['_all']['primaries']['store']['size_in_bytes']
        
        # Create alias if this is the first index
        is_first_index = False
        alias_name = f"{SOURCE.lower()}"
        
        try:
            # Check if alias exists
            existing_alias = client.indices.get_alias(name=alias_name)
            logger.info(f"Alias {alias_name} already exists, pointing to: {list(existing_alias.keys())}")
        except opensearchpy.exceptions.NotFoundError:
            # Alias doesn't exist, create it
            is_first_index = True
            logger.info(f"Creating new alias {alias_name} pointing to {index_name}")
            client.indices.put_alias(index=index_name, name=alias_name)
        
        # Update job status in database via API
        update_url = f"{API_BASE_URL}/indices"
        update_data = {
            "environment": ENVIRONMENT,
            "region": REGION,
            "source": SOURCE,
            "index_name": index_name,
            "alias_name": alias_name,
            "status": "created",
            "document_count": doc_count,
            "size_bytes": index_size,
            "job_id": job_id,
            "is_first_index": is_first_index
        }
        headers = {"X-API-Key": API_KEY}
        
        try:
            response = requests.post(update_url, json=update_data, headers=headers)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to update index status in database: {str(e)}")
        
        # Report completion
        report_status(
            job_id, 
            "completed", 
            f"Successfully created index {index_name} with {doc_count} documents"
        )
        
        logger.info(f"Index creation complete: {index_name} with {doc_count} documents")
    except Exception as e:
        error_msg = f"Error creating index: {str(e)}"
        logger.error(error_msg)
        report_status(job_id, "failed", error=error_msg)
        sys.exit(1)

if __name__ == "__main__":
    main()
