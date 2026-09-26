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
  description = "Explicit EKS minor version in standard support, verified in Singapore."
  type        = string
  validation {
    condition     = can(regex("^1\\.[0-9]+$", var.kubernetes_version))
    error_message = "Supply a verified EKS minor version such as 1.xx."
  }
}
variable "addon_versions" {
  description = "Exact EKS add-on versions compatible with the selected Kubernetes minor."
  type = object({
    vpc_cni    = string
    kube_proxy = string
    coredns    = string
  })
  validation {
    condition     = alltrue([for version in values(var.addon_versions) : length(trimspace(version)) > 0 && !startswith(version, "REPLACE")])
    error_message = "Supply verified exact versions for all three EKS add-ons."
  }
}
variable "node_release_version" {
  description = "Explicit AL2023 EKS optimized managed-node AMI release version."
  type        = string
  validation {
    condition     = length(trimspace(var.node_release_version)) > 0 && !startswith(var.node_release_version, "REPLACE")
    error_message = "Supply a verified managed-node AMI release version."
  }
}
variable "node_ami_id" {
  description = "Amazon EKS optimized AMI ID paired with the managed-node release by preflight."
  type        = string
  validation {
    condition     = can(regex("^ami-[0-9a-f]{8,17}$", var.node_ami_id))
    error_message = "Supply the node AMI ID captured by preflight."
  }
}
variable "node_ssm_parameter_version" {
  description = "Version of the regional recommended EKS AMI SSM parameter that published the node release and AMI ID."
  type        = number
  validation {
    condition     = var.node_ssm_parameter_version > 0 && floor(var.node_ssm_parameter_version) == var.node_ssm_parameter_version
    error_message = "Supply the positive SSM parameter version captured by preflight."
  }
}
variable "relay_ami_id" {
  description = "Explicit Amazon Linux 2023 x86_64 AMI ID for the private SSM relay."
  type        = string
  validation {
    condition     = can(regex("^ami-[0-9a-f]{8,17}$", var.relay_ami_id))
    error_message = "Supply a verified AMI ID for the relay."
  }
}
variable "node_instance_type" {
  type    = string
  default = "t3.medium"
  validation {
    condition     = var.node_instance_type == "t3.medium"
    error_message = "The approved worker size is t3.medium."
  }
}
variable "relay_instance_type" {
  type    = string
  default = "t3.micro"
  validation {
    condition     = var.relay_instance_type == "t3.micro"
    error_message = "The six-vCPU base allowance assumes a t3.micro relay."
  }
}
variable "db_instance_class" {
  type    = string
  default = "db.t4g.small"
  validation {
    condition     = var.db_instance_class == "db.t4g.small"
    error_message = "The approved Multi-AZ database class is db.t4g.small."
  }
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
