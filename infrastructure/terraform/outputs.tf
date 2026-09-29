output "alb_dns_name" {
  description = "Point your DNS (or use directly) at this - the load balancer's public address."
  value       = aws_lb.main.dns_name
}

output "db_endpoint" {
  value     = aws_db_instance.main.address
  sensitive = true
}

output "redis_endpoint" {
  value = aws_elasticache_cluster.main.cache_nodes[0].address
}

output "ecr_repository_url" {
  description = "Push CI-built images here (see .github/workflows/ci.yml)."
  value       = aws_ecr_repository.api.repository_url
}

output "documents_bucket" {
  value = aws_s3_bucket.documents.bucket
}

output "acm_certificate_validation_records" {
  description = "If domain_name was set, add these DNS records to validate the ACM certificate before HTTPS will work."
  value       = var.domain_name != "" ? aws_acm_certificate.main[0].domain_validation_options : null
}
