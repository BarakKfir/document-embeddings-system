#!/usr/bin/env python3
# DocsEmbeddings Job - Processes sanitized documents into embeddings
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
import asyncio
import aiohttp
from tqdm import tqdm
import numpy as np
import re
import io

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('docs-embeddings')

# Environment variables
SYNC_ID = os.environ.get('SYNC_ID')
SOURCE = os.environ.get('SOURCE')
API_KEY = os.environ.get('API_KEY')
API_BASE_URL = os.environ.get('API_BASE_URL', 'http://sync-management-api:8000')
S3_BUCKET = os.environ.get('S3_BUCKET', 'document-embeddings')
AZURE_OPENAI_ENDPOINT = os.environ.get('AZURE_OPENAI_ENDPOINT')
AZURE_OPENAI_KEY = os.environ.get('AZURE_OPENAI_KEY')
AZURE_OPENAI_DEPLOYMENT = os.environ.get('AZURE_OPENAI_DEPLOYMENT', 'text-embedding-ada-002')
MAX_CONCURRENT_REQUESTS = int(os.environ.get('MAX_CONCURRENT_REQUESTS', '5'))
CHUNK_SIZE = int(os.environ.get('CHUNK_SIZE', '1000'))  # Text chunk size for embeddings
CHUNK_OVERLAP = int(os.environ.get('CHUNK_OVERLAP', '200'))  # Overlap between chunks

# Initialize S3 client
s3_client = boto3.client('s3',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_KEY')
)

# API client for status reporting
def report_status(status, message=None, error=None, progress=None):
    """Report job status to the Sync Management API"""
    url = f"{API_BASE_URL}/job/{SYNC_ID}/status"
    data = {
        "status": status,
        "job_type": "docs-embeddings",
        "message": message,
        "error": error,
        "progress": progress
    }
    headers = {"X-API-Key": API_KEY}
    
    try:
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to report status: {str(e)}")
        return False

def report_document(document_id, status, stage, path=None, error=None):
    """Report document status to the Sync Management API"""
    url = f"{API_BASE_URL}/job/{SYNC_ID}/document"
    data = {
        "document_id": document_id,
        "status": status,
        "stage": stage,
        "path": path,
        "error": error
    }
    headers = {"X-API-Key": API_KEY}
    
    try:
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to report document status: {str(e)}")
        return False

def get_sanitized_documents():
    """Get list of sanitized documents for this sync"""
    try:
        # List objects in sanitized folder for this sync
        prefix = f"sanitized/{SOURCE}/{SYNC_ID}"
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix=prefix
        )
        
        if 'Contents' not in response:
            return []
        
        documents = []
        for obj in response['Contents']:
            key = obj['Key']
            if key.endswith('.json') and not key.endswith('metadata.json'):
                # Extract document ID from key
                parts = key.split('/')
                if len(parts) >= 4:
                    filename = parts[-1]
                    doc_id = filename.split('.')[0]
                    documents.append({
                        'key': key,
                        'document_id': doc_id
                    })
        
        return documents
    except Exception as e:
        logger.error(f"Error getting sanitized documents: {str(e)}")
        return []

