terraform {
  backend "s3" {
    bucket              = "aws-contact-form-eks-tfstate-203888389134-ap-southeast-1"
    key                 = "foundation/terraform.tfstate"
    region              = "ap-southeast-1"
    encrypt             = true
    use_lockfile        = true
    allowed_account_ids = ["203888389134"]
  }
}
