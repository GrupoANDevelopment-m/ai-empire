output "primary_alb_dns" { value = aws_lb.primary.dns_name }
output "primary_api_url" { value = "https://${aws_lb.primary.dns_name}" }
output "rds_endpoint" { value = module.rds_primary.endpoint }
output "redis_endpoint" { value = module.redis.primary_endpoint }
