terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  # Backend configured per-region in backend-{region}.tfvars
  # Run: terraform init -backend-config=backend-eu.tfvars
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = "ai-empire"
      Environment = var.environment
      ManagedBy   = "terraform"
      Owner       = var.owner_email
    }
  }
}

variable "region" {
  description = "AWS region to deploy in"
  type        = string
  default     = "eu-west-1"
}

variable "environment" {
  description = "Environment name (production, staging, dev)"
  type        = string
  default     = "production"
}

variable "owner_email" {
  description = "Owner email for tagging and alerts"
  type        = string
  default     = "ops@ai-empire.example.com"
}

variable "domain" {
  description = "Public domain for the deployment (e.g. ai.example.com)"
  type        = string
  default     = ""
}

# ── Networking ──────────────────────────────────────────────────────────────
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.5"
  name    = "ai-empire-${var.environment}"
  cidr    = "10.0.0.0/16"

  azs             = ["${var.region}a", "${var.region}b", "${var.region}c"]
  public_subnets  = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  private_subnets = ["10.0.10.0/24", "10.0.11.0/24", "10.0.12.0/24"]
  database_subnets = ["10.0.20.0/24", "10.0.21.0/24", "10.0.22.0/24"]
  intra_subnets   = ["10.0.30.0/24", "10.0.31.0/24", "10.0.32.0/24"]  # EFS

  enable_nat_gateway     = true
  single_nat_gateway     = var.environment != "production"  # save $ in non-prod
  enable_vpn_gateway      = false
  enable_dns_hostnames    = true
  enable_dns_support      = true

  # Flow logs for security audit
  enable_flow_log                      = true
  create_flow_log_cloudwatch_log_group = true
  create_flow_log_iam_role             = true

  tags = {
    "kubernetes.io/cluster/${var.environment}" = "shared"
  }
}

# ── Security: GuardDuty for threat detection ───────────────────────────────
resource "aws_guardduty_detector" "this" {
  count = var.environment == "production" ? 1 : 0
  enable = true
  finding_publishing_frequency = "FIFTEEN_MINUTES"
}

# ── Security: AWS WAF on the ALB ────────────────────────────────────────────
resource "aws_wafv2_web_acl" "main" {
  name  = "ai-empire-${var.environment}"
  scope = "REGIONAL"
  default_action {
    allow {}
  }
  rule {
    name     = "RateLimit"
    priority = 1
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = 2000  # 2000 req per 5 min per IP
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "RateLimit"
      sampled_requests_enabled   = true
    }
  }
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 2
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name  = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "CommonRuleSet"
      sampled_requests_enabled   = true
    }
  }
  rule {
    name     = "AWSManagedRulesSQLiRuleSet"
    priority = 3
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesSQLiRuleSet"
        vendor_name  = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "SQLiRuleSet"
      sampled_requests_enabled   = true
    }
  }
  rule {
    name     = "GeoBlock"
    priority = 4
    action {
      block {}
    }
    statement {
      geo_match_statement {
        country_codes = var.blocked_country_codes
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "GeoBlock"
      sampled_requests_enabled   = true
    }
  }
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "ai-empire-waf"
    sampled_requests_enabled   = true
  }
}

variable "blocked_country_codes" {
  type    = list(string)
  default = []
  # e.g. ["KP", "IR"] for sanctions compliance
}

# ── ECS Fargate cluster ─────────────────────────────────────────────────────
module "ecs" {
  source  = "terraform-aws-modules/ecs/aws"
  version = "~> 5.9"
  cluster_name = "ai-empire-${var.environment}"

  fargate_capacity_providers = {
    FARGATE = {
      default_capacity_provider_strategy = {
        weight = 100
      }
    }
    FARGATE_SPOT = {
      default_capacity_provider_strategy = {
        weight = 50
      }
    }
  }

