# main.tf - Infrastructure as Code for Document Embeddings & Indexing System

# Provider configuration
provider "aws" {
  region = var.aws_region
}

provider "kubernetes" {
  config_path = var.k8s_config_path
}

# S3 storage for documents
resource "aws_s3_bucket" "document_storage" {
  bucket = var.s3_bucket_name
  acl    = "private"

  versioning {
    enabled = true
  }

  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }

  lifecycle_rule {
    enabled = true

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    expiration {
      days = 365
    }
  }

  tags = {
    Name        = "Document Embeddings Storage"
    Environment = var.environment
    Project     = "Infinity AI Copilot"
  }
}

# IAM roles for services
resource "aws_iam_role" "sync_service_role" {
  name = "${var.environment}-sync-service-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "eks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "sync_service_policy" {
  name   = "${var.environment}-sync-service-policy"
  role   = aws_iam_role.sync_service_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:DeleteObject"
        ]
        Effect   = "Allow"
        Resource = [
          "${aws_s3_bucket.document_storage.arn}",
          "${aws_s3_bucket.document_storage.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role" "index_service_role" {
  name = "${var.environment}-index-service-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "eks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "index_service_policy" {
  name   = "${var.environment}-index-service-policy"
  role   = aws_iam_role.index_service_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Effect   = "Allow"
        Resource = [
          "${aws_s3_bucket.document_storage.arn}",
          "${aws_s3_bucket.document_storage.arn}/valid_index_collections/*"
        ]
      }
    ]
  })
}

# RDS database for management APIs
resource "aws_db_instance" "management_db" {
  identifier             = "${var.environment}-doc-sync-db"
  engine                 = "postgres"
  engine_version         = "13.7"
  instance_class         = "db.t3.small"
  allocated_storage      = 20
  storage_type           = "gp2"
  multi_az               = var.environment == "production"
  name                   = "docmanagement"
  username               = var.db_username
  password               = var.db_password
  db_subnet_group_name   = var.db_subnet_group
  vpc_security_group_ids = [var.db_security_group_id]
  skip_final_snapshot    = true
  backup_retention_period = 7
  deletion_protection    = var.environment == "production"

  tags = {
    Name        = "${var.environment} Document Management DB"
    Environment = var.environment
    Project     = "Infinity AI Copilot"
  }
}

# Kubernetes deployments for services
resource "kubernetes_namespace" "doc_sync" {
  metadata {
    name = "document-sync"
  }
}

# Kubernetes Secrets
resource "kubernetes_secret" "api_secrets" {
  metadata {
    name      = "api-secrets"
    namespace = kubernetes_namespace.doc_sync.metadata[0].name
  }

  data = {
    DB_USERNAME      = var.db_username
    DB_PASSWORD      = var.db_password
    DB_HOST          = aws_db_instance.management_db.address
    DB_PORT          = aws_db_instance.management_db.port
    DB_NAME          = aws_db_instance.management_db.name
    AWS_ACCESS_KEY   = var.aws_access_key
    AWS_SECRET_KEY   = var.aws_secret_key
    INTERNAL_API_KEY = var.internal_api_key
    AZURE_OPENAI_KEY = var.azure_openai_key
  }
}

# Kubernetes service account for jobs
resource "kubernetes_service_account" "job_service_account" {
  metadata {
    name      = "job-service-account"
    namespace = kubernetes_namespace.doc_sync.metadata[0].name
    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.sync_service_role.arn
    }
  }
}

# Sync Management API Deployment
resource "kubernetes_deployment" "sync_mgmt_api" {
  metadata {
    name      = "sync-management-api"
    namespace = kubernetes_namespace.doc_sync.metadata[0].name
  }

  spec {
    replicas = 2

    selector {
      match_labels = {
        app = "sync-management-api"
      }
    }

    template {
      metadata {
        labels = {
          app = "sync-management-api"
        }
      }

      spec {
        container {
          name  = "api"
          image = "${var.container_registry}/sync-management-api:${var.api_version}"
          
          port {
            container_port = 8000
          }

          env_from {
            secret_ref {
              name = kubernetes_secret.api_secrets.metadata[0].name
            }
          }

          env {
            name  = "ENVIRONMENT"
            value = var.environment
          }

          env {
            name  = "S3_BUCKET"
            value = aws_s3_bucket.document_storage.bucket
          }

          resources {
            limits = {
              cpu    = "500m"
              memory = "512Mi"
            }
            requests = {
              cpu    = "100m"
              memory = "256Mi"
            }
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 30
            period_seconds        = 15
          }
        }
      }
    }
  }
}

