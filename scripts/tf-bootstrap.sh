#!/usr/bin/env bash
#
# tf-bootstrap.sh — create S3 bucket + DynamoDB table for Terraform state
# Run once per region before first terraform apply.
#
# Usage:
#   ./scripts/tf-bootstrap.sh eu-west-1
#   ./scripts/tf-bootstrap.sh us-east-1
#

set -euo pipefail

REGION="${1:-eu-west-1}"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="ai-empire-tf-state-${REGION}-${ACCOUNT}"
TABLE="ai-empire-tf-locks"

echo "Region: $REGION"
echo "Account: $ACCOUNT"
echo "Bucket: $BUCKET"
echo "Lock table: $TABLE"
echo

# 1. Create S3 bucket (with versioning + encryption)
if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
    echo "✓ S3 bucket $BUCKET already exists"
else
    aws s3api create-bucket \
        --bucket "$BUCKET" \
        --region "$REGION" \
        --create-bucket-configuration LocationConstraint="$REGION" 2>&1 | tail -2
    echo "✓ S3 bucket $BUCKET created"

    aws s3api put-bucket-versioning \
        --bucket "$BUCKET" \
        --versioning-configuration Status=Enabled
    echo "✓ Versioning enabled"

    aws s3api put-bucket-encryption \
        --bucket "$BUCKET" \
        --server-side-encryption-configuration '{
          "Rule": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        }'
    echo "✓ Encryption enabled (AES256)"

    aws s3api put-bucket-lifecycle-configuration \
        --bucket "$BUCKET" \
        --lifecycle-configuration '{
          "Rules": [{
            "ID": "expire-old-versions",
            "Status": "Enabled",
            "NoncurrentVersionExpiration": {"NoncurrentDays": 90}
          }]
        }'
    echo "✓ Lifecycle: 90d version expiry"

    aws s3api put-public-access-block \
        --bucket "$BUCKET" \
        --public-access-block-configuration \
        "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
    echo "✓ Public access blocked"
fi

# 2. Create DynamoDB lock table
if aws dynamodb describe-table --table-name "$TABLE" --region "$REGION" 2>/dev/null >/dev/null; then
    echo "✓ DynamoDB table $TABLE already exists"
else
    aws dynamodb create-table \
        --table-name "$TABLE" \
        --attribute-definitions AttributeName=LockID,AttributeType=S \
        --key-schema AttributeName=LockID,KeyType=HASH \
        --billing-mode PAY_PER_REQUEST \
        --region "$REGION" 2>&1 | tail -2
    echo "✓ DynamoDB lock table $TABLE created"
fi

# 3. Generate per-region backend file
cat > "terraform/backend-${REGION}.tfvars" <<EOF
bucket         = "${BUCKET}"
key            = "ai-empire/terraform.tfstate"
region         = "${REGION}"
dynamodb_table = "${TABLE}"
encrypt        = true
EOF
echo
echo "Wrote terraform/backend-${REGION}.tfvars"
echo
echo "Next steps:"
echo "  cd terraform"
echo "  terraform init -backend-config=backend-${REGION}.tfvars"
echo "  terraform plan -var-file=terraform.tfvars"
echo "  terraform apply"
