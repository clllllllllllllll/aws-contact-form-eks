resource "aws_db_subnet_group" "main" {
  name       = "contact-form-db"
  subnet_ids = [for az in local.azs : aws_subnet.database[az].id]
  tags       = { Name = "contact-form-db" }
}

# RDS generates and manages the master password. Terraform receives only
# the secret ARN and never stores the password value in its state.
resource "aws_db_instance" "main" {
  identifier                   = "contact-form-postgres"
  engine                       = "postgres"
  engine_version               = var.db_engine_version
  instance_class               = var.db_instance_class
  allocated_storage            = 20
  max_allocated_storage        = 40
  storage_type                 = "gp3"
  storage_encrypted            = true
  multi_az                     = true
  db_name                      = "contactform"
  username                     = "contact_master"
  manage_master_user_password  = true
  db_subnet_group_name         = aws_db_subnet_group.main.name
  vpc_security_group_ids       = [aws_security_group.rds.id]
  publicly_accessible          = false
  backup_retention_period      = 1
  delete_automated_backups     = true
  skip_final_snapshot          = true
  deletion_protection          = false
  apply_immediately            = true
  auto_minor_version_upgrade   = true
  performance_insights_enabled = false
  copy_tags_to_snapshot        = true
  tags                         = { Name = "contact-form-postgres" }
  depends_on                   = [aws_route_table_association.database]
}

# Metadata only. The database setup Job writes the first secret version.
# A generated suffix avoids name reuse conflicts during Secrets Manager deletion.
resource "aws_secretsmanager_secret" "app" {
  name_prefix             = "contact-form/app-"
  description             = "Restricted PostgreSQL login and Flask signing key"
  recovery_window_in_days = 0
}