# Index Management API Deployment
resource "kubernetes_deployment" "index_mgmt_api" {
  metadata {
    name      = "index-management-api"
    namespace = kubernetes_namespace.doc_sync.metadata[0].name
  }

  spec {
    replicas = 2

    selector {
      match_labels = {
        app = "index-management-api"
      }
    }

    template {
      metadata {
        labels = {
          app = "index-management-api"
        }
      }

      spec {
        container {
          name  = "api"
          image = "${var.container_registry}/index-management-api:${var.api_version}"
          
          port {
            container_port = 8000
          }

          env_from {
            secret_ref {
              name = kubernetes_secret.api_secrets.metadata[0].name
            }
          }

          env {
            name  = "ENVIRONMENT"
            value = var.environment
          }

          env {
            name  = "OPENSEARCH_ENDPOINT"
            value = var.opensearch_endpoint
          }

          resources {
            limits = {
              cpu    = "500m"
              memory = "512Mi"
            }
            requests = {
              cpu    = "100m"
              memory = "256Mi"
            }
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 30
            period_seconds        = 15
          }
        }
      }
    }
  }
}

# Service for Sync Management API
resource "kubernetes_service" "sync_mgmt_api_service" {
  metadata {
    name      = "sync-management-api"
    namespace = kubernetes_namespace.doc_sync.metadata[0].name
  }

  spec {
    selector = {
      app = kubernetes_deployment.sync_mgmt_api.spec[0].template[0].metadata[0].labels.app
    }

    port {
      port        = 80
      target_port = 8000
    }
  }
}

# Service for Index Management API
resource "kubernetes_service" "index_mgmt_api_service" {
  metadata {
    name      = "index-management-api"
    namespace = kubernetes_namespace.doc_sync.metadata[0].name
  }

  spec {
    selector = {
      app = kubernetes_deployment.index_mgmt_api.spec[0].template[0].metadata[0].labels.app
    }

    port {
      port        = 80
      target_port = 8000
    }
  }
}

# CronJob for Source Sync (MITRE example)
resource "kubernetes_cron_job" "mitre_sync_job" {
  metadata {
    name      = "mitre-sync-job"
    namespace = kubernetes_namespace.doc_sync.metadata[0].name
  }

  spec {
    schedule = "0 0 * * 1"  # Weekly on Monday
    job_template {
      metadata {
        name = "mitre-sync"
      }
      spec {
        template {
          metadata {
            name = "mitre-sync"
          }
          spec {
            service_account_name = kubernetes_service_account.job_service_account.metadata[0].name
            container {
              name    = "source-sync"
              image   = "${var.container_registry}/source-sync:${var.job_version}"
              command = ["/app/source_sync.py"]
              
              env_from {
                secret_ref {
                  name = kubernetes_secret.api_secrets.metadata[0].name
                }
              }

              env {
                name  = "SOURCE"
                value = "mitre"
              }

              env {
                name  = "S3_BUCKET"
                value = aws_s3_bucket.document_storage.bucket
              }

              env {
                name  = "API_BASE_URL"
                value = "http://sync-management-api"
              }

              resources {
                limits = {
                  cpu    = "500m"
                  memory = "512Mi"
                }
                requests = {
                  cpu    = "100m"
                  memory = "256Mi"
                }
              }
            }
            restart_policy = "OnFailure"
          }
        }
      }
    }
  }
}

# CronJob for SyncWatcher
resource "kubernetes_cron_job" "sync_watcher_job" {
  metadata {
    name      = "sync-watcher-job"
    namespace = kubernetes_namespace.doc_sync.metadata[0].name
  }

  spec {
    schedule = "*/1 * * * *"  # Every minute
    job_template {
      metadata {
        name = "sync-watcher"
      }
      spec {
        template {
          metadata {
            name = "sync-watcher"
          }
          spec {
            container {
              name    = "sync-watcher"
              image   = "${var.container_registry}/sync-watcher:${var.job_version}"
              command = ["/app/sync_watcher.py"]
              
              env_from {
                secret_ref {
                  name = kubernetes_secret.api_secrets.metadata[0].name
                }
              }

              env {
                name  = "API_BASE_URL"
                value = "http://sync-management-api"
              }

              resources {
                limits = {
                  cpu    = "200m"
                  memory = "256Mi"
                }
                requests = {
                  cpu    = "50m"
                  memory = "128Mi"
                }
              }
            }
            restart_policy = "OnFailure"
          }
        }
      }
    }
  }
}

# More CronJobs would be defined similarly for:
# - admin_guides_sync_job
# - secure_knowledge_sync_job
# - cpr_blogs_sync_job
# - jira_tickets_sync_job
# - storage_cleanup_job
# - index_creator_job
# - index_cleanup_job

# Output values
output "s3_bucket_name" {
  value = aws_s3_bucket.document_storage.bucket
}

output "database_endpoint" {
  value = aws_db_instance.management_db.address
}

output "sync_api_service_name" {
  value = kubernetes_service.sync_mgmt_api_service.metadata[0].name
}

output "index_api_service_name" {
  value = kubernetes_service.index_mgmt_api_service.metadata[0].name
}
