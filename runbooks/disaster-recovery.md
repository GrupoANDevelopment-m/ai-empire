# Disaster Recovery Runbook

## Severity levels

- **SEV-1**: All regions down — total outage
- **SEV-2**: One region down — partial outage, failover automatic
- **SEV-3**: Service degraded but functional

## SEV-2: Single region failure

### Detection
- Route 53 health checks fail (3 × 30s = 90s)
- CloudWatch alarm `ai-empire-{region}-instance-down`
- Email/Slack notification (if WATCHTOWER_NOTIFY_URL set)

### Automatic response
1. Route 53 marks region unhealthy
2. Traffic shifts to next PRIMARY region
3. No user impact beyond RTT latency

### Investigation
```bash
# Check region status
aws ec2 describe-instances --region us-east-1 \
  --filters "Name=tag:Project,Values=ai-empire" \
  --query 'Reservations[*].Instances[*].[State.Name,PublicIp]'

# Check ALB target health
aws elbv2 describe-target-health --target-group-arn $TG_ARN --region us-east-1

# Check instance logs
aws ec2 get-console-output --instance-id i-xxx --region us-east-1 | tail -50
```

### Recovery
```bash
# If just instance crash — ASG auto-launches new
# If AZ failure — ASG launches in other AZ

# Manual restart
aws ec2 reboot-instances --instance-ids i-xxx --region us-east-1
```

## SEV-1: All regions down

### Detection
- Route 53 health checks fail in ALL regions
- CloudWatch composite alarm triggers

### Escalation
1. Page on-call engineer (PagerDuty/Opsgenie)
2. Post in #incident Slack channel
3. Notify leadership within 30 minutes

### Investigation checklist
- [ ] Is AWS having issues? https://health.aws.amazon.com
- [ ] Is our account suspended? `aws support describe-cases`
- [ ] DNS resolution working? `dig ai-empire.example.com`
- [ ] Certificate valid? `aws acm describe-certificate --certificate-arn $ARN`
- [ ] RDS accessible? `aws rds describe-db-instances`
- [ ] S3 bucket accessible? `aws s3 ls s3://...`

### Recovery steps
1. If DNS broken — verify Route 53 zone, update nameservers at registrar
2. If certificate broken — request new ACM cert, update ALB listener
3. If compute broken — check IAM permissions, ASG launch template, AMI exists
4. If database broken — restore from snapshot (RDS automated backup)
5. If everything broken — restore from S3 backup

### Restore from backup
```bash
# 1. List backups
aws s3 ls s3://ai-empire-backups-{suffix}/backups/ | tail

# 2. Download most recent
aws s3 cp s3://ai-empire-backups-{suffix}/backups/{ts}.tar.gz .

# 3. Extract to fresh instance
tar -xzf {ts}.tar.gz -C /opt/ai-empire/

# 4. Start services
cd /opt/ai-empire && ./empire start

# 5. Verify
curl https://ai-empire.example.com/health
```

## Recovery time objectives

| Scenario | RTO | RPO |
|----------|------|-----|
| Single instance crash | < 5 min | 0 (stateful) |
| Single AZ failure | < 10 min | 0 (stateful) |
| Single region failure | < 1 min (auto) | 0 |
| All regions failure | < 30 min | < 1 hour |
| Database corruption | < 1 hour | < 1 hour (PITR) |
| Data center destruction | < 4 hours | < 24 hours |

## Quarterly DR drill

```bash
# 1. Pick one region (e.g., ap-southeast-1) to simulate failure
aws ec2 stop-instances --instance-ids i-xxx,i-yyy --region ap-southeast-1

# 2. Verify failover (other regions take traffic)
watch -n 30 'dig +short ai-empire.example.com'

# 3. Measure time
START=$(date +%s)
while ! curl -fs https://ai-empire.example.com/health > /dev/null; do sleep 1; done
echo "Recovery took: $(($(date +%s) - START)) seconds"

# 4. Restore
aws ec2 start-instances --instance-ids i-xxx,i-yyy --region ap-southeast-1

# 5. Verify in Slack #drills
```

## Post-mortem

After any SEV-1/SEV-2:
1. Create incident doc in `incidents/YYYY-MM-DD-{name}.md`
2. Timeline with timestamps
3. Customer impact (users affected, duration)
4. Root cause analysis
5. Action items (preventive)

## Communication

- Internal: #incidents Slack channel
- Status page: https://status.ai-empire.example.com
- Customer email: If > 30 min outage, send notice
- Social: Only if > 1 hour outage

## References

- `docs/MULTI_REGION.md` — architecture
- `terraform/README.md` — terraform
- `runbooks/auto-update.md` — image update procedure