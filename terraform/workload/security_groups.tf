resource "aws_security_group" "alb" {
  name_prefix = "contact-form-alb-"
  description = "Ingress for the controller-created public ALB"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "contact-form-alb" }
}
resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  description       = "HTTP to HTTPS redirect"
}
resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "Public HTTPS"
}

resource "aws_security_group" "nodes" {
  name_prefix = "contact-form-nodes-"
  description = "EKS worker instances and pod ENIs"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "contact-form-nodes" }
}
resource "aws_vpc_security_group_ingress_rule" "node_self" {
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_security_group.nodes.id
  ip_protocol                  = "-1"
  description                  = "Pod and node communication within node group"
}
resource "aws_vpc_security_group_ingress_rule" "node_from_alb" {
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
  description                  = "ALB to Flask IP targets"
}
resource "aws_vpc_security_group_egress_rule" "nodes_outbound" {
  security_group_id = aws_security_group.nodes.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "AWS APIs, image pulls, EKS control plane and RDS"
}
resource "aws_vpc_security_group_egress_rule" "alb_to_nodes" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.nodes.id
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
  description                  = "Flask target port"
}

resource "aws_security_group" "rds" {
  name_prefix = "contact-form-rds-"
  description = "RDS PostgreSQL from EKS worker and pod ENIs only"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "contact-form-rds" }
}
resource "aws_vpc_security_group_ingress_rule" "rds_from_nodes" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_security_group.nodes.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "Application and database setup Job"
}

resource "aws_security_group" "relay" {
  name_prefix = "contact-form-relay-"
  description = "Private SSM management relay, no inbound access"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "contact-form-relay" }
}
resource "aws_vpc_security_group_egress_rule" "relay_https" {
  security_group_id = aws_security_group.relay.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "SSM public endpoints via NAT, and private EKS API"
}
resource "aws_vpc_security_group_egress_rule" "relay_dns_udp" {
  security_group_id = aws_security_group.relay.id
  cidr_ipv4         = aws_vpc.main.cidr_block
  from_port         = 53
  to_port           = 53
  ip_protocol       = "udp"
  description       = "VPC DNS"
}
resource "aws_vpc_security_group_egress_rule" "relay_dns_tcp" {
  security_group_id = aws_security_group.relay.id
  cidr_ipv4         = aws_vpc.main.cidr_block
  from_port         = 53
  to_port           = 53
  ip_protocol       = "tcp"
  description       = "VPC DNS"
}

# EKS also creates a managed cluster security group. Its ID exists after cluster creation.
resource "aws_vpc_security_group_ingress_rule" "api_from_relay" {
  security_group_id            = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
  referenced_security_group_id = aws_security_group.relay.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
  description                  = "Private API from SSM relay"
}
resource "aws_vpc_security_group_ingress_rule" "api_from_nodes" {
  security_group_id            = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
  referenced_security_group_id = aws_security_group.nodes.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
  description                  = "Kubelet to private API"
}
resource "aws_vpc_security_group_ingress_rule" "nodes_from_control_plane" {
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
  from_port                    = 10250
  to_port                      = 10250
  ip_protocol                  = "tcp"
  description                  = "Control plane to kubelet"
}
