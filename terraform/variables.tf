# Per-region backend config example.
# Run: terraform init -backend-config=backend-eu.tfvars

bucket         = "ai-empire-tf-state-eu-west-1"
region         = "eu-west-1"
dynamodb_table = "ai-empire-tf-locks"
encrypt        = true
