# AI Empire — Production (multi-region active-active)

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  backend "s3" {
    bucket         = "empire-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "empire-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.primary_region
  
  default_tags {
    tags = {
      Project     = "ai-empire"
      Environment = "production"
      ManagedBy   = "terraform"
    }
  }
}

# Primary region (us-east-1)
module "primary_vpc" {
  source = "../../modules/vpc"
  name   = "empire-primary"
  vpc_cidr = "10.0.0.0/16"
  azs    = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

# WAF
module "waf" {
  source = "../../modules/waf"
  name   = "empire-prod"
}

# ECS
module "ecs_primary" {
  source = "../../modules/ecs"
  name   = "empire-primary"
  image  = "ghcr.io/grupoandevelopment-m/ai-empire:4.0.0"
  region = var.primary_region
  
  desired_count         = 3
  private_subnets       = module.primary_vpc.private_subnets
  api_security_group_id = aws_security_group.api_primary.id
  target_group_arn      = aws_lb_target_group.primary.arn
  
  jwt_secret_arn      = aws_secretsmanager_secret.jwt.arn
  nvidia_nim_key_arn  = aws_secretsmanager_secret.nvidia.arn
  muapi_key_arn       = aws_secretsmanager_secret.muapi.arn
}

# RDS Aurora Serverless v2
module "rds_primary" {
  source = "../../modules/rds"
  name   = "empire-primary"
  vpc_id = module.primary_vpc.vpc_id
  database_subnets = module.primary_vpc.database_subnets
  api_security_group_id = aws_security_group.api_primary.id
  kms_key_id = aws_kms_key.main.arn
}

# ElastiCache Global
module "redis" {
  source = "../../modules/elasticache"
  name   = "empire"
  primary_region = var.primary_region
  private_subnets = module.primary_vpc.private_subnets
  redis_security_group_id = aws_security_group.redis.id
  auth_token = var.redis_auth_token
}

# Application Load Balancer
resource "aws_lb" "primary" {
  name               = "empire-primary"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = module.primary_vpc.public_subnets
  
  enable_deletion_protection = true
  enable_http2              = true
  enable_wafv2              = true
  wafv2_web_acl_arn         = module.waf.arn
  
  access_logs {
    bucket  = aws_s3_bucket.alb_logs.bucket
    prefix  = "primary"
    enabled = true
  }
  
  tags = { Name = "empire-primary" }
}

# Security Groups, IAM, etc...
