resource "aws_kms_key" "eks" {
  description             = "Encrypt EKS Kubernetes secrets for disposable contact-form cluster"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}
resource "aws_eks_cluster" "main" {
  name     = var.cluster_name
  version  = var.kubernetes_version
  role_arn = aws_iam_role.cluster.arn

  bootstrap_self_managed_addons = false
  enabled_cluster_log_types     = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = false
  }
  upgrade_policy { support_type = "STANDARD" }
  encryption_config {
    provider { key_arn = aws_kms_key.eks.arn }
    resources = ["secrets"]
  }
  vpc_config {
    subnet_ids              = [for az in local.azs : aws_subnet.app[az].id]
    endpoint_private_access = true
    endpoint_public_access  = false
  }
  depends_on = [
    aws_iam_role_policy_attachment.cluster,
    data.terraform_remote_state.foundation,
    aws_route_table_association.app,
  ]
}
resource "aws_eks_access_entry" "deployer" {
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = var.deployer_principal_arn
  type          = "STANDARD"
}
resource "aws_eks_access_policy_association" "deployer" {
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = aws_eks_access_entry.deployer.principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope { type = "cluster" }
}
resource "aws_eks_addon" "vpc_cni" {
  cluster_name             = aws_eks_cluster.main.name
  addon_name               = "vpc-cni"
  addon_version            = var.addon_versions.vpc_cni
  service_account_role_arn = aws_iam_role.irsa["cni"].arn
  depends_on               = [aws_iam_role_policy_attachment.cni]
}
resource "aws_eks_addon" "kube_proxy" {
  cluster_name  = aws_eks_cluster.main.name
  addon_name    = "kube-proxy"
  addon_version = var.addon_versions.kube_proxy
}

resource "aws_launch_template" "nodes" {
  name_prefix = "contact-form-nodes-"
  tags        = { Name = "contact-form-nodes" }
  vpc_security_group_ids = [
    aws_security_group.nodes.id,
    aws_eks_cluster.main.vpc_config[0].cluster_security_group_id,
  ]
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 30
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  tag_specifications {
    resource_type = "instance"
    tags = {
      Name      = "contact-form-eks-worker"
      Project   = "aws-contact-form-eks"
      ManagedBy = "Terraform"
      Lifecycle = "workload"
    }
  }
  tag_specifications {
    resource_type = "volume"
    tags = {
      Name      = "contact-form-eks-worker-root"
      Project   = "aws-contact-form-eks"
      ManagedBy = "Terraform"
      Lifecycle = "workload"
    }
  }
}
resource "aws_eks_node_group" "per_az" {
  for_each        = toset(local.azs)
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.cluster_name}-${index(local.azs, each.key)}"
  node_role_arn   = aws_iam_role.nodes.arn
  subnet_ids      = [aws_subnet.app[each.key].id]
  capacity_type   = "ON_DEMAND"
  instance_types  = [var.node_instance_type]
  ami_type        = "AL2023_x86_64_STANDARD"
  release_version = var.node_release_version
  labels          = { demo_az = each.key }
  scaling_config {
    desired_size = 1
    min_size     = 1
    max_size     = 1
  }
  update_config { max_unavailable = 1 }
  launch_template {
    id      = aws_launch_template.nodes.id
    version = aws_launch_template.nodes.latest_version
  }
  depends_on = [
    aws_iam_role_policy_attachment.nodes_worker,
    aws_iam_role_policy_attachment.nodes_ecr,
    aws_eks_addon.vpc_cni,
    aws_eks_addon.kube_proxy,
    aws_vpc_security_group_ingress_rule.api_from_nodes,
    aws_vpc_security_group_ingress_rule.nodes_from_control_plane,
  ]
}
resource "aws_eks_addon" "coredns" {
  cluster_name  = aws_eks_cluster.main.name
  addon_name    = "coredns"
  addon_version = var.addon_versions.coredns
  depends_on    = [aws_eks_node_group.per_az]
}
