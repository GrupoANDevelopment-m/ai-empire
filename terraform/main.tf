# AI Empire — Multi-region Terraform configuration
# Deploys AI Empire to AWS, GCP, or Azure across multiple regions.
#
# Usage:
#   terraform init
#   terraform plan -var-file=prod.tfvars
#   terraform apply -var-file=prod.tfvars
#
# Regions (default): us-east-1, eu-west-1, ap-southeast-1
# Can be overridden via -var="regions=[us-west-2,sa-east-1]"

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }

  # Backend: store state in S3 with locking
  backend "s3" {
    bucket         = "ai-empire-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "ai-empire-terraform-locks"
  }
}

# ─── Variables ────────────────────────────────────────────────────────────────

variable "project_name" {
  description = "Project name (used for resource tagging)"
  type        = string
  default     = "ai-empire"
}

variable "regions" {
  description = "AWS regions to deploy to"
  type        = list(string)
  default     = ["us-east-1", "eu-west-1", "ap-southeast-1"]
}

variable "instance_type" {
  description = "EC2 instance type for the AI Empire host"
  type        = string
  default     = "t3.large"  # 2 vCPU, 8 GB RAM
}

variable "min_instances" {
  description = "Minimum instances per region (for autoscaling)"
  type        = number
  default     = 1
}

variable "max_instances" {
  description = "Maximum instances per region"
  type        = number
  default     = 3
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "ssh_public_key" {
  description = "SSH public key for EC2 access"
  type        = string
  default     = ""
}

variable "domain_name" {
  description = "Primary domain for the AI Empire instance"
  type        = string
  default     = "ai-empire.example.com"
}

variable "letsencrypt_email" {
  description = "Email for Let's Encrypt certificate registration"
  type        = string
  default     = "ops@example.com"
}

variable "enable_backups" {
  description = "Enable automatic EBS snapshots"
  type        = bool
  default     = true
}

# ─── Locals ──────────────────────────────────────────────────────────────────

locals {
  common_tags = {
    Project     = var.project_name
    ManagedBy   = "terraform"
    Environment = "production"
  }
}

# ─── Provider ────────────────────────────────────────────────────────────────

provider "aws" {
  region = var.regions[0]
}

# ─── Random suffix for unique resource names ────────────────────────────────

resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  name_suffix = random_id.elementalfa.suffix.hex
}

resource "random_id" "elementalfa" {
  byte_length = 6
}

# ─── Networking (per region) ────────────────────────────────────────────────

module "network" {
  source = "./modules/network"

  for_each = toset(var.regions)

  region          = each.value
  project_name    = var.project_name
  vpc_cidr        = var.vpc_cidr
  common_tags     = local.common_tags
  name_suffix     = local.name_suffix
}

# ─── Compute (per region) ──────────────────────────────────────────────────

module "compute" {
  source = "./modules/compute"

  for_each = toset(var.regions)

  region          = each.value
  project_name    = var.project_name
  instance_type   = var.instance_type
  min_instances   = var.min_instances
  max_instances   = var.max_instances
  ssh_public_key  = var.ssh_public_key
  vpc_id          = module.network[each.value].vpc_id
  subnet_ids      = module.network[each.value].public_subnet_ids
  security_group_id = module.network[each.value].security_group_id
  common_tags     = local.common_tags
  name_suffix     = local.name_suffix
  enable_backups  = var.enable_backups
}

# ─── Storage (global: S3 for state + backups) ─────────────────────────────

resource "aws_s3_bucket" "backups" {
  bucket = "${var.project_name}-backups-${local.name_suffix}"

  tags = merge(local.common_tags, {
    Purpose = "empire-data-backups"
  })
}

resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    id     = "expire-old-backups"
    status = "Enabled"

    expiration {
      days = 90
    }

    noncurrent_version_expiration {
      days = 30
    }
  }
}

