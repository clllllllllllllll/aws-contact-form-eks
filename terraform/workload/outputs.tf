output "cluster_name" {
  value = aws_eks_cluster.main.name
}
output "cluster_endpoint" {
  value = aws_eks_cluster.main.endpoint
}
output "cluster_ca_data" {
  value = aws_eks_cluster.main.certificate_authority[0].data
}
output "relay_instance_id" {
  value = aws_instance.relay.id
}
output "vpc_id" {
  value = aws_vpc.main.id
}
output "alb_security_group_id" {
  value = aws_security_group.alb.id
}
output "rds_identifier" {
  value = aws_db_instance.main.identifier
}
output "rds_host" {
  value = aws_db_instance.main.address
}
output "rds_port" {
  value = aws_db_instance.main.port
}
output "rds_database_name" {
  value = aws_db_instance.main.db_name
}
output "rds_master_secret_arn" {
  value = aws_db_instance.main.master_user_secret[0].secret_arn
}
output "app_secret_arn" {
  value = aws_secretsmanager_secret.app.arn
}
output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}
output "hosted_zone_id" {
  value = local.hosted_zone_id
}
output "domain_name" {
  value = local.domain_name
}
output "certificate_arn" {
  value = local.certificate_arn
}
output "availability_zones" {
  value = local.azs
}

output "controller_role_arn" {
  value = aws_iam_role.irsa["controller"].arn
}
output "application_role_arn" {
  value = aws_iam_role.irsa["app"].arn
}
output "database_setup_role_arn" {
  value = aws_iam_role.irsa["setup"].arn
}
output "public_subnet_ids" {
  value = [for az in local.azs : aws_subnet.public[az].id]
}
