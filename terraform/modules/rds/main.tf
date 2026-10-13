# RDS Postgres for AI Empire
resource "aws_db_subnet_group" "main" {
  name       = var.name
  subnet_ids = var.database_subnets
  tags       = var.tags
}

resource "aws_security_group" "rds" {
  name        = "${var.name}-rds"
  description = "RDS security group"
  vpc_id      = var.vpc_id
  
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.api_security_group_id]
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = var.tags
}

resource "aws_rds_cluster" "main" {
  cluster_identifier              = var.name
  engine                          = "aurora-postgresql"
  engine_version                  = "15.5"
  database_name                   = "empire"
  master_username                 = "empire"
  manage_master_user_password     = true
  master_user_secret_kms_key_id   = var.kms_key_id
  
  db_subnet_group_name            = aws_db_subnet_group.main.name
  vpc_security_group_ids          = [aws_security_group.rds.id]
  
  storage_encrypted               = true
  kms_key_id                      = var.kms_key_id
  deletion_protection             = true
  skip_final_snapshot             = false
  final_snapshot_identifier       = "${var.name}-final"
  
  backup_retention_period         = 30
  preferred_backup_window         = "03:00-04:00"
  preferred_maintenance_window    = "Sun:04:00-Sun:05:00"
  
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  iam_database_authentication_enabled = true
  
  serverlessv2_scaling_configuration {
    min_capacity = 2
    max_capacity = 64
  }
  
  tags = var.tags
}

resource "aws_rds_cluster_instance" "main" {
  count              = 2
  identifier         = "${var.name}-${count.index}"
  cluster_identifier = aws_rds_cluster.main.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.main.engine
  
  performance_insights_enabled          = true
  performance_insights_kms_key_id       = var.kms_key_id
  performance_insights_retention_period = 7
  
  monitoring_interval = 60
  monitoring_role_arn = aws_iam_role.rds_monitoring.arn
  
  ca_cert_identifier = "rds-ca-rsa4096-g1"
  
  tags = var.tags
}

resource "aws_iam_role" "rds_monitoring" {
  name = "${var.name}-rds-monitoring"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "monitoring.rds.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}