  services = {
    langgraph = {
      cpu    = 2048
      memory = 4096
      container_definitions = {
        langgraph = {
          cpu       = 2048
          memory    = 4096
          essential = true
          image     = "ghcr.io/GrupoANDevelopment-m/ai-empire/orchestrator:latest"
          essential = true
          port_mappings = [
            {
              name          = "langgraph"
              container_port = 8123
              protocol      = "tcp"
            }
          ]
          environment = [
            { name = "DATABASE_URL", value = "postgresql://empire:${module.rds.db_password}@${module.rds.endpoint}/ai_empire" },
            { name = "REDIS_URL", value = "redis://${module.redis.endpoint}:6379/0" },
            { name = "OTEL_EXPORTER_OTLP_ENDPOINT", value = "http://otel-collector:4317" },
            { name = "SECRET_KEY", value = var.langgraph_secret_key },
          ]
          secrets = [
            { name = "ANTHROPIC_API_KEY", valueFrom = "/ai-empire/anthropic-key" },
            { name = "OPENAI_API_KEY", valueFrom = "/ai-empire/openai-key" },
          ]
        }
      }
      desired_count    = var.environment == "production" ? 3 : 1
      min_capacity     = 1
      max_capacity     = 10
      cpu              = 2048
      memory           = 4096
      assign_public_ip = false
      health_check_grace_period_seconds = 60
      deployment_minimum_healthy_percent = 50
      deployment_maximum_percent         = 200
      load_balancer = {
        service = {
          target_group_arn = module.alb.target_group_arns["langgraph"]
          container_name   = "langgraph"
          container_port   = 8123
        }
      }
      subnet_ids = module.vpc.private_subnets
      security_group_ids = [module.ecs_sg.id]
    }
  }
}

# ── RDS PostgreSQL (multi-AZ in production) ────────────────────────────────
module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  version = "~> 6.5"
  identifier = "ai-empire-${var.environment}"
  engine     = "postgres"
  engine_version = "16.4"
  engine_lifecycle_support = "extended-support-disabled"

  family = "postgres16"
  major_engine_version = "16"

  instance_class    = var.environment == "production" ? "db.r7g.large" : "db.t4g.medium"
  allocated_storage = 100
  max_allocated_storage = 1000
  storage_type      = "gp3"
  storage_encrypted = true
  kms_key_id        = aws_kms_key.rds.arn

  db_name  = "ai_empire"
  username = "empire"
  port     = 5432

  multi_az               = var.environment == "production"
  db_subnet_group_name   = module.vpc.database_subnet_group_name
  vpc_security_group_ids = [module.rds_sg.id]

  # Backup
  backup_retention_period = var.environment == "production" ? 35 : 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"
  copy_tags_to_snapshot   = true
  deletion_protection     = var.environment == "production"

  # Performance Insights
  performance_insights_enabled    = true
  performance_insights_kms_key_id = aws_kms_key.rds.arn
  performance_insights_retention_period = 7

  # Enhanced monitoring (CloudWatch metrics at 15s granularity)
  monitoring_interval = 15
  monitoring_role_arn = aws_iam_role.rds_monitoring.arn

  # pgvector extension support
  parameters = [
    { name = "shared_preload_libraries", value = "vector", apply_method = "pending-reboot" },
  ]

  tags = {
    BackupSchedule = "daily-0300"
  }
}

resource "random_password" "rds" {
  length  = 32
  special = false
}

# ── ElastiCache Redis ───────────────────────────────────────────────────────
module "redis" {
  source  = "terraform-aws-modules/elasticache/aws"
  version = "~> 4.4"
  cluster_id = "ai-empire-${var.environment}"
  engine     = "redis"
  engine_version = "7.1"

  node_type           = var.environment == "production" ? "cache.r7g.large" : "cache.t4g.medium"
  num_cache_nodes     = var.environment == "production" ? 3 : 1

  maintenance_window       = "Mon:05:00-Mon:06:00"
  snapshot_retention_limit = 7
  apply_immediately        = false

