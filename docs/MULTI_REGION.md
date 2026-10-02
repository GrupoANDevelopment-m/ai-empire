# Multi-Region Deployment

AI Empire runs in multiple AWS regions with global DNS failover for high availability.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Route 53 (DNS)                         │
│             Health checks every 30s per region              │
└────────────────────┬────────────────────────────────────────┘
                     │
       ┌─────────────┼─────────────┐
       │             │             │
       ▼             ▼             ▼
   ┌────────┐    ┌────────┐    ┌────────┐
   │ us-east│    │eu-west │    │ap-south│
   │  ALB+  │    │  ALB+  │    │  ALB+  │
   │  ASG   │    │  ASG   │    │  ASG   │
   └───┬────┘    └───┬────┘    └───┬────┘
       │             │             │
       └─────────────┼─────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
   ┌─────────┐             ┌──────────┐
   │   RDS   │             │    S3    │
   │ Postgres│             │ Backups  │
   │Multi-AZ │             │Cross-reg │
   │Encryp.  │             │Versioned │
   └─────────┘             └──────────┘
```

## Why multi-region?

1. **Latency** — users get served from nearest region (< 100ms p99)
2. **Availability** — 99.99% SLA vs 99.9% single-region
3. **Compliance** — data residency in EU for European users
5. **Cost** — no extra license, only AWS infra cost

## Components

### Network (per region)
- VPC with /16 CIDR
- 3 public subnets (ALB + NAT)
- 3 private subnets (EC2 + RDS)
- Single NAT gateway (cost-optimized; multi-NAT for prod)
- Security groups: ALB (80/443), EC2 (8123 from ALB + 22 from VPC), Postgres (3306 from EC2)

### Compute (per region)
- Auto Scaling Group: 2-6 instances (configurable)
- Launch template:
  - Ubuntu 22.04 LTS
  - IMDSv2 required (security)
  - 100 GB gp3 EBS, encrypted
  - IAM role for CloudWatch + Secrets Manager
- Application Load Balancer:
  - HTTPS-only with ACM cert
  - HTTP→HTTPS redirect
  - Drop invalid headers
  - Health check on `/health` (200)

### Storage (global)
- S3 bucket for backups, versioned, lifecycle 90d
- RDS Postgres, Multi-AZ, 30d automated backups, encrypted at rest

### DNS
- Route 53 hosted zone
- Health check per region (30s interval)
- Failover routing: PRIMARY → SECONDARY (in order of regions var)

## Deployment

```bash
# 1. Pre-reqs
aws s3 mb s3://ai-empire-terraform-state --region us-east-1
aws dynamodb create-table \
  --table-name ai-empire-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

# 2. Configure
cd terraform
cp prod.tfvars my-prod.tfvars
# Edit my-prod.tfvars with your domain, ssh key, regions

# 3. Deploy
terraform init
terraform plan -var-file=my-prod.tfvars
terraform apply -var-file=my-prod.tfvars

# 4. Verify
terraform output
```

## Traffic routing

Route 53 health checks hit `/health` every 30s. After 3 failures (90s), region is marked unhealthy and traffic shifts to next PRIMARY.

```bash
# Test failover
curl -i https://ai-empire.example.com/health
# Returns 200 if any region is healthy
```

## State management

State stored in S3 with DynamoDB locking:
```hcl
terraform {
  backend "s3" {
    bucket         = "ai-empire-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "ai-empire-terraform-locks"
  }
}
```

## Disabling a region

```bash
# Remove from vars
# Or, comment out in prod.tfvars and apply
terraform apply -var-file=prod.tfvars \
  -target=module.compute["ap-southeast-1"]
```

State is preserved so the region can be re-enabled.

## Cost optimization

### Production
- 3 regions × (2-6 EC2 + ALB + EBS) + RDS + S3
- ~$590/month baseline (small)

### Development
- 1 region, 1 instance
- ~$80/month

### Spot instances
```hcl
# Use spot for non-critical workloads
variable "instance_market_options" {
  default = {
    market_type = "spot"
    spot_options = {
      max_price = "0.05"
    }
  }
}
```

## See also

- `terraform/README.md` — terraform quickstart
- `terraform/main.tf` — root module
- `terraform/modules/network/` — VPC module
- `terraform/modules/compute/` — EC2+ALB module
- `runbooks/disaster-recovery.md` — DR procedures