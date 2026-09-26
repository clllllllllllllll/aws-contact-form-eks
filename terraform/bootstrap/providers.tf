provider "aws" {
  region              = "ap-southeast-1"
  allowed_account_ids = ["203888389134"]

  default_tags {
    tags = {
      Project   = "aws-contact-form-eks"
      ManagedBy = "Terraform"
      Lifecycle = "persistent"
    }
  }
}
