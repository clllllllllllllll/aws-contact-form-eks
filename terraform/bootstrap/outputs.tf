output "state_bucket_name" {
  description = "Persistent S3 bucket for the foundation and workload Terraform state."
  value       = aws_s3_bucket.state.id
}

output "state_bucket_region" {
  description = "AWS Region containing the state bucket."
  value       = "ap-southeast-1"
}
