# Spec §48: "Production should support: containerized services, managed
# PostgreSQL, Redis, object storage, CI/CD." AWS chosen as a concrete,
# fully-documented target (ECS Fargate + RDS + ElastiCache + S3) rather than
# a vague multi-cloud abstraction - spec §63's own "don't over-engineer"
# principle applied to infrastructure, not just application code.
#
# HONESTY NOTE (matches this codebase's standing convention for anything
# unverifiable in the sandbox that wrote it - see docs/architecture.md's
# Phase 25 entry): this Terraform was written and reviewed for internal
# consistency (resource references, variable wiring, security group rules)
# but `terraform plan`/`apply` has never been run against it - this sandbox
# has no Terraform binary and no AWS credentials or network access. Review
# it the way you would code from a contractor who did excellent, careful
# work but has never actually deployed it: real, but run `terraform
# validate` and `plan` yourself before `apply`.

variable "environment" {
  description = "Deployment environment name (e.g. staging, production)."
  type        = string
}

variable "aws_region" {
  description = "AWS region. af-south-1 (Cape Town) is the AWS region geographically closest to Kenya as of this writing; there is no AWS region inside Kenya itself."
  type        = string
  default     = "af-south-1"
}

variable "project_name" {
  type    = string
  default = "farmplatform"
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to spread subnets across."
  type        = number
  default     = 2
}

variable "api_image" {
  description = "Full ECR image URI:tag for the API container. Built and pushed by CI (see .github/workflows/ci.yml) before this is applied."
  type        = string
}

variable "api_cpu" {
  type    = number
  default = 512 # 0.5 vCPU - spec gives no load figures to size against; adjust once real traffic is observed
}

variable "api_memory" {
  type    = number
  default = 1024 # MB
}

variable "api_desired_count" {
  type    = number
  default = 2 # spec §29/§46's multi-replica concerns (Redis-backed rate limiting, etc.) only matter once this is >1
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro" # smallest Graviton instance - right-size after real usage, not guessed capacity
}

variable "db_allocated_storage_gb" {
  type    = number
  default = 20
}

variable "db_name" {
  type    = string
  default = "farmdb"
}

variable "db_username" {
  type    = string
  default = "farm"
}

variable "db_password" {
  description = "Set via TF_VAR_db_password or a tfvars file that is NEVER committed (spec §49: never commit secrets). No default on purpose - this must be supplied explicitly."
  type        = string
  sensitive   = true
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "jwt_secret" {
  description = "Set via TF_VAR_jwt_secret. Same never-commit rule as db_password."
  type        = string
  sensitive   = true
}

variable "domain_name" {
  description = "Public domain for the ALB (e.g. api.example-farm.co.ke). Leave blank to skip ACM/Route53 wiring and use the raw ALB DNS name instead."
  type        = string
  default     = ""
}

variable "cors_origins" {
  description = "Browser origins allowed to call the API, e.g. [\"https://app.example-farm.co.ke\"]. Leave empty to keep the API default (localhost only) - set this for any real deployment."
  type        = list(string)
  default     = []
}

variable "public_site_base_url" {
  description = "Public address of the web app (used for QR-code links etc.), e.g. https://app.example-farm.co.ke. Leave blank to keep the API default (http://localhost:3000)."
  type        = string
  default     = ""
}

variable "extra_environment" {
  description = "Additional NON-secret API settings as NAME = value, e.g. { STORAGE_BACKEND = \"supabase\", SUPABASE_URL = \"https://<ref>.supabase.co\", SUPABASE_STORAGE_BUCKET = \"listing-images\" }."
  type        = map(string)
  default     = {}
}

variable "extra_secrets" {
  description = "Additional SECRET API settings as NAME = value, stored in Secrets Manager (never in the task definition), e.g. { SUPABASE_SECRET_KEY = \"sb_secret_...\", STRIPE_SECRET_KEY = \"...\", MOCK_PAYMENT_SECRET = \"...\" }. Same never-commit rule as db_password."
  type        = map(string)
  default     = {}
  sensitive   = true
}
