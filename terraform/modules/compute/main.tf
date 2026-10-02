# AI Empire — Compute module
# Creates ASG + Launch Template + ALB for one region.

variable "region" {
  type = string
}

variable "project_name" {
  type = string
}

variable "instance_type" {
  type = string
}

variable "min_instances" {
  type = number
}

variable "max_instances" {
  type = number
}

variable "ssh_public_key" {
  type    = string
  default = ""
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "common_tags" {
  type = map(string)
}

variable "name_suffix" {
  type = string
}

variable "enable_backups" {
  type    = bool
  default = true
}

# ─── AMI ───────────────────────────────────────────────────────────────

data "aws_ami" "ubuntu_22" {
  most_recent = true
  owners      = ["099720109477"]  # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ─── Key Pair ──────────────────────────────────────────────────────────

resource "aws_key_pair" "main" {
  count      = var.ssh_public_key != "" ? 1 : 0
  key_name   = "${var.project_name}-${var.name_suffix}"
  public_key = var.ssh_public_key

  tags = var.common_tags
}

# ─── IAM Role for EC2 ──────────────────────────────────────────────────

data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2" {
  name               = "${var.project_name}-ec2-${var.name_suffix}"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

# Allow EC2 to push to CloudWatch Logs
data "aws_iam_policy_document" "ec2_cloudwatch" {
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
    ]
    resources = ["*"]
  }

  # Allow S3 backup writes
  statement {
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = ["*"]
  }

  # Allow Secrets Manager reads
  statement {
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ec2_cloudwatch" {
  name   = "${var.project_name}-ec2-cloudwatch"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.ec2_cloudwatch.json
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${var.project_name}-ec2-${var.name_suffix}"
  role = aws_iam_role.ec2.name
}

# ─── Launch Template ───────────────────────────────────────────────────

resource "aws_launch_template" "main" {
  name_prefix   = "${var.project_name}-lt-"
  image_id      = data.aws_ami.ubuntu_22.id
  instance_type = var.instance_type

  key_name = var.ssh_public_key != "" ? aws_key_pair.main[0].key_name : null

  vpc_security_group_ids = [var.security_group_id]

  user_data = base64encode(templatefile("${path.module}/user_data.sh", {
    project_name = var.project_name
  }))

  block_device_mappings {
    device_name = "/dev/sda1"

    ebs {
      volume_size           = 100
      volume_type           = "gp3"
      iops                  = 3000
      throughput            = 125
      encrypted             = true
      delete_on_termination = true
    }
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"  # IMDSv2 required
    http_put_response_hop_limit = 1
  }

  tag_specifications {
    resource_type = "instance"
    tags = merge(var.common_tags, {
      Name = "${var.project_name}-empire-${var.name_suffix}"
    })
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ─── Auto Scaling Group ────────────────────────────────────────────────

resource "aws_autoscaling_group" "main" {
  name                = "${var.project_name}-asg-${var.name_suffix}"
  vpc_zone_identifier = var.subnet_ids
  target_group_arns   = [aws_lb_target_group.main.arn]
  health_check_type   = "ELB"
  health_check_grace_period = 300

  min_size         = var.min_instances
  max_size         = var.max_instances
  desired_capacity = var.min_instances

  enabled_metrics = [
    "GroupDesiredCapacity",
    "GroupInServiceInstances",
    "GroupPendingInstances",
    "GroupStandbyInstances",
    "GroupTerminatingInstances",
    "GroupTotalInstances",
  ]

  launch_template {
    id      = aws_launch_template.main.id
    version = "$Latest"
  }

  instance_refresh {
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 50
      instance_warmup        = 120
    }
  }

  tag {
    key                 = "Name"
    value               = "${var.project_name}-empire-${var.name_suffix}"
    propagate_at_launch = true
  }

  tag {
    key                 = "Project"
    value               = var.project_name
    propagate_at_launch = true
  }
}

# ─── Load Balancer ─────────────────────────────────────────────────────

resource "aws_lb" "main" {
  name               = "${var.project_name}-alb-${var.name_suffix}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.security_group_id]  # Tighten this in prod
  subnets            = var.subnet_ids

  enable_deletion_protection = true
  drop_invalid_header_fields = true

  tags = var.common_tags
}

resource "aws_lb_target_group" "main" {
  name        = "${var.project_name}-tg-${var.name_suffix}"
  port        = 8123
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "instance"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = var.common_tags
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.main.arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.main.arn
  }
}

resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# ─── ACM Certificate ───────────────────────────────────────────────────

resource "aws_acm_certificate" "main" {
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = var.common_tags
}

# ─── CloudWatch Log Group ──────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "main" {
  name              = "/aws/ec2/${var.project_name}"
  retention_in_days = 30

  tags = var.common_tags
}

# ─── Outputs ───────────────────────────────────────────────────────────

output "load_balancer_dns" {
  value = aws_lb.main.dns_name
}

output "load_balancer_zone_id" {
  value = aws_lb.main.zone_id
}

output "asg_name" {
  value = aws_autoscaling_group.main.name
}

output "instance_public_ips" {
  value = []  # Use ALB DNS, not IPs
}

output "health_check_url" {
  value = aws_lb.main.dns_name
}