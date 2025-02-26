#!/usr/bin/env python3
# Source Sync Job - Detects and downloads documents from configured sources
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
import xml.etree.ElementTree as ET

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('source-sync')

# Environment variables
SYNC_ID = os.environ.get('SYNC_ID')
SOURCE = os.environ.get('SOURCE')
FRESH_START = os.environ.get('FRESH_START', 'false').lower() == 'true'
API_KEY = os.environ.get('API_KEY')
API_BASE_URL = os.environ.get('API_BASE_URL', 'http://sync-management-api:8000')
S3_BUCKET = os.environ.get('S3_BUCKET', 'document-embeddings')

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
        "job_type": "source-sync",
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

def get_last_valid_index():
    """Get the latest valid index collection metadata for the source"""
    if FRESH_START:
        return None
    
    try:
        # List objects in valid_index_collections for this source
        prefix = f"valid_index_collections/{SOURCE}/"
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix=prefix
        )
        
        if 'Contents' not in response:
            return None
        
        # Get the latest index by looking at the timestamps in folder names
        collection_folders = []
        for obj in response['Contents']:
            key = obj['Key']
            parts = key.split('/')
            if len(parts) >= 3:
                collection_folder = parts[2]
                if collection_folder not in collection_folders:
                    collection_folders.append(collection_folder)
        
        if not collection_folders:
            return None
        
        # Sort by timestamp portion (after the uuid_)
        collection_folders.sort(key=lambda x: x.split('_')[1] if '_' in x else '', reverse=True)
        latest_folder = collection_folders[0]
        
        # Get metadata file from this folder
        metadata_key = f"{prefix}{latest_folder}/metadata.json"
        try:
            response = s3_client.get_object(
                Bucket=S3_BUCKET,
                Key=metadata_key
            )
            metadata = json.loads(response['Body'].read().decode('utf-8'))
            return metadata
        except s3_client.exceptions.NoSuchKey:
            return None
    except Exception as e:
        logger.error(f"Error getting last valid index: {str(e)}")
        return None

def process_mitre():
    """Process MITRE ATT&CK Enterprise framework data"""
    url = "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"
    report_status("running", f"Downloading MITRE data from {url}")
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Get last valid index metadata if available
        last_index = get_last_valid_index()
        last_mitre_hash = last_index.get('mitre_hash') if last_index else None
        
        # Calculate hash of current data
        current_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        
        # Check if data has changed
        if last_mitre_hash == current_hash and not FRESH_START:
            report_status("completed", "No changes detected in MITRE data")
            return
        
        # Process objects - in MITRE, these are the individual techniques, tactics, etc.
        objects_processed = 0
        objects_total = len(data.get('objects', []))
        
        for obj in data.get('objects', []):
            # Only process certain types of objects
            if obj.get('type') in ['attack-pattern', 'course-of-action', 'intrusion-set']:
                obj_id = obj.get('id', str(uuid.uuid4()))
                
                # Create document path in S3
                object_path = f"original/{SOURCE}/{SYNC_ID}_{datetime.now().strftime('%Y%m%d')}/{obj_id}.json"
                
                # Save to S3
                s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=object_path,
                    Body=json.dumps(obj).encode('utf-8'),
                    ContentType='application/json'
                )
                
                # Report document status
                report_document(
                    document_id=obj_id,
                    status="downloaded",
                    stage="original",
                    path=object_path
                )
                
                objects_processed += 1
                if objects_processed % 100 == 0:
                    progress = objects_processed / objects_total
                    report_status("running", f"Processed {objects_processed}/{objects_total} MITRE objects", progress=progress)
        
        # Save metadata
        metadata = {
            "sync_id": SYNC_ID,
            "source": SOURCE,
            "timestamp": datetime.now().isoformat(),
            "mitre_hash": current_hash,
            "objects_count": objects_processed
        }
        
        metadata_path = f"original/{SOURCE}/{SYNC_ID}_{datetime.now().strftime('%Y%m%d')}/metadata.json"
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=metadata_path,
            Body=json.dumps(metadata).encode('utf-8'),
            ContentType='application/json'
        )
        
        report_status("completed", f"Successfully processed {objects_processed} MITRE objects")
    except Exception as e:
        error_msg = f"Error processing MITRE data: {str(e)}"
        logger.error(error_msg)
        report_status("failed", error=error_msg)
        sys.exit(1)

