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
variable "domain_name" {
  description = "Registered domain delegated to the Route 53 hosted zone."
  type        = string
  default     = "cheelong.xyz"
  validation {
    condition     = can(regex("^[a-z0-9-]+(\\.[a-z0-9-]+)+$", var.domain_name))
    error_message = "Supply a domain such as cheelong.xyz."
  }
}
variable "enable_certificate" {
  description = "Set true only after the registrar uses the hosted zone's Route 53 nameservers."
  type        = bool
}
variable "enable_security_services" {
  description = "Enable account/Region-wide Config and Security Hub after inventory and cost review."
  type        = bool
}
variable "enable_cloudtrail" {
  description = "Create a project trail only if the account lacks suitable management-event coverage."
  type        = bool
}
variable "pause_config_and_fsbp" {
  description = "For a later demo standby, stop the existing Config recorder and disable Security Hub/FSBP while retaining their configuration and keeping the project management trail logging."
  type        = bool
  default     = false
}
