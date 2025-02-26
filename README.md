# Document Embeddings & Indexing System

Automated system for document processing, embedding generation, and integration with OpenSearch to support RAG capabilities in Infinity AI Copilot.

## Overview

This system automates the extraction, processing, and indexing of documents from multiple sources:
- MITRE ATT&CK Framework
- Admin Guides
- Secure Knowledge Articles
- CPR Research Blogs
- Jira Tickets

## Architecture

The system consists of the following components:
- Management APIs for sync and index operations
- Web UI for monitoring and control
- Specialized jobs for each stage of document processing
- S3 storage for document stages
- OpenSearch for vector search capabilities

## Directory Structure

- **apis/** - API services code
- **database/** - Database schema and migrations
- **docs/** - Documentation including architecture diagrams
- **jobs/** - Processing jobs for each stage of the pipeline
- **k8s/** - Kubernetes configuration files
- **monitoring/** - Monitoring dashboards and scripts
- **terraform/** - Infrastructure as Code
- **ui/** - User interface components