def process_admin_guides():
    """Process Admin Guides from support.checkpoint.com"""
    sitemap_url = "https://support.checkpoint.com/sitemaps/documentation-sitemap-index.xml"
    report_status("running", f"Downloading Admin Guides sitemap from {sitemap_url}")
    
    try:
        response = requests.get(sitemap_url)
        response.raise_for_status()
        
        # Parse sitemap index
        root = ET.fromstring(response.content)
        
        # Define namespace
        ns = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        
        # Get individual sitemaps
        sitemaps = []
        for sitemap in root.findall("sitemap:sitemap", ns):
            loc = sitemap.find("sitemap:loc", ns)
            if loc is not None and "documentation" in loc.text:
                sitemaps.append(loc.text)
        
        # Process each sitemap
        total_docs = 0
        processed_docs = 0
        
        # First, count total docs across all sitemaps
        for sitemap_url in sitemaps:
            try:
                response = requests.get(sitemap_url)
                response.raise_for_status()
                sitemap_root = ET.fromstring(response.content)
                total_docs += len(sitemap_root.findall("sitemap:url", ns))
            except Exception as e:
                logger.warning(f"Error counting docs in sitemap {sitemap_url}: {str(e)}")
        
        report_status("running", f"Found {total_docs} documents in sitemaps")
        
        # Now process each document
        for sitemap_url in sitemaps:
            try:
                response = requests.get(sitemap_url)
                response.raise_for_status()
                sitemap_root = ET.fromstring(response.content)
                
                for url in sitemap_root.findall("sitemap:url", ns):
                    loc = url.find("sitemap:loc", ns)
                    lastmod = url.find("sitemap:lastmod", ns)
                    
                    if loc is not None:
                        doc_url = loc.text
                        doc_id = hashlib.md5(doc_url.encode()).hexdigest()
                        lastmod_date = lastmod.text if lastmod is not None else None
                        
                        # Skip if not changed (based on lastmod) unless fresh start
                        if not FRESH_START and lastmod_date:
                            # TODO: Check against last valid index
                            pass
                        
                        # Download document content
                        try:
                            doc_response = requests.get(doc_url)
                            doc_response.raise_for_status()
                            
                            # Save to S3
                            object_path = f"original/{SOURCE}/{SYNC_ID}_{datetime.now().strftime('%Y%m%d')}/{doc_id}.html"
                            
                            s3_client.put_object(
                                Bucket=S3_BUCKET,
                                Key=object_path,
                                Body=doc_response.content,
                                ContentType='text/html',
                                Metadata={
                                    'url': doc_url,
                                    'lastmod': lastmod_date or '',
                                    'source': SOURCE
                                }
                            )
                            
                            # Report document status
                            report_document(
                                document_id=doc_id,
                                status="downloaded",
                                stage="original",
                                path=object_path
                            )
                            
                            processed_docs += 1
                            if processed_docs % 10 == 0:
                                progress = processed_docs / total_docs
                                report_status(
                                    "running", 
                                    f"Processed {processed_docs}/{total_docs} Admin Guide documents", 
                                    progress=progress
                                )
                        except Exception as e:
                            logger.warning(f"Error downloading document {doc_url}: {str(e)}")
                            report_document(
                                document_id=doc_id,
                                status="failed",
                                stage="original",
                                error=str(e)
                            )
            except Exception as e:
                logger.warning(f"Error processing sitemap {sitemap_url}: {str(e)}")
        
        # Save metadata
        metadata = {
            "sync_id": SYNC_ID,
            "source": SOURCE,
            "timestamp": datetime.now().isoformat(),
            "documents_count": processed_docs
        }
        
        metadata_path = f"original/{SOURCE}/{SYNC_ID}_{datetime.now().strftime('%Y%m%d')}/metadata.json"
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=metadata_path,
            Body=json.dumps(metadata).encode('utf-8'),
            ContentType='application/json'
        )
        
        report_status("completed", f"Successfully processed {processed_docs} Admin Guide documents")
    except Exception as e:
        error_msg = f"Error processing Admin Guides: {str(e)}"
        logger.error(error_msg)
        report_status("failed", error=error_msg)
        sys.exit(1)

# Similar functions would be implemented for other sources:
# - process_secure_knowledge()
# - process_cpr_blogs()
# - process_jira_tickets()

def main():
    """Main entry point"""
    logger.info(f"Starting source sync job for {SOURCE} with sync ID {SYNC_ID}")
    logger.info(f"Fresh start: {FRESH_START}")
    
    # Report initial status
    report_status("running", f"Starting document sync for {SOURCE}")
    
    # Process according to source type
    if SOURCE == "mitre":
        process_mitre()
    elif SOURCE == "admin_guides":
        process_admin_guides()
    elif SOURCE == "secure_knowledge":
        # process_secure_knowledge()
        pass
    elif SOURCE == "cpr_blogs":
        # process_cpr_blogs()
        pass
    elif SOURCE == "jira_tickets":
        # process_jira_tickets()
        pass
    else:
        error_msg = f"Unknown source: {SOURCE}"
        logger.error(error_msg)
        report_status("failed", error=error_msg)
        sys.exit(1)
    
    logger.info(f"Source sync job completed for {SOURCE}")

if __name__ == "__main__":
    main()
