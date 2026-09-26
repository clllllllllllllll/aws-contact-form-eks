# Config and Security Hub affect this AWS account and Region, so opt in only
# after checking for existing recorders/Hub subscriptions and reviewing costs.
resource "aws_iam_role" "config" {
  count = var.enable_security_services ? 1 : 0
  name  = "contact-form-config-recorder"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "config.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}
resource "aws_iam_role_policy_attachment" "config" {
  count      = var.enable_security_services ? 1 : 0
  role       = aws_iam_role.config[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWS_ConfigRole"
}
resource "aws_iam_role_policy" "config_delivery" {
  count = var.enable_security_services ? 1 : 0
  name  = "contact-form-config-delivery"
  role  = aws_iam_role.config[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetBucketAcl", "s3:ListBucket"]
      Resource = aws_s3_bucket.evidence.arn
      }, {
      Effect   = "Allow"
      Action   = ["s3:PutObject"]
      Resource = "${aws_s3_bucket.evidence.arn}/service-logs/config/*"
    }]
  })
}
resource "aws_config_configuration_recorder" "main" {
  count    = var.enable_security_services ? 1 : 0
  name     = "contact-form-recorder"
  role_arn = aws_iam_role.config[0].arn
  recording_group {
    all_supported                 = true
    include_global_resource_types = true
  }
  depends_on = [aws_iam_role_policy_attachment.config, aws_iam_role_policy.config_delivery]
}
resource "aws_config_delivery_channel" "main" {
  count          = var.enable_security_services ? 1 : 0
  name           = "contact-form-delivery"
  s3_bucket_name = aws_s3_bucket.evidence.id
  s3_key_prefix  = "service-logs/config"
  depends_on     = [aws_config_configuration_recorder.main, aws_s3_bucket_policy.evidence]
}
resource "aws_config_configuration_recorder_status" "main" {
  count      = var.enable_security_services ? 1 : 0
  name       = aws_config_configuration_recorder.main[0].name
  is_enabled = true
  depends_on = [aws_config_delivery_channel.main]
}
resource "aws_securityhub_account" "main" {
  count                    = var.enable_security_services ? 1 : 0
  enable_default_standards = false
  depends_on               = [aws_config_configuration_recorder_status.main]
}
resource "aws_securityhub_standards_subscription" "fsbp" {
  count         = var.enable_security_services ? 1 : 0
  standards_arn = "arn:aws:securityhub:${var.aws_region}::standards/aws-foundational-security-best-practices/v/1.0.0"
  depends_on    = [aws_securityhub_account.main]
}
resource "aws_cloudtrail" "management" {
  count                         = var.enable_cloudtrail ? 1 : 0
  name                          = "contact-form-management"
  s3_bucket_name                = aws_s3_bucket.evidence.id
  s3_key_prefix                 = "service-logs/cloudtrail"
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_log_file_validation    = true
  event_selector {
    read_write_type           = "All"
    include_management_events = true
  }
  depends_on = [aws_s3_bucket_policy.evidence]
}

# Keep audit logs across disposable cluster rebuilds. The cluster name is
# fixed for this assignment, so a new cluster can reuse this log group.
resource "aws_cloudwatch_log_group" "eks" {
  name              = "/aws/eks/contact-form-eks/cluster"
  retention_in_days = 7
  lifecycle { prevent_destroy = true }
}

# These fixed-name log groups survive deletion and rebuilding of the RDS instance.
resource "aws_cloudwatch_log_group" "rds" {
  for_each          = toset(["postgresql", "upgrade"])
  name              = "/aws/rds/instance/contact-form-postgres/${each.key}"
  retention_in_days = 7
  lifecycle { prevent_destroy = true }
}
