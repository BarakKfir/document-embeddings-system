# Testing Strategy for Document Embeddings & Indexing System

## Overview

This document outlines the comprehensive testing strategy for the Document Embeddings & Indexing System. The goal is to ensure reliability, performance, and accuracy of the entire pipeline from document ingestion to vector search integration with Infinity AI Copilot.

## Testing Levels

### 1. Unit Testing

**Objective**: Verify that individual components (functions, methods, classes) work correctly in isolation.

**Tools**: pytest, unittest, Jest (for UI)

**Coverage Targets**: 
- Python backend code: 80% minimum code coverage
- JavaScript/React frontend code: 70% minimum code coverage

**Key Components to Test**:
- Document parsing and sanitization
- Embedding generation
- Vector math operations
- API endpoint handlers
- Database access functions
- UI component rendering

**Sample Test Cases**:
```python
# Test for document sanitization function
def test_sanitize_html_document():
    # Arrange
    html_content = """
    <html>
        <head><title>Test Document</title></head>
        <body>
            <h1>Sample Title</h1>
            <p>This is a <b>sample</b> paragraph.</p>
            <script>alert('bad code')</script>
        </body>
    </html>
    """
    
    # Act
    sanitized_text = sanitize_html_document(html_content)
    
    # Assert
    assert "Sample Title" in sanitized_text
    assert "This is a sample paragraph." in sanitized_text
    assert "alert" not in sanitized_text
    assert "<script>" not in sanitized_text
```

### 2. Integration Testing

**Objective**: Verify that components work correctly together.

**Tools**: pytest with integration fixtures, Cypress for UI

**Key Integration Points**:
- API to database connections
- S3 storage interactions
- Embedding model API integration
- OpenSearch client operations
- End-to-end job workflows (e.g., from source sync to embedding generation)

**Sample Test Case**:
```python
# Test OpenSearch index creation and document indexing
def test_index_creation_and_document_indexing(opensearch_client):
    # Arrange
    index_name = f"test-index-{uuid.uuid4()}"
    mapping = create_index_mapping()
    test_document = {
        "document_id": "test-doc-1",
        "chunk_id": "test-chunk-1",
        "text": "This is a test document",
        "embedding": [0.1] * 1536,
        "metadata": {"source": "test"}
    }
    
    # Act
    opensearch_client.indices.create(index=index_name, body=mapping)
    opensearch_client.index(index=index_name, id="test-chunk-1", body=test_document)
    opensearch_client.indices.refresh(index=index_name)
    
    # Query
    result = opensearch_client.get(index=index_name, id="test-chunk-1")
    
    # Assert
    assert result["found"] is True
    assert result["_source"]["document_id"] == "test-doc-1"
    assert result["_source"]["text"] == "This is a test document"
    
    # Clean up
    opensearch_client.indices.delete(index=index_name)
```

### 3. End-to-End Testing

**Objective**: Validate complete workflows from start to finish.

**Tools**: Custom test scripts, Kubernetes jobs for staging environment

**Key Workflows**:
- Full document sync for each source
- Document processing pipeline (download → sanitize → embed → index)
- OpenSearch index creation and alias updates
- UI operations (triggering syncs, monitoring jobs, updating production indices)

**Sample Test Script**:
```python
def test_mitre_sync_workflow():
    # Start a MITRE sync
    sync_id = start_sync_job("mitre")
    
    # Wait for job completion (with timeout)
    wait_for_sync_completion(sync_id, timeout_minutes=30)
    
    # Check sync job status
    sync_job = get_sync_job(sync_id)
    assert sync_job["status"] == "completed"
    assert sync_job["documents_total"] > 0
    assert sync_job["documents_success"] > 0
    
    # Verify documents were processed correctly
    doc_statuses = get_document_statuses(sync_id)
    assert any(status["stage"] == "embedded" for status in doc_statuses)
    
    # Create index from collection
    index_id = create_index_job(sync_id)
    wait_for_index_job_completion(index_id, timeout_minutes=15)
    
    # Check index creation result
    index_job = get_index_job(index_id)
    assert index_job["status"] == "completed"
    
    # Verify OpenSearch index
    index_name = index_job["index_name"]
    doc_count = get_opensearch_doc_count(index_name)
    assert doc_count > 0
    
    # Test vector search functionality 
    query = "privilege escalation technique"
    results = run_vector_search(query, index_name, limit=5)
    assert len(results) > 0
```

### 4. Performance Testing

**Objective**: Verify system performance under various loads and conditions.

