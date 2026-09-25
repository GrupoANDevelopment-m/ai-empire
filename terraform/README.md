# AI Empire — Multi-region Terraform

Production-grade infrastructure for AI Empire on AWS. Multi-region by default.

## What's included

- **VPC** with public/private/database/intra subnets across 3 AZs
- **ECS Fargate** cluster with FARGATE + FARGATE_SPOT capacity providers
- **RDS PostgreSQL** (multi-AZ in prod) with pgvector + Performance Insights + Enhanced Monitoring
- **ElastiCache Redis** with at-rest + in-transit encryption + auth token
- **ALB** with WAF v2 (rate limit + AWS managed rule sets + GeoBlock)
- **CloudFront** CDN in front of ALB, TLS 1.2+ only
- **Route53** for custom domains
- **S3** for ALB logs with lifecycle to Glacier
- **Secrets Manager** for API keys (Anthropic, OpenAI, JWT)
- **KMS** for encryption at rest
- **GuardDuty** threat detection (production only)
- **Security Groups** least-privilege per service
- **IAM** roles with separation of duties
- **VPC Flow Logs** to CloudWatch

## Multi-region deployment

```bash
# EU region
cd terraform/
terraform init -backend-config=backend-eu.tfvars
terraform apply -var-file=eu.tfvars

# US region (different state)
terraform init -backend-config=backend-us.tfvars
terraform apply -var-file=us.tfvars

# Failover / latency routing via Route53 latency records:
# ai-empire.example.com  →  EU ALB
# ai-empire.example.com  →  US ALB (latency-based)
```

## Files

- `main.tf` — all resources
- `variables.tf` — backend config example
- `backend-eu.tfvars` — S3+DynamoDB backend for EU region
- `backend-us.tfvars` — same for US region
- `eu.tfvars`, `us.tfvars` — per-region input variables

## Prerequisites

- Terraform >= 1.6
- AWS account with permissions for VPC, ECS, RDS, ElastiCache, ALB, WAF, CloudFront, KMS, Secrets Manager, IAM, S3, Route53, CloudWatch
- S3 bucket + DynamoDB table for remote state (create once per region)
- ACM certificate ARN (for HTTPS)

## Cost (rough monthly estimate, prod)

| Service | Cost |
|---|---|
| ECS Fargate (3 tasks × 2vCPU × 4GB) | ~$60 |
| RDS db.r7g.large multi-AZ + 100GB | ~$280 |
| ElastiCache cache.r7g.large × 3 | ~$135 |
| ALB | ~$25 |
| CloudFront | ~$5 (low traffic) |
| NAT Gateway × 3 | ~$100 |
| KMS, Secrets Manager, CloudWatch | ~$10 |
| **Total** | **~$615/month** |

Add $5-50/month for Anthropic/OpenAI API usage on top.

## Quick start

```bash
# 1. Bootstrap state backend (one-time per region)
./scripts/tf-bootstrap.sh eu-west-1

# 2. Deploy
cd terraform
terraform init -backend-config=backend-eu.tfvars
terraform plan -var-file=eu.tfvars
terraform apply -var-file=eu.tfvars

# 3. Get endpoints
terraform output alb_dns_name
terraform output cloudfront_domain
```
