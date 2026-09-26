data "aws_iam_policy_document" "eks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}
data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "cluster" {
  name               = "contact-form-eks-cluster"
  assume_role_policy = data.aws_iam_policy_document.eks_assume.json
}
resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}
resource "aws_iam_role" "nodes" {
  name               = "contact-form-eks-nodes"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}
resource "aws_iam_role_policy_attachment" "nodes_worker" {
  role       = aws_iam_role.nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}
resource "aws_iam_role_policy_attachment" "nodes_ecr" {
  role       = aws_iam_role.nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPullOnly"
}

resource "aws_iam_openid_connect_provider" "cluster" {
  url            = aws_eks_cluster.main.identity[0].oidc[0].issuer
  client_id_list = ["sts.amazonaws.com"]
}

# Each Kubernetes service account has its own trust policy and AWS role.
data "aws_iam_policy_document" "irsa" {
  for_each = {
    cni        = "kube-system:aws-node"
    controller = "kube-system:aws-load-balancer-controller"
    app        = "contact-form:contact-form"
    setup      = "contact-form:contact-form-db-setup"
  }
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.cluster.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.cluster_oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.cluster_oidc_host}:sub"
      values   = ["system:serviceaccount:${each.value}"]
    }
  }
}
resource "aws_iam_role" "irsa" {
  for_each           = data.aws_iam_policy_document.irsa
  name               = "contact-form-${each.key}"
  assume_role_policy = each.value.json
}
resource "aws_iam_role_policy_attachment" "cni" {
  role       = aws_iam_role.irsa["cni"].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

# The restricted policy is derived from vendored upstream v2.14.1.
# Terraform owns ALB/node security group rules; the controller cannot change SGs.
resource "aws_iam_policy" "controller" {
  name   = "contact-form-alb-controller"
  policy = file("${path.module}/policies/controller-policy-restricted.json")
}
resource "aws_iam_role_policy_attachment" "controller" {
  role       = aws_iam_role.irsa["controller"].name
  policy_arn = aws_iam_policy.controller.arn
}

resource "aws_iam_role_policy" "app_secret" {
  name = "read-application-secret"
  role = aws_iam_role.irsa["app"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = aws_secretsmanager_secret.app.arn
    }]
  })
}
resource "aws_iam_role_policy" "database_setup" {
  name = "database-setup-secrets"
  role = aws_iam_role.irsa["setup"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue", "secretsmanager:ListSecretVersionIds"]
      Resource = [
        aws_db_instance.main.master_user_secret[0].secret_arn,
        aws_secretsmanager_secret.app.arn,
      ]
      }, {
      Effect   = "Allow"
      Action   = ["secretsmanager:PutSecretValue"]
      Resource = aws_secretsmanager_secret.app.arn
    }]
  })
}

resource "aws_iam_role" "relay" {
  name               = "contact-form-ssm-relay"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}
resource "aws_iam_role_policy_attachment" "relay" {
  role       = aws_iam_role.relay.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_instance_profile" "relay" {
  name = "contact-form-ssm-relay"
  role = aws_iam_role.relay.name
}
