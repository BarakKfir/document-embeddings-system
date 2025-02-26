# Elasticsearch logging configuration
apiVersion: v1
kind: ConfigMap
metadata:
  name: logging-config
data:
  logstash.conf: |
    input {
      file {
        path => "/var/log/services/*.log"
        type => "service-logs"
      }
      file {
        path => "/var/log/jobs/*.log"
        type => "job-logs"
      }
    }
    
    filter {
      if [type] == "service-logs" {
        grok {
          match => { "message" => "%{TIMESTAMP_ISO8601:timestamp} %{LOGLEVEL:level} %{GREEDYDATA:message}" }
        }
      }
      if [type] == "job-logs" {
        grok {
          match => { "message" => "%{TIMESTAMP_ISO8601:timestamp} %{WORD:job_name} %{WORD:status} %{GREEDYDATA:message}" }
        }
      }
    }
    
    output {
      elasticsearch {
        hosts => ["elasticsearch-service:9200"]
        index => "logs-%{+YYYY.MM.dd}"
      }
    }

---
# Sample Alert Configuration
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: embedding-system-alerts
spec:
  groups:
  - name: embedding-system
    rules:
    - alert: HighJobFailureRate
      expr: sum(rate(job_failure_total[15m])) / sum(rate(job_total[15m])) > 0.1
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "High job failure rate"
        description: "More than 10% of jobs have been failing in the last 15 minutes"
        
    - alert: S3StorageNearCapacity
      expr: s3_bucket_size_bytes / s3_bucket_limit_bytes > 0.85
      for: 30m
      labels:
        severity: warning
      annotations:
        summary: "S3 bucket near capacity"
        description: "S3 bucket is more than 85% full"
        
    - alert: OpenSearchSlowQueries
      expr: rate(opensearch_search_time_seconds_sum[5m]) / rate(opensearch_search_count[5m]) > 2
      for: 10m
      labels:
        severity: warning
      annotations:
        summary: "Slow OpenSearch queries"
        description: "Average query time is greater than 2 seconds"
        
    - alert: StuckJob
      expr: time() - job_last_update_timestamp > 3600
      for: 15m
      labels:
        severity: critical
      annotations:
        summary: "Job stuck for over an hour"
        description: "A job has been running for more than an hour without updates"