  subnet_ids = module.vpc.private_subnets
  vpc_security_group_ids = [module.redis_sg.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token_enabled         = true
  auth_token                 = random_password.redis.result

  apply_immediately_for_changes = false
}

resource "random_password" "redis" {
  length  = 32
  special = false
}

# ── ALB with WAF ────────────────────────────────────────────────────────────
module "alb" {
  source  = "terraform-aws-modules/alb/aws"
  version = "~> 9.0"
  load_balancer_name = "ai-empire-${var.environment}"

  vpc_id  = module.vpc.vpc_id
  subnets = module.vpc.public_subnets
  security_groups = [module.alb_sg.id]

  # HTTPS only
  http_tcp_listeners = []  # disable HTTP
  https_listeners = [
    {
      port               = 443
      protocol           = "HTTPS"
      certificate_arn    = var.acm_certificate_arn
      action_type        = "forward"
      target_group_index = 0
    }
  ]

  # Redirect HTTP to HTTPS
  http_tcp_listener = {
    port     = 80
    protocol = "HTTP"
    action   = "redirect"
    redirect = {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }

  # Web ACL attached
  web_acl_arn = aws_wafv2_web_acl.main.arn

  access_logs = {
    bucket = module.log_bucket.bucket
    prefix = "alb"
  }
}

# S3 bucket for ALB logs
module "log_bucket" {
  source = "terraform-aws-modules/s3-bucket/aws"
  version = "~> 4.1"
  bucket = "ai-empire-alb-logs-${var.environment}-${data.aws_caller_identity.current.account_id}"
  acl    = "private"

  versioning = {
    enabled = true
  }

  lifecycle_rule = [
    {
      id      = "expire-old-logs"
      enabled = true
      expiration = {
        days = 90
      }
      transition = [
        {
          days          = 30
          storage_class = "STANDARD_IA"
        },
        {
          days          = 60
          storage_class = "GLACIER"
        }
      ]
    }
  ]

  server_side_encryption_configuration = {
    rule = {
      apply_server_side_encryption_by_default = {
        sse_algorithm = "AES256"
      }
    }
  }

