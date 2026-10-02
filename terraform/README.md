# Multi-Region Terraform

Deploys AI Empire to multiple AWS regions with global DNS failover.

## Architecture

```
                    ┌─────────────────┐
                    │  Route 53 (DNS) │
                    │  Health check   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
       ┌────────────┐ ┌────────────┐ ┌────────────┐
       │ us-east-1  │ │ eu-west-1  │ │ ap-southeast│
       │  ALB+EC2   │ │  ALB+EC2   │ │  ALB+EC2    │
       │  ASG 2-6   │ │  ASG 2-6   │ │  ASG 1-3    │
       └─────┬──────┘ └─────┬──────┘ └─────┬───────┘
             │              │              │
             └──────────────┼──────────────┘
                            │
                ┌───────────┴──────────┐
                │                      │
                ▼                      ▼
        ┌──────────────┐      ┌──────────────┐
        │ RDS Postgres │      │  S3 Backups  │
        │ Multi-AZ     │      │  Cross-region│
        │ Encrypted    │      │  Versioned   │
        └──────────────┘      └──────────────┘
```

## Quick start

```bash
# 1. Configure backend (S3 + DynamoDB)
aws s3api create-bucket --bucket ai-empire-terraform-state --region us-east-1
aws dynamodb create-table \
  --table-name ai-empire-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

# 2. Initialize
terraform init

# 3. Plan
terraform plan -var-file=prod.tfvars

# 4. Apply
terraform apply -var-file=prod.tfvars
```

## Customization

### Add region
```hcl
# prod.tfvars
regions = ["us-east-1", "eu-west-1", "ap-southeast-1", "sa-east-1"]
```

### Bigger instances
```hcl
instance_type = "t3.xlarge"  # 4 vCPU, 16 GB RAM
```

### More replicas
```hcl
min_instances = 3
max_instances = 10
```

## Modules

- `main.tf` — root module
- `modules/network/` — VPC, subnets, NAT, security groups
- `modules/compute/` — ASG, launch template, ALB
- `modules/compute/user_data.sh` — bootstrap script

## Cost estimate (production)

| Resource | Quantity | Monthly USD |
|----------|----------|-------------|
| EC2 t3.large | 6 (2 per region) | ~$280 |
| ALB | 3 | ~$75 |
| RDS db.t3.medium Multi-AZ | 1 | ~$120 |
| EBS gp3 100 GB | 6 | ~$60 |
| S3 backups 100 GB | 1 | ~$3 |
| Data transfer | varies | ~$50 |
| **Total** | | **~$590/mo** |

## Disaster recovery

RPO/RTO targets:
- **RPO**: 1 hour (hourly backups to S3)
- **RTO**: 15 minutes (Route 53 failover to other region)

Test DR quarterly:
```bash
# Simulate region failure
aws ec2 stop-instances --instance-ids i-xxx --region us-east-1

# Verify Route 53 failover
dig ai-empire.example.com
```

## See also

- `docs/MULTI_REGION.md` — architecture details
- `runbooks/disaster-recovery.md` — DR procedures
- `terraform/main.tf` — root config