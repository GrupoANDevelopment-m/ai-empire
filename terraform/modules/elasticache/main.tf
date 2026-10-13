# ElastiCache Redis Global for AI Empire
resource "aws_elasticache_global_replication_group" "main" {
  global_replication_group_id_suffix = var.name
  description                        = "AI Empire global cache"
  
  primary_replication_group_id = aws_elasticache_replication_group.primary.id
}

resource "aws_elasticache_replication_group" "primary" {
  replication_group_id = "${var.name}-primary"
  replication_group_description = "Primary cluster (${var.primary_region})"
  engine                = "redis"
  engine_version        = "7.1"
  node_type             = "cache.r7g.large"
  number_cache_clusters = 3
  
  port                       = 6379
  parameter_group_name       = "default.redis7"
  subnet_group_name          = aws_elasticache_subnet_group.main.name
  security_group_ids         = [var.redis_security_group_id]
  
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = var.auth_token
  
  automatic_failover_enabled = true
  multi_az_enabled           = true
  
  snapshot_retention_limit = 7
  snapshot_window          = "03:00-05:00"
  
  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.redis.name
    destination_type = "cloudwatch-logs"
    log_format       = "text"
    log_type         = "slow-log"
  }
  
  tags = var.tags
}

resource "aws_elasticache_subnet_group" "main" {
  name       = var.name
  subnet_ids = var.private_subnets
  tags       = var.tags
}

resource "aws_cloudwatch_log_group" "redis" {
  name              = "/aws/elasticache/${var.name}"
  retention_in_days = 30
  tags              = var.tags
}
