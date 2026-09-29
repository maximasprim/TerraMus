# Spec §48: "Production should support: ... managed PostgreSQL, Redis,
# object storage." These three resources are exactly that - RDS instead of
# a self-hosted Postgres container, ElastiCache instead of a Redis
# container, S3 instead of local disk for the object storage abstraction
# spec §2 asks for (livestock photos/videos, invoices, veterinary
# documents, etc.).

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-${var.environment}-db"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "main" {
  identifier             = "${var.project_name}-${var.environment}-db"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = var.db_instance_class
  allocated_storage      = var.db_allocated_storage_gb
  storage_encrypted      = true
  db_name                = var.db_name
  username               = var.db_username
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]

  # spec §74 backup & recovery.
  backup_retention_period   = 7
  backup_window             = "02:00-03:00" # UTC - off-peak for Africa/Nairobi (spec §56 default timezone), roughly 5-6am local
  multi_az                  = var.environment == "production"
  deletion_protection       = var.environment == "production"
  skip_final_snapshot       = var.environment != "production"
  final_snapshot_identifier = var.environment == "production" ? "${var.project_name}-${var.environment}-final" : null

  tags = { Name = "${var.project_name}-${var.environment}-db" }
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project_name}-${var.environment}-redis"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_cluster" "main" {
  cluster_id         = "${var.project_name}-${var.environment}-redis"
  engine             = "redis"
  engine_version     = "7.1"
  node_type          = var.redis_node_type
  num_cache_nodes    = 1 # single node: this app's Redis usage (cache/sessions/rate-limit/queues per spec §2) tolerates a cold cache on failover; not a durability-critical store
  port               = 6379
  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]
  tags               = { Name = "${var.project_name}-${var.environment}-redis" }
}

# Spec §2 object storage abstraction - one bucket, prefixed by document
# type at the application layer (the API's storage abstraction decides
# "livestock-photos/", "invoices/", etc. as key prefixes, not separate
# buckets, keeping bucket policy/lifecycle rules in one place).
resource "aws_s3_bucket" "documents" {
  bucket = "${var.project_name}-${var.environment}-documents"
  tags   = { Name = "${var.project_name}-${var.environment}-documents" }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration {
    status = "Enabled" # spec §74 backup & recovery - object storage backups via versioning, not a separate backup product
  }
}

resource "aws_ecr_repository" "api" {
  name                 = "${var.project_name}-api"
  image_tag_mutability = "IMMUTABLE" # a given tag (e.g. a git SHA) always points at the same image - no silent redeploys of "latest"
  image_scanning_configuration {
    scan_on_push = true
  }
}