  force_destroy = var.environment != "production"
}

data "aws_caller_identity" "current" {}

# ── KMS keys for encryption ─────────────────────────────────────────────────
resource "aws_kms_key" "rds" {
  description             = "KMS for RDS encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

resource "aws_kms_key" "logs" {
  description             = "KMS for log encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

# ── IAM roles ───────────────────────────────────────────────────────────────
resource "aws_iam_role" "rds_monitoring" {
  name = "ai-empire-rds-monitoring-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "monitoring.rds.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# ── Secrets (Anthropic + OpenAI keys, JWT secret) ───────────────────────────
resource "aws_secretsmanager_secret" "langgraph_secret_key" {
  name                    = "ai-empire/langgraph-secret-key"
  kms_key_id              = aws_kms_key.logs.arn
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "langgraph_secret_key" {
  secret_id     = aws_secretsmanager_secret.langgraph_secret_key.id
  secret_string = random_password.jwt_secret.result
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "anthropic_key" {
  name                    = "ai-empire/anthropic-key"
  kms_key_id              = aws_kms_key.logs.arn
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret" "openai_key" {
  name                    = "ai-empire/openai-key"
  kms_key_id              = aws_kms_key.logs.arn
  recovery_window_in_days = 7
}

variable "langgraph_secret_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for HTTPS"
  type        = string
  default     = ""
}

# ── Security groups ──────────────────────────────────────────────────────────
module "alb_sg" {
  source = "terraform-aws-modules/security-group/aws"
  version = "~> 5.1"
  name        = "ai-empire-alb-${var.environment}"
  description = "Security group for ALB"
  vpc_id      = module.vpc.vpc_id
  ingress_with_cidr_blocks = [
    { from_port = 80, to_port = 80, protocol = "tcp", cidr_blocks = "0.0.0.0/0" },
    { from_port = 443, to_port = 443, protocol = "tcp", cidr_blocks = "0.0.0.0/0" },
  ]
  egress_with_cidr_blocks = [
    { from_port = 0, to_port = 0, protocol = "-1", cidr_blocks = "0.0.0.0/0" },
  ]
}

module "ecs_sg" {
  source = "terraform-aws-modules/security-group/aws"
  version = "~> 5.1"
  name        = "ai-empire-ecs-${var.environment}"
  description = "Security group for ECS tasks"
  vpc_id      = module.vpc.vpc_id
  ingress_with_source_security_group_id = [
    { from_port = 8123, to_port = 8123, protocol = "tcp", source_security_group_id = module.alb_sg.security_group_id },
  ]
  egress_with_cidr_blocks = [
    { from_port = 0, to_port = 0, protocol = "-1", cidr_blocks = "0.0.0.0/0" },
  ]
}

module "rds_sg" {
  source = "terraform-aws-modules/security-group/aws"
  version = "~> 5.1"
  name        = "ai-empire-rds-${var.environment}"
  description = "Security group for RDS"
  vpc_id      = module.vpc.vpc_id
  ingress_with_source_security_group_id = [
    { from_port = 5432, to_port = 5432, protocol = "tcp", source_security_group_id = module.ecs_sg.security_group_id },
  ]
}

module "redis_sg" {
  source = "terraform-aws-modules/security-group/aws"
  version = "~> 5.1"
  name        = "ai-empire-redis-${var.environment}"
  description = "Security group for Redis"
  vpc_id      = module.vpc.vpc_id
  ingress_with_source_security_group_id = [
    { from_port = 6379, to_port = 6379, protocol = "tcp", source_security_group_id = module.ecs_sg.security_group_id },
  ]
}

# ── CloudFront (CDN + WAF) ───────────────────────────────────────────────────
resource "aws_cloudfront_distribution" "main" {
  enabled             = true
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  price_class         = "PriceClass_100"  # US/EU only
  comment             = "AI Empire CDN"
  default_cache_behavior {
    target_origin_id       = "alb"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]
    compress               = true
    cache_policy_id        = aws_cloudfront_cache_policy.api.id
  }
  origin {
    domain_name = module.alb.lb_dns_name
    origin_id   = "alb"
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }
  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }
  viewer_certificate {
    acm_certificate_arn      = var.acm_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
  web_acl_id = aws_wafv2_web_acl.main.arn
  aliases    = var.domain != "" ? [var.domain] : []
}

resource "aws_cloudfront_cache_policy" "api" {
  name        = "ai-empire-api-${var.environment}"
  comment     = "Cache policy for API responses (5min TTL, vary by Authorization)"
  default_ttl = 0
  max_ttl     = 300
  min_ttl     = 0
  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "whitelist"
      headers = ["Authorization", "Accept", "Content-Type"]
    }
    query_strings_config {
      query_string_behavior = "whitelist"
      query_strings = ["limit", "offset"]
    }
  }
}

# ── Route53 ─────────────────────────────────────────────────────────────────
data "aws_route53_zone" "main" {
  count = var.domain != "" ? 1 : 0
  name  = var.domain
}

resource "aws_route53_record" "main" {
  count = var.domain != "" ? 1 : 0
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = var.domain
  type    = "A"
  alias {
    name                   = aws_cloudfront_distribution.main.domain_name
    zone_id                = aws_cloudfront_distribution.main.hosted_zone_id
    evaluate_target_health = false
  }
}

# ── Outputs ─────────────────────────────────────────────────────────────────
output "alb_dns_name" {
  description = "ALB DNS name (for testing before CloudFront deploys)"
  value       = module.alb.lb_dns_name
}

output "cloudfront_domain" {
  description = "CloudFront CDN domain"
  value       = aws_cloudfront_distribution.main.domain_name
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.rds.db_instance_endpoint
  sensitive   = true
}

output "redis_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = module.redis.endpoint
  sensitive   = true
}

output "ecs_cluster_name" {
  value = module.ecs.cluster_name
}