async def get_embedding(client, text, retries=3):
    """Get embeddings from Azure OpenAI API"""
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/embeddings?api-version=2023-05-15"
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_OPENAI_KEY
    }
    data = {
        "input": text,
        "dimensions": 1536  # OpenAI ada-002 dimensions
    }
    
    for attempt in range(retries):
        try:
            async with client.post(url, headers=headers, json=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.warning(f"API error: {response.status}, {error_text}")
                    if response.status == 429:  # Rate limit
                        wait_time = min(2 ** attempt, 60)  # Exponential backoff
                        logger.info(f"Rate limited, waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue
                    elif response.status >= 500:  # Server error
                        wait_time = min(2 ** attempt, 30)
                        logger.info(f"Server error, waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise Exception(f"API error: {response.status}, {error_text}")
                
                result = await response.json()
                if 'data' in result and len(result['data']) > 0:
                    return result['data'][0]['embedding']
                else:
                    raise Exception("No embedding returned")
        except Exception as e:
            if attempt < retries - 1:
                wait_time = min(2 ** attempt, 30)
                logger.warning(f"Error getting embedding, retrying in {wait_time}s: {str(e)}")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Failed to get embedding after {retries} attempts: {str(e)}")
                raise
    
    raise Exception(f"Failed to get embedding after {retries} attempts")

def chunk_text(text, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP):
    """Split text into overlapping chunks for embedding"""
    if not text or len(text) < chunk_size:
        return [text] if text else []
    
    # Split text into sentences to avoid cutting in the middle of sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 <= chunk_size:
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence
        else:
            # Add current chunk to list if not empty
            if current_chunk:
                chunks.append(current_chunk)
            
            # Start a new chunk, possibly including some overlap
            if chunk_overlap > 0 and current_chunk:
                # Calculate overlap from the end of the current chunk
                words = current_chunk.split()
                overlap_words = words[-min(len(words), chunk_overlap//5):]  # Approximate words in overlap
                current_chunk = " ".join(overlap_words) + " " + sentence
            else:
                current_chunk = sentence
    
    # Add the last chunk if it's not empty
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks

async def process_document(client, semaphore, doc):
    """Process a single document to generate embeddings"""
    document_id = doc['document_id']
    sanitized_key = doc['key']
    
    try:
        # Get sanitized document from S3
        response = s3_client.get_object(
            Bucket=S3_BUCKET,
            Key=sanitized_key
        )
        sanitized_doc = json.loads(response['Body'].read().decode('utf-8'))
        
        # Extract text from sanitized document
        content = sanitized_doc.get('content', '')
        metadata = sanitized_doc.get('metadata', {})
        
        # Chunk text
        chunks = chunk_text(content)
        
        if not chunks:
            logger.warning(f"No content to embed for document {document_id}")
            report_document(
                document_id=document_id,
                status="skipped",
                stage="embedded",
                error="No content to embed"
            )
            return False
        
        # Process each chunk with rate limiting
        chunk_embeddings = []
        chunk_texts = []
        
        for i, chunk in enumerate(chunks):
            async with semaphore:
                try:
                    # Get embedding from Azure OpenAI
                    embedding = await get_embedding(client, chunk)
                    
                    chunk_embeddings.append(embedding)
                    chunk_texts.append(chunk)
                except Exception as e:
                    logger.error(f"Error embedding chunk {i} for document {document_id}: {str(e)}")
                    # Continue with other chunks
        
        if not chunk_embeddings:
            logger.error(f"Failed to generate any embeddings for document {document_id}")
            report_document(
                document_id=document_id,
                status="failed",
                stage="embedded",
                error="Failed to generate embeddings"
            )
            return False
        
        # Create embedded document
        embedded_doc = {
            "document_id": document_id,
            "source": SOURCE,
            "sync_id": SYNC_ID,
            "metadata": metadata,
            "chunks": [
                {
                    "text": text,
                    "embedding": embedding,
                    "chunk_id": f"{document_id}_{i}"
                }
                for i, (text, embedding) in enumerate(zip(chunk_texts, chunk_embeddings))
            ]
        }
        
        # Save to S3
        embedded_path = f"embedded/{SOURCE}/{SYNC_ID}_{datetime.now().strftime('%Y%m%d')}/{document_id}.json"
        
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=embedded_path,
            Body=json.dumps(embedded_doc).encode('utf-8'),
            ContentType='application/json'
        )
        
        # Report success
        report_document(
            document_id=document_id,
            status="completed",
            stage="embedded",
            path=embedded_path
        )
        
        return True
    except Exception as e:
        error_msg = f"Error processing document {document_id}: {str(e)}"
        logger.error(error_msg)
        report_document(
            document_id=document_id,
            status="failed",
            stage="embedded",
            error=error_msg
        )
        return False

async def process_documents(documents):
    """Process all documents to generate embeddings"""
    # Create rate limiting semaphore
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    # Create shared HTTP client session
    async with aiohttp.ClientSession() as client:
        # Process documents with progress tracking
        total = len(documents)
        processed = 0
        success = 0
        
        report_status("running", f"Starting embedding generation for {total} documents")
        
        # Process in batches to avoid overwhelming memory
        batch_size = 20
        for i in range(0, total, batch_size):
            batch = documents[i:i+batch_size]
            tasks = [process_document(client, semaphore, doc) for doc in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                processed += 1
                if isinstance(result, bool) and result:
                    success += 1
                
                # Report progress periodically
                if processed % 10 == 0 or processed == total:
                    progress = processed / total
                    report_status(
                        "running",
                        f"Processed {processed}/{total} documents ({success} successful)",
                        progress=progress
                    )
        
        # Save metadata
        metadata = {
            "sync_id": SYNC_ID,
            "source": SOURCE,
            "timestamp": datetime.now().isoformat(),
            "documents_total": total,
            "documents_success": success,
            "documents_failed": total - success,
            "completion_status": "completed" if success > 0 else "failed"
        }
        
        metadata_path = f"embedded/{SOURCE}/{SYNC_ID}_{datetime.now().strftime('%Y%m%d')}/metadata.json"
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=metadata_path,
            Body=json.dumps(metadata).encode('utf-8'),
            ContentType='application/json'
        )
        
        if success > 0:
            report_status(
                "completed",
                f"Embedded {success}/{total} documents successfully"
            )
        else:
            report_status(
                "failed",
                error=f"Failed to embed any documents"
            )

async def main_async():
    """Async main entry point"""
    logger.info(f"Starting document embeddings job for {SOURCE} with sync ID {SYNC_ID}")
    
    # Report initial status
    report_status("running", "Starting document embeddings generation")
    
    # Get documents to process
    documents = get_sanitized_documents()
    
    if not documents:
        report_status("completed", "No documents to process")
        return
    
    # Process documents
    await process_documents(documents)
    
    logger.info(f"Document embeddings job completed for {SOURCE}")

def main():
    """Main entry point"""
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
