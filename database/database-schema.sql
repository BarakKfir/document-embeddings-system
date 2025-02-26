-- Database schema for Sync Management and Index Management

-- Create schema
CREATE SCHEMA IF NOT EXISTS doc_management;
SET search_path TO doc_management;

-- Create extension for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enum types
CREATE TYPE job_status AS ENUM ('pending', 'running', 'completed', 'failed', 'cancelled');
CREATE TYPE document_status AS ENUM ('pending', 'downloading', 'downloaded', 'sanitizing', 'sanitized', 'embedding', 'embedded', 'failed', 'skipped');
CREATE TYPE document_stage AS ENUM ('original', 'sanitized', 'embedded');

-- Sync jobs table
CREATE TABLE sync_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source VARCHAR(50) NOT NULL,
    status job_status NOT NULL DEFAULT 'pending',
    progress NUMERIC(5, 2) DEFAULT 0,
    error_message TEXT,
    fresh_start BOOLEAN NOT NULL DEFAULT FALSE,
    prod_ready BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    created_by VARCHAR(100) NOT NULL,
    prod_ready_at TIMESTAMP WITH TIME ZONE,
    prod_ready_by VARCHAR(100),
    
    -- Metrics
    documents_total INTEGER DEFAULT 0,
    documents_processed INTEGER DEFAULT 0,
    documents_success INTEGER DEFAULT 0,
    documents_failed INTEGER DEFAULT 0
);

-- Create indexes for sync_jobs
CREATE INDEX idx_sync_jobs_source ON sync_jobs(source);
CREATE INDEX idx_sync_jobs_status ON sync_jobs(status);
CREATE INDEX idx_sync_jobs_created_at ON sync_jobs(created_at);

-- Document status table
CREATE TABLE document_statuses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sync_id UUID NOT NULL REFERENCES sync_jobs(id) ON DELETE CASCADE,
    document_id VARCHAR(255) NOT NULL,
    status document_status NOT NULL DEFAULT 'pending',
    stage document_stage,
    path VARCHAR(1024),
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    processing_time NUMERIC(10, 2), -- in seconds
    
    -- Unique constraint to avoid duplicates within a sync
    UNIQUE (sync_id, document_id)
);

-- Create indexes for document_statuses
CREATE INDEX idx_document_statuses_sync_id ON document_statuses(sync_id);
CREATE INDEX idx_document_statuses_status ON document_statuses(status);
CREATE INDEX idx_document_statuses_stage ON document_statuses(stage);

-- Job logs table
CREATE TABLE job_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sync_id UUID NOT NULL REFERENCES sync_jobs(id) ON DELETE CASCADE,
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    message TEXT,
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Create indexes for job_logs
CREATE INDEX idx_job_logs_sync_id ON job_logs(sync_id);
CREATE INDEX idx_job_logs_job_type ON job_logs(job_type);
CREATE INDEX idx_job_logs_created_at ON job_logs(created_at);

-- Source configuration table
CREATE TABLE source_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source VARCHAR(50) NOT NULL UNIQUE,
    url VARCHAR(1024) NOT NULL,
    auth_type VARCHAR(50),
    auth_config JSONB,
    schedule VARCHAR(50), -- cron schedule
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    config_json JSONB, -- Additional source-specific configuration
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_sync_id UUID REFERENCES sync_jobs(id),
    max_docs_per_sync INTEGER DEFAULT 5000
);

-- OpenSearch indices table for Index Management
CREATE TABLE opensearch_indices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    environment VARCHAR(20) NOT NULL, -- 'staging' or 'production'
    region VARCHAR(20) NOT NULL, -- 'eu' or 'us'
    source VARCHAR(50) NOT NULL,
    index_name VARCHAR(255) NOT NULL,
    alias_name VARCHAR(255),
    status VARCHAR(50) NOT NULL, -- 'created', 'active', 'deprecated', 'deleted'
    sync_id UUID REFERENCES sync_jobs(id),
    document_count INTEGER DEFAULT 0,
    size_bytes BIGINT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMP WITH TIME ZONE,
    deprecated_at TIMESTAMP WITH TIME ZONE,
    deleted_at TIMESTAMP WITH TIME ZONE,
    
    -- Additional metadata
    shards INTEGER DEFAULT 5,
    replicas INTEGER DEFAULT 1,
    metadata JSONB,
    
    -- Unique constraint for environment, region, source and index name
    UNIQUE (environment, region, source, index_name)
);

-- Create indexes for opensearch_indices
CREATE INDEX idx_opensearch_indices_status ON opensearch_indices(status);
CREATE INDEX idx_opensearch_indices_env_region ON opensearch_indices(environment, region);
CREATE INDEX idx_opensearch_indices_source ON opensearch_indices(source);