**Tools**: Locust, JMeter, custom benchmarking scripts

**Key Performance Metrics**:
- Document processing throughput (docs/min)
- Embedding generation latency
- OpenSearch indexing speed
- Vector search response time under load
- API response times
- Resource utilization (CPU, memory, disk)

**Test Scenarios**:
1. **Load Testing**: Simulate concurrent users accessing the UI and APIs
2. **Stress Testing**: Process 10,000+ documents simultaneously
3. **Endurance Testing**: Run continuous operations for 24+ hours
4. **Scalability Testing**: Measure performance as document volume grows

**Sample Performance Test**:
```python
def test_embedding_throughput():
    # Prepare test data
    test_docs = generate_test_documents(count=1000, avg_size_kb=5)
    
    # Measure embedding throughput
    start_time = time.time()
    embeddings = batch_create_embeddings(test_docs)
    end_time = time.time()
    
    # Calculate metrics
    duration_seconds = end_time - start_time
    docs_per_second = len(test_docs) / duration_seconds
    
    # Log results
    logging.info(f"Embedding throughput: {docs_per_second:.2f} docs/second")
    logging.info(f"Total time for {len(test_docs)} documents: {duration_seconds:.2f} seconds")
    
    # Assert minimum performance
    assert docs_per_second >= 5.0, "Embedding throughput below minimum threshold"
```

### 5. Security Testing

**Objective**: Identify and address security vulnerabilities.

**Tools**: OWASP ZAP, SonarQube, Bandit (Python), npm audit

**Security Focus Areas**:
- API authentication and authorization
- Data encryption (in transit and at rest)
- Input validation and sanitization
- Dependency vulnerabilities
- Container security
- IAM role permissions

**Key Test Cases**:
1. Attempt unauthorized access to APIs
2. Test for SQL injection in database queries
3. Validate SSL/TLS configuration
4. Scan for sensitive information in logs
5. Verify proper S3 bucket permissions
6. Test for cross-site scripting in UI

## Testing Environments

### 1. Development Environment
- Local testing with mocked services
- Docker Compose for integration testing
- Use of test databases and S3 buckets

### 2. Staging Environment
- Full Kubernetes deployment
- Integration with real services (OpenSearch, S3)
- Separate OpenSearch indices for testing
- Populated with sample data

### 3. Production Environment
- Limited testing post-deployment
- Smoke tests to verify critical paths
- Monitoring for anomalies

## Testing Automation

### Continuous Integration Pipeline
- Automated unit tests on all PRs
- Integration tests on main branch commits
- End-to-end tests before staging deployment
- Security scans integrated into pipeline

### Testing Schedule
- Unit tests: Run on every commit
- Integration tests: Run on main branch merge
- End-to-end tests: Run nightly
- Performance tests: Run weekly
- Security scans: Run on main branch merge and weekly

## Bug Tracking and Resolution

### Process
1. All bugs are logged in Jira with severity classification
2. Critical bugs block deployment to production
3. High severity bugs require resolution within 24 hours
4. Medium and low severity bugs are prioritized in backlog

### Bug Classification
- **Critical**: System unavailable or data corruption
- **High**: Major feature broken, significant impact to users
- **Medium**: Feature partially broken, workaround available
- **Low**: Minor issues, minimal impact on functionality

## Testing Documentation

### Required Documentation
- Test plans for each component
- Test cases with expected results
- Bug reports with reproduction steps
- Performance test results and benchmarks
- Security testing reports

## Special Testing Considerations

### Data Privacy
- Use of synthetic or anonymized data for testing
- No production data in non-production environments

### Embedding Model Validation
- Testing for embedding quality and consistency
- Comparison with baseline embeddings
- Verification of vector dimensions and normalization

### OpenSearch Vector Search Quality
- Testing for search relevance and ranking
- Evaluation of semantic search accuracy
- Benchmarking against known good results

## Rollback and Recovery Testing

### Scenarios to Test
1. Database migration failures
2. Failed OpenSearch index creation
3. Partial document processing
4. OpenSearch node failures
5. S3 connectivity issues

### Recovery Procedures
- Testing for index aliasing and rollback
- Validation of recovery from failed jobs
- Verification of job retry mechanisms

## Conclusion

This testing strategy provides a comprehensive approach to ensure the Document Embeddings & Indexing System is reliable, performant, and secure. By implementing this strategy, we can deliver a high-quality system that meets the requirements for automated document processing and integration with the Infinity AI Copilot.