resource "aws_s3_bucket_public_access_block" "backups" {
  bucket = aws_s3_bucket.backups.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# ─── RDS (Postgres — global for shared state) ──────────────────────────────

resource "aws_db_instance" "postgres" {
  identifier     = "${var.project_name}-postgres-${local.name_suffix}"
  engine         = "postgres"
  engine_version = "16.3"
  instance_class = "db.t3.medium"
  allocated_storage = 50
  max_allocated_storage = 200

  db_name  = "empire"
  username = "empire"
  port     = 3306

  # Use Secrets Manager for password
  password = data.aws_secretsmanager_secret_version.postgres_password.secret_string

  vpc_security_group_ids = [module.network[var.regions[0]].postgres_sg_id]
  db_subnet_group_name = aws_db_subnet_group.postgres.name

  multi_az              = true
  storage_encrypted     = true
  backup_retention_period = 30
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  deletion_protection = true

  tags = merge(local.common_tags, {
    Purpose = "empire-shared-postgres"
  })
}

resource "aws_db_subnet_group" "postgres" {
  name       = "${var.project_name}-postgres-${local.name_suffix}"
  subnet_ids = module.network[var.regions[0]].private_subnet_ids

  tags = local.common_tags
}

# Secrets Manager — postgres password
resource "aws_secretsmanager_secret" "postgres_password" {
  name = "${var.project_name}-postgres-password-${local.name_suffix}"

  tags = local.common_tags
}

resource "random_password" "postgres_password" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret_version" "postgres_password" {
  secret_id = aws_secretsmanager_secret.postgres_password.id
  secret_string = random_password.postgres_password.result
}

data "aws_secretsmanager_secret_version" "postgres_password" {
  secret_id = aws_secretsmanager_secret.postgres_password.id
}

# ─── Route 53 (global DNS failover) ────────────────────────────────────────

resource "aws_route53_zone" "primary" {
  name = var.domain_name
  tags = local.common_tags
}

# Health check + failover for each region
resource "aws_route53_health_check" "regions" {
  for_each = toset(var.regions)

  fqdn              = module.compute[each.value].health_check_url
  port               = 443
  type               = "HTTPS"
  resource_path      = "/health"
  failure_threshold = 3
  request_interval   = 30

  tags = merge(local.common_tags, { Region = each.value })
}

# DNS failover records (primary → secondary)
resource "aws_route53_record" "regions" {
  for_each = toset(var.regions)

  zone_id = aws_route53_zone.primary.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = module.compute[each.value].load_balancer_dns
    zone_id                = module.compute[each.value].load_balancer_zone_id
    evaluate_target_health = true
  }

  failover_routing_policy {
    type = index(var.regions, each.value) == 0 ? "PRIMARY" : "SECONDARY"
  }

  set_identifier  = each.value
  health_check_id = aws_route53_health_check.regions[each.value].id
}

# ─── CloudWatch Alarms (cross-region) ──────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "instance_down" {
  for_each = toset(var.regions)

  alarm_name          = "${var.project_name}-${each.value}-instance-down"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "StatusCheckFailed"
  namespace           = "AWS/EC2"
  period              = "60"
  statistic           = "Maximum"
  threshold           = "0"
  alarm_description   = "EC2 instance in ${each.value} is down"
  treat_missing_data  = "breaching"

  dimensions = {
    AutoScalingGroupName = module.compute[each.value].asg_name
  }

  tags = merge(local.common_tags, { Region = each.value })
}

# ─── Outputs ────────────────────────────────────────────────────────────────

output "regions" {
  description = "Deployed regions"
  value       = var.regions
}

output "backups_bucket" {
  description = "S3 bucket for backups"
  value       = aws_s3_bucket.backups.id
}

output "postgres_endpoint" {
  description = "Postgres RDS endpoint"
  value       = aws_db_instance.postgres.endpoint
}

output "domain_url" {
  description = "Primary domain URL"
  value       = "https://${var.domain_name}"
}

output "instance_ips" {
  description = "Public IPs of deployed instances (use ALB DNS, not IPs)"
  value       = { for r in var.regions : r => module.compute[r].instance_public_ips }
}

output "load_balancer_dns" {
  description = "Load balancer DNS per region"
  value       = { for r in var.regions : r => module.compute[r].load_balancer_dns }
}