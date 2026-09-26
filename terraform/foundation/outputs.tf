output "hosted_zone_id" {
  value = aws_route53_zone.main.zone_id
}
output "name_servers" {
  value = aws_route53_zone.main.name_servers
}
output "domain_name" {
  value = var.domain_name
}
output "certificate_arn" {
  value = var.enable_certificate ? aws_acm_certificate_validation.site[0].certificate_arn : null
}
output "evidence_bucket_name" {
  value = aws_s3_bucket.evidence.id
}

output "alb_access_log_bucket_name" {
  value = aws_s3_bucket.evidence.id
  depends_on = [
    aws_s3_bucket_policy.evidence,
    aws_s3_bucket_public_access_block.evidence,
    aws_s3_bucket_ownership_controls.evidence,
    aws_s3_bucket_server_side_encryption_configuration.evidence,
    aws_s3_bucket_versioning.evidence,
    aws_s3_bucket_lifecycle_configuration.evidence,
  ]
}

output "eks_log_group_name" {
  value = aws_cloudwatch_log_group.eks.name
}

output "rds_log_group_names" {
  value = { for export, group in aws_cloudwatch_log_group.rds : export => group.name }
}
