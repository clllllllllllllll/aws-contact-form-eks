data "terraform_remote_state" "foundation" {
  backend = "s3"
  config = {
    bucket              = "aws-contact-form-eks-tfstate-203888389134-ap-southeast-1"
    key                 = "foundation/terraform.tfstate"
    region              = "ap-southeast-1"
    allowed_account_ids = ["203888389134"]
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs               = slice(sort(data.aws_availability_zones.available.names), 0, 2)
  domain_name       = data.terraform_remote_state.foundation.outputs.domain_name
  hosted_zone_id    = data.terraform_remote_state.foundation.outputs.hosted_zone_id
  certificate_arn   = data.terraform_remote_state.foundation.outputs.certificate_arn
  cluster_oidc_host = replace(aws_eks_cluster.main.identity[0].oidc[0].issuer, "https://", "")
}