-- Alias actions log table
CREATE TABLE alias_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    environment VARCHAR(20) NOT NULL,
    region VARCHAR(20) NOT NULL,
    source VARCHAR(50) NOT NULL,
    alias_name VARCHAR(255) NOT NULL,
    old_index_name VARCHAR(255),
    new_index_name VARCHAR(255) NOT NULL,
    action_type VARCHAR(50) NOT NULL, -- 'create', 'update', 'delete'
    performed_by VARCHAR(100) NOT NULL,
    performed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    reason TEXT,
    status VARCHAR(50) NOT NULL -- 'success', 'failed'
);

-- Create indexes for alias_actions
CREATE INDEX idx_alias_actions_env_region ON alias_actions(environment, region);
CREATE INDEX idx_alias_actions_source ON alias_actions(source);
CREATE INDEX idx_alias_actions_performed_at ON alias_actions(performed_at);

-- Index jobs table for tracking OpenSearch index creation jobs
CREATE TABLE index_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    environment VARCHAR(20) NOT NULL,
    region VARCHAR(20) NOT NULL,
    source VARCHAR(50) NOT NULL,
    job_type VARCHAR(50) NOT NULL, -- 'create', 'cleanup'
    status job_status NOT NULL DEFAULT 'pending',
    error_message TEXT,
    index_name VARCHAR(255),
    sync_id UUID REFERENCES sync_jobs(id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    created_by VARCHAR(100) NOT NULL
);

-- Create indexes for index_jobs
CREATE INDEX idx_index_jobs_env_region ON index_jobs(environment, region);
CREATE INDEX idx_index_jobs_source ON index_jobs(source);
CREATE INDEX idx_index_jobs_status ON index_jobs(status);

-- Add versioning to track schema changes
CREATE TABLE schema_versions (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) NOT NULL,
    applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    description TEXT
);

-- Insert initial version
INSERT INTO schema_versions (version, description) 
VALUES ('1.0.0', 'Initial schema for document sync and index management');

-- Create users and permissions
-- App user for services
CREATE USER doc_sync_app WITH PASSWORD 'app_password_placeholder';
GRANT USAGE ON SCHEMA doc_management TO doc_sync_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA doc_management TO doc_sync_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA doc_management TO doc_sync_app;

-- Read-only user for reporting
CREATE USER doc_sync_readonly WITH PASSWORD 'readonly_password_placeholder';
GRANT USAGE ON SCHEMA doc_management TO doc_sync_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA doc_management TO doc_sync_readonly;

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = NOW(); 
   RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updating timestamps
CREATE TRIGGER update_sync_jobs_timestamp
BEFORE UPDATE ON sync_jobs
FOR EACH ROW EXECUTE PROCEDURE update_timestamp();

CREATE TRIGGER update_document_statuses_timestamp
BEFORE UPDATE ON document_statuses
FOR EACH ROW EXECUTE PROCEDURE update_timestamp();

CREATE TRIGGER update_source_configs_timestamp
BEFORE UPDATE ON source_configs
FOR EACH ROW EXECUTE PROCEDURE update_timestamp();

CREATE TRIGGER update_index_jobs_timestamp
BEFORE UPDATE ON index_jobs
FOR EACH ROW EXECUTE PROCEDURE update_timestamp();

-- Function to update sync_jobs progress automatically
CREATE OR REPLACE FUNCTION update_sync_progress()
RETURNS TRIGGER AS $$
BEGIN
   -- If a document status was updated
   IF TG_TABLE_NAME = 'document_statuses' THEN
      -- Update the document counts for the related sync job
      WITH counts AS (
         SELECT 
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE status NOT IN ('pending', 'downloading')) AS processed,
            COUNT(*) FILTER (WHERE status = 'embedded') AS success,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed
         FROM document_statuses
         WHERE sync_id = NEW.sync_id
      )
      UPDATE sync_jobs
      SET 
         documents_total = counts.total,
         documents_processed = counts.processed,
         documents_success = counts.success,
         documents_failed = counts.failed,
         progress = CASE 
            WHEN counts.total > 0 THEN 
               (counts.processed::NUMERIC / counts.total::NUMERIC) * 100
            ELSE 0
         END
      FROM counts
      WHERE sync_jobs.id = NEW.sync_id;
   END IF;
   
   RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update sync progress
CREATE TRIGGER update_sync_progress_trigger
AFTER INSERT OR UPDATE ON document_statuses
FOR EACH ROW EXECUTE PROCEDURE update_sync_progress();

-- Sample data for source configs
INSERT INTO source_configs (source, url, schedule, config_json)
VALUES 
('mitre', 'https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json', '0 0 * * 1', '{"parser_type": "json"}'),
('admin_guides', 'https://support.checkpoint.com/sitemaps/documentation-sitemap-index.xml', '0 0 * * 2', '{"parser_type": "sitemap"}'),
('secure_knowledge', 'https://support.checkpoint.com/results/sk/', '0 0 * * 3', '{"parser_type": "html"}'),
('cpr_blogs', 'https://research.checkpoint.com/wp-json/wp/v2/posts/', '0 0 * * 4', '{"parser_type": "json"}'),
('jira_tickets', 'https://jira-prd.checkpoint.com/', '0 0 * * 5', '{"parser_type": "jira", "auth_required": true}');
