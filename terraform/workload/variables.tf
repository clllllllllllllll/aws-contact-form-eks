variable "aws_account_id" {
  type    = string
  default = "203888389134"
  validation {
    condition     = var.aws_account_id == "203888389134"
    error_message = "This assignment is restricted to AWS account 203888389134."
  }
}
variable "aws_region" {
  type    = string
  default = "ap-southeast-1"
  validation {
    condition     = var.aws_region == "ap-southeast-1"
    error_message = "This assignment is restricted to ap-southeast-1."
  }
}
variable "cluster_name" {
  type    = string
  default = "contact-form-eks"
  validation {
    condition     = var.cluster_name == "contact-form-eks"
    error_message = "Cluster name is fixed to match the retained EKS log group."
  }
}
variable "kubernetes_version" {
  description = "Pin a version in EKS standard support and confirm it in Singapore before apply."
  type        = string
  default     = "1.35"
}
variable "node_instance_type" {
  type    = string
  default = "t3.medium"
}
variable "relay_instance_type" {
  type    = string
  default = "t3.micro"
}
variable "db_instance_class" {
  type    = string
  default = "db.t4g.small"
}
variable "db_engine_version" {
  description = "RDS picks the current minor release in this PostgreSQL major version."
  type        = string
  default     = "16"
}
variable "deployer_principal_arn" {
  description = "IAM principal that runs Ansible and kubectl through the private API tunnel."
  type        = string
  default     = "arn:aws:iam::203888389134:user/contact-form-deployer"
}
