# Disposable workload

This Terraform root is a locally validated draft. It has **not** been applied in AWS. Apply the persistent foundation first, including the validated certificate for `cheelong.xyz`, and review Singapore costs and permissions before any workload plan or apply.

`backend.tf` declares the encrypted S3 state key `workload/terraform.tfstate` with S3 lockfiles and an account restriction. Before a live `terraform init`, inspect local and S3 state as described in [Terraform roots](../README.md#backend-initialization). The earlier `init -backend=false` was for syntax checks only; do not treat its provider cache as initialized remote state.

The intended runtime contains a VPC across two AZs, two public ALB/NAT subnets, two private worker subnets, two isolated RDS subnets, one EKS managed worker per AZ, a private-only EKS API, a private SSM relay, Multi-AZ PostgreSQL, ECR, and an empty application secret. RDS manages the master secret. A later Kubernetes setup Job initializes the database and writes the restricted application secret. No database password is a Terraform input or output.

## Controller and Ingress contract

The controller role has an inline IAM policy using exact account and region ARNs plus the cluster and Ingress stack ownership tags for writes. The inline form fits IAM's 10,240-character aggregate role limit; the rendered size must be checked before deployment. It omits security-group mutations and unused capacity reservation, WAF, Shield, and Cognito permissions. The pinned controller v2.14.1 sends listener and rule tags in its create calls; create-time `AddTags` is scoped to the matching creation actions. Ansible must install chart `1.14.0` with `image.tag=v2.14.1` and `enableBackendSecurityGroup=false` and `enableManageBackendSecurityGroupRules=false`. The Ingress must:

- use `alb.ingress.kubernetes.io/security-groups` with Terraform's `alb_security_group_id` output;
- set `alb.ingress.kubernetes.io/manage-backend-security-group-rules: "false"`;
- use `alb.ingress.kubernetes.io/target-type: ip`, port 8000 and `/health/ready`;
- use the two `public_subnet_ids`, the foundation's ACM certificate, and no WAF/Shield annotations.

Terraform owns the ALB and worker security-group rules. The Ingress and controller create the **single physical ALB**. The controller will not create or modify security groups under this contract. Review the rendered policy and live reconciliation before deployment; the scoped draft has not been simulated or attached. See [preflight and permissions](../../docs/preflight.md).

## Verified version file

EKS minor, all three add-on versions, managed node AL2023 release, its SSM parameter version and AMI ID, and the relay AL2023 AMI are required Terraform inputs without defaults. The checked-in [example](version-inputs.tfvars.json.example) contains invalid placeholders; preflight fills the two node evidence fields in the verified output. Follow the [preflight procedure](../../docs/preflight.md) to choose and verify values, then retain `.local/verified-workload.tfvars.json` through teardown.

Before the full deployer plan below, complete **both target stages** in the [required first-create procedure](../../docs/workload-permissions.md#required-trusted-bootstrap-and-demo-guide-change) under the [live-demo approval gates](../../docs/live-demo.md#4-read-only-pins-and-fresh-runtime-plan). In the reconciled backend, a separate trusted administrator first applies the reviewed key/app-secret target, then rebinds exact KMS/secret ARNs and validates/simulates/attaches those policies. Keep all four OIDC IAM grants at the inert `id/BOOTSTRAP-PLACEHOLDER`. The deployer next plans `-target=aws_eks_cluster.main` with the **same verified variables**, inspects its VPC/NAT/role dependencies, updates the Singapore estimate and credits, and gets separate explicit approval before applying the saved cluster plan. EKS paid time starts at cluster creation. Read the issuer with `aws eks describe-cluster`; the administrator generates ignored mode-600 `.local/deployer-iam-provisioning.json` from the tracked inert template, replaces all four OIDC placeholders in that copy, validates/simulates and publishes/attaches the copy. Only then make the fresh full plan below. Rebuild repeats both targets and regenerates the review copy for the new issuer. From the repository root:

```bash
WORKLOAD_VARS="$PWD/.local/verified-workload.tfvars.json"
# Precondition: both approved targets, exact KMS/secret/OIDC rebinding, and policy attachment are complete.
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" -out=workload.tfplan
terraform -chdir=terraform/workload show -no-color workload.tfplan
# Apply only this reviewed saved plan after the cost/credit check and explicit approval.
terraform -chdir=terraform/workload apply workload.tfplan
```

The reviewed saved plan embeds these inputs. For teardown, use `plan -destroy -input=false -var-file="$WORKLOAD_VARS" -out=workload-destroy.tfplan`, review it with `show`, and apply that saved plan after Ansible cleanup.

## Lifecycle

The foundation owns `/aws/eks/contact-form-eks/cluster` and the fixed-name RDS `postgresql` and `upgrade` log groups with seven-day retention, so their logs survive runtime teardown. Workload planning requires the foundation's `rds_log_group_names` output to match both expected names. Check both actual states for prior RDS log-group ownership and complete any deliberate state handoff before applying; see [backend initialization](../README.md#backend-initialization). The setup Job and Flask use distinct IRSA roles. The app can read only the application secret; the setup Job can read the RDS master secret and read/write the app secret.

Before `terraform destroy`, Ansible must remove the application DNS alias and Ingress, then wait until the controller has deleted the ALB and target groups. Destroying this root deliberately deletes RDS and all submissions, the worker instances, NAT gateways, ECR images, and runtime secrets. Keep the foundation and state bucket. Check AWS for orphaned ALBs, NAT gateways, EIPs and RDS instances after destroy.

For local checks with the provider already installed (no AWS access or state migration):

```bash
terraform -chdir=terraform/workload fmt -check
terraform -chdir=terraform/workload validate -no-color
```

A successful validate checks Terraform syntax and provider schema. It does not verify IAM permissions, pricing, quotas, Singapore engine versions, or live deployment.
