locals {
  controller_arn_prefix = "arn:aws:elasticloadbalancing:${var.aws_region}:${var.aws_account_id}"
  controller_arns = {
    load_balancer = "${local.controller_arn_prefix}:loadbalancer/app/*/*"
    target_group  = "${local.controller_arn_prefix}:targetgroup/*/*"
    listener      = "${local.controller_arn_prefix}:listener/app/*/*/*"
    rule          = "${local.controller_arn_prefix}:listener-rule/app/*/*/*/*"
  }
  controller_owned_tags = {
    "aws:ResourceTag/elbv2.k8s.aws/cluster" = var.cluster_name
    "aws:ResourceTag/ingress.k8s.aws/stack" = "contact-form/contact-form"
  }
  controller_request_tags = {
    "aws:RequestTag/elbv2.k8s.aws/cluster" = var.cluster_name
    "aws:RequestTag/ingress.k8s.aws/stack" = "contact-form/contact-form"
  }

  controller_policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "CreateELBServiceLinkedRole"
        Effect   = "Allow"
        Action   = ["iam:CreateServiceLinkedRole"]
        Resource = "arn:aws:iam::${var.aws_account_id}:role/aws-service-role/elasticloadbalancing.amazonaws.com/AWSServiceRoleForElasticLoadBalancing"
        Condition = {
          StringEquals = { "iam:AWSServiceName" = "elasticloadbalancing.amazonaws.com" }
        }
      },
      {
        Sid    = "DiscoverRegionalNetworkingAndLoadBalancers"
        Effect = "Allow"
        Action = [
          "ec2:DescribeAccountAttributes", "ec2:DescribeAddresses",
          "ec2:DescribeAvailabilityZones", "ec2:DescribeInstances",
          "ec2:DescribeInternetGateways", "ec2:DescribeNetworkInterfaces",
          "ec2:DescribeRouteTables", "ec2:DescribeSecurityGroups",
          "ec2:DescribeSubnets", "ec2:DescribeTags", "ec2:DescribeVpcs",
          "elasticloadbalancing:DescribeListenerAttributes",
          "elasticloadbalancing:DescribeListenerCertificates",
          "elasticloadbalancing:DescribeListeners",
          "elasticloadbalancing:DescribeLoadBalancerAttributes",
          "elasticloadbalancing:DescribeLoadBalancers",
          "elasticloadbalancing:DescribeRules", "elasticloadbalancing:DescribeSSLPolicies",
          "elasticloadbalancing:DescribeTags", "elasticloadbalancing:DescribeTargetGroupAttributes",
          "elasticloadbalancing:DescribeTargetGroups", "elasticloadbalancing:DescribeTargetHealth",
        ]
        Resource = "*"
        Condition = {
          StringEquals = { "aws:RequestedRegion" = var.aws_region }
        }
      },
      {
        Sid      = "ReadSelectedCertificate"
        Effect   = "Allow"
        Action   = ["acm:DescribeCertificate"]
        Resource = local.certificate_arn
      },
      {
        Sid      = "CreateOwnedApplicationLoadBalancer"
        Effect   = "Allow"
        Action   = ["elasticloadbalancing:CreateLoadBalancer"]
        Resource = local.controller_arns.load_balancer
        Condition = {
          StringEquals = merge(local.controller_request_tags, {
            "elasticloadbalancing:Scheme" = "internet-facing"
          })
        }
      },
      {
        Sid      = "CreateOwnedTargetGroup"
        Effect   = "Allow"
        Action   = ["elasticloadbalancing:CreateTargetGroup"]
        Resource = local.controller_arns.target_group
        Condition = {
          StringEquals = local.controller_request_tags
        }
      },
      {
        Sid      = "CreateListenerOnOwnedLoadBalancer"
        Effect   = "Allow"
        Action   = ["elasticloadbalancing:CreateListener"]
        Resource = local.controller_arns.load_balancer
        Condition = {
          StringEquals = local.controller_owned_tags
        }
      },
      {
        Sid      = "CreateRuleOnOwnedListener"
        Effect   = "Allow"
        Action   = ["elasticloadbalancing:CreateRule"]
        Resource = local.controller_arns.listener
        Condition = {
          StringEquals = local.controller_owned_tags
        }
      },
      {
        Sid      = "TagResourcesDuringCreation"
        Effect   = "Allow"
        Action   = ["elasticloadbalancing:AddTags"]
        Resource = values(local.controller_arns)
        Condition = {
          StringEquals = merge(local.controller_request_tags, {
            "elasticloadbalancing:CreateAction" = [
              "CreateLoadBalancer", "CreateTargetGroup", "CreateListener", "CreateRule",
            ]
          })
        }
      },
      {
        Sid      = "UpdateTagsOnOwnedResources"
        Effect   = "Allow"
        Action   = ["elasticloadbalancing:AddTags", "elasticloadbalancing:RemoveTags"]
        Resource = values(local.controller_arns)
        Condition = {
          StringEquals = local.controller_owned_tags
        }
      },
      {
        Sid      = "NeverRemoveOwnershipTags"
        Effect   = "Deny"
        Action   = ["elasticloadbalancing:RemoveTags"]
        Resource = values(local.controller_arns)
        Condition = {
          "ForAnyValue:StringEquals" = {
            "aws:TagKeys" = ["elbv2.k8s.aws/cluster", "ingress.k8s.aws/stack"]
          }
        }
      },
      {
        Sid      = "NeverChangeClusterOwnership"
        Effect   = "Deny"
        Action   = ["elasticloadbalancing:AddTags"]
        Resource = values(local.controller_arns)
        Condition = {
          Null = { "aws:RequestTag/elbv2.k8s.aws/cluster" = "false" }
          StringNotEquals = {
            "aws:RequestTag/elbv2.k8s.aws/cluster" = var.cluster_name
          }
        }
      },
      {
        Sid      = "NeverChangeStackOwnership"
        Effect   = "Deny"
        Action   = ["elasticloadbalancing:AddTags"]
        Resource = values(local.controller_arns)
        Condition = {
          Null = { "aws:RequestTag/ingress.k8s.aws/stack" = "false" }
          StringNotEquals = {
            "aws:RequestTag/ingress.k8s.aws/stack" = "contact-form/contact-form"
          }
        }
      },
      {
        Sid    = "ManageOwnedLoadBalancer"
        Effect = "Allow"
        Action = [
          "elasticloadbalancing:DeleteLoadBalancer",
          "elasticloadbalancing:ModifyLoadBalancerAttributes",
          "elasticloadbalancing:SetIpAddressType", "elasticloadbalancing:SetSubnets",
        ]
        Resource  = local.controller_arns.load_balancer
        Condition = { StringEquals = local.controller_owned_tags }
      },
      {
        Sid    = "ManageOwnedTargetGroup"
        Effect = "Allow"
        Action = [
          "elasticloadbalancing:DeleteTargetGroup", "elasticloadbalancing:DeregisterTargets",
          "elasticloadbalancing:ModifyTargetGroup", "elasticloadbalancing:ModifyTargetGroupAttributes",
          "elasticloadbalancing:RegisterTargets",
        ]
        Resource  = local.controller_arns.target_group
        Condition = { StringEquals = local.controller_owned_tags }
      },
      {
        Sid    = "ManageOwnedListener"
        Effect = "Allow"
        Action = [
          "elasticloadbalancing:AddListenerCertificates", "elasticloadbalancing:DeleteListener",
          "elasticloadbalancing:ModifyListener", "elasticloadbalancing:ModifyListenerAttributes",
          "elasticloadbalancing:RemoveListenerCertificates",
        ]
        Resource  = local.controller_arns.listener
        Condition = { StringEquals = local.controller_owned_tags }
      },
      {
        Sid    = "ManageOwnedRule"
        Effect = "Allow"
        Action = [
          "elasticloadbalancing:DeleteRule", "elasticloadbalancing:ModifyRule",
          "elasticloadbalancing:SetRulePriorities",
        ]
        Resource  = local.controller_arns.rule
        Condition = { StringEquals = local.controller_owned_tags }
      },
    ]
  }
}
