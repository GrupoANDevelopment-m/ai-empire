# AI Empire — dev environment
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = "ai-empire"
      Environment = "dev"
      ManagedBy   = "terraform"
    }
  }
}

variable "region" { type = string, default = "us-east-1" }

# Smaller, cheaper dev stack
module "vpc" {
  source = "../../modules/vpc"
  name   = "empire-dev"
  vpc_cidr = "10.0.0.0/16"
  azs    = ["us-east-1a", "us-east-1b"]
}
