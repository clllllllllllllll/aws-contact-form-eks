# Disposable workload

This Terraform root is a locally validated draft. It has **not** been applied in AWS. Apply the persistent foundation first, including the validated certificate for `cheelong.xyz`, and review Singapore costs and permissions before any workload plan or apply.

`backend.tf` declares the encrypted S3 state key `workload/terraform.tfstate` with S3 lockfiles and an account restriction. Before a live `terraform init`, inspect local and S3 state as described in [Terraform roots](../README.md#backend-initialization). The earlier `init -backend=false` was for syntax checks only; do not treat its provider cache as initialized remote state.

The intended runtime contains a VPC across two AZs, two public ALB/NAT subnets, two private worker subnets, two isolated RDS subnets, one EKS managed worker per AZ, a private-only EKS API, a private SSM relay, Multi-AZ PostgreSQL, ECR, and an empty application secret. RDS manages the master secret. A later Kubernetes setup Job initializes the database and writes the restricted application secret. No database password is a Terraform input or output.

## Controller and Ingress contract

The controller IAM policy is derived from the pinned upstream v2.14.1 policy. It omits security-group mutations and unused WAF/Shield mutations. Ansible must install chart `1.14.0` with `image.tag=v2.14.1` and `enableBackendSecurityGroup=false` and `enableManageBackendSecurityGroupRules=false`. The Ingress must:

- use `alb.ingress.kubernetes.io/security-groups` with Terraform's `alb_security_group_id` output;
- set `alb.ingress.kubernetes.io/manage-backend-security-group-rules: "false"`;
- use `alb.ingress.kubernetes.io/target-type: ip`, port 8000 and `/health/ready`;
- use the two `public_subnet_ids`, the foundation's ACM certificate, and no WAF/Shield annotations.

Terraform owns the ALB and worker security-group rules. The Ingress and controller create the **single physical ALB**. The controller will not create or modify security groups under this contract. Broader permissions retained from the upstream controller policy must be reviewed against the deployed actions; an IAM role bound to the controller service account limits who can exercise them.

## Lifecycle

The foundation owns `/aws/eks/contact-form-eks/cluster` so audit events survive runtime teardown until their seven-day retention expires. The cluster name is fixed to match that group. The setup Job and Flask use distinct IRSA roles. The app can read only the application secret; the setup Job can read the RDS master secret and read/write the app secret.

Before `terraform destroy`, Ansible must remove the application DNS alias and Ingress, then wait until the controller has deleted the ALB and target groups. Destroying this root deliberately deletes RDS and all submissions, the worker instances, NAT gateways, ECR images, and runtime secrets. Keep the foundation and state bucket. Check AWS for orphaned ALBs, NAT gateways, EIPs and RDS instances after destroy.

For local checks with the provider already installed (no AWS access or state migration):

```bash
terraform -chdir=terraform/workload fmt -check
terraform -chdir=terraform/workload validate -no-color
```

A successful validate checks Terraform syntax and provider schema. It does not verify IAM permissions, pricing, quotas, Singapore engine versions, or live deployment.
