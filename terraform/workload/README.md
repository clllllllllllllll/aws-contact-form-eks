# Disposable workload

**Current status (28 September 2026):** The earlier partial apply failed at the EKS node-group role lookup and was destroyed. The approved full deployment then succeeded: two Ready workers and two Ready Flask pods, one Ingress-created ALB, HTTPS `200`, POST `/thanks`, RDS readback `id=1`, and an Ansible rerun with `changed=0`. Teardown needed two Terraform plans: the first deleted 70 of 72 resources and failed to disassociate both EIPs; NAT deletion had already removed their associations, and a fresh two-EIP plan released them. Workload state is empty, and a later scoped residual inventory completed with no actionable workload resources observed. The state bucket and foundation remain. A one-shot destroy, fresh rebuild and actual project FSBP control results still need verification. Before another paid build, verify effective IAM permissions, fresh version inputs, state and cost. Old plans and kubeconfig cannot be reused.

`backend.tf` declares the encrypted S3 state key `workload/terraform.tfstate` with S3 lockfiles and an account restriction. The backend was initialized for the first target. Before future initialization or apply, inspect local and S3 state as described in [Terraform roots](../README.md#backend-initialization). The earlier `init -backend=false` was for syntax checks only; do not treat its provider cache as initialized remote state.

The intended runtime contains a VPC across two AZs, two public ALB/NAT subnets, two private worker subnets, two isolated RDS subnets, one EKS managed worker per AZ, a private-only EKS API, a private SSM relay, Multi-AZ PostgreSQL, ECR, and application-secret metadata. RDS manages the master secret. A later Kubernetes setup Job initializes the database and writes the restricted application secret. No database password is a Terraform input or output.

## Controller and Ingress contract

The controller role has an inline IAM policy using exact account and region ARNs plus the cluster and Ingress stack ownership tags for writes. The inline form fits IAM's 10,240-character aggregate role limit; the rendered size must be checked before deployment. It omits security-group mutations and unused capacity reservation, WAF, Shield, and Cognito permissions. The pinned controller v2.14.1 sends listener and rule tags in its create calls; create-time `AddTags` is scoped to the matching creation actions. Ansible must install chart `1.14.0` with `image.tag=v2.14.1` and `enableBackendSecurityGroup=false` and `enableManageBackendSecurityGroupRules=false`. The Ingress must:

- use `alb.ingress.kubernetes.io/security-groups` with Terraform's `alb_security_group_id` output;
- set `alb.ingress.kubernetes.io/manage-backend-security-group-rules: "false"`;
- use `alb.ingress.kubernetes.io/target-type: ip`, port 8000 and `/health/ready`;
- use the two `public_subnet_ids`, the foundation's ACM certificate, and no WAF/Shield annotations.

Terraform provides the ALB security group, worker security-group rules and the controller IAM role/policy. Ansible applies the Ingress; the controller creates and owns the **single physical ALB**, listeners and target groups. Terraform declares no ALB resource. The controller will not create or modify security groups under this contract. The full deployment exercised the controller and one ALB; keep the rendered-policy and effective-permission review in the next build because policy simulation has not been recorded. See [preflight](#read-only-preflight) and [service policy scope](#service-policy-scope).

## Service policy scope

The six workload service drafts, IAM provisioning draft, IAM role-write draft, and workstation helper draft use stable account/Region/name patterns. An IAM administrator publishes and verifies them once, then attaches only the policies needed for each approved operation. The [temporary first-creation draft](../policies/workload/deployer-workload-bootstrap-temporary-draft.json) remains short-lived because tagged KMS key creation needs `kms:TagResource` on a generated key ARN. A permanent grant on `key/*` could tag another key into the project's authorized set. The secret creation grant stays in that same temporary policy; its name prefix alone cannot prove ownership of an existing untagged secret.

| Draft | Resource scope and window |
| --- | --- |
| [Temporary bootstrap](../policies/workload/deployer-workload-bootstrap-temporary-draft.json) | First target only: tagged symmetric key and `contact-form/app-*` secret creation, creation tags and initial reads. Attach immediately before that reviewed two-create plan; detach immediately afterward, including after failure. A reviewed policy may be retained detached for another run. |
| [EC2 network](../policies/workload/deployer-workload-service-draft-ec2-network.json) | VPC, six subnets, NAT/EIPs, routes, owned-EIP disassociation for teardown, and regional refresh reads. |
| [EC2 compute](../policies/workload/deployer-workload-service-draft-ec2-compute.json) | Project security groups/rules, relay, worker launch template and root-volume tags. |
| [EKS](../policies/workload/deployer-workload-service-draft-eks.json) | Private cluster, deployer access, three add-ons and two node groups. The encryption key condition matches a Singapore/account KMS key UUID shape; KMS grant authority is separately restricted to an already tagged project key. |
| [KMS](../policies/workload/deployer-workload-service-draft-kms.json) | Post-create actions on a Singapore/account key UUID with all three existing ownership tags; no create, tag or untag grant. `CreateGrant` still permits grantee choice and must be attached only when needed. |
| [RDS](../policies/workload/deployer-workload-service-draft-rds.json) | Named private Multi-AZ database and subnet group, with RDS-managed master secret. |
| [Secrets Manager/ECR](../policies/workload/deployer-workload-service-draft-secret-ecr.json) | App-secret metadata and deletion under `contact-form/app-*`, guarded by all three existing ownership tags; no value read/write or tag mutation. Named ECR repository permissions are unchanged. |

The RDS policy restricts requested create storage to 20 GiB and requested modify storage to at most 40 GiB with class `db.t4g.small`. IAM has no condition for `MaxAllocatedStorage`: Terraform sets its autoscaling ceiling to 40 GiB, but IAM does **not** enforce a hard 40-GiB ceiling. Review both storage values in the exact saved plan and keep the RDS write grant attached only for a time-limited apply or destroy window; monitor actual storage and charges.

The provider tags owned resources `Project=aws-contact-form-eks`, `ManagedBy=Terraform`, and `Lifecycle=workload`. Verify those tags and key-policy IAM delegation on every new KMS key, app secret and OIDC provider before destructive actions. A name or matching tag is not, by itself, proof of Terraform ownership. The four OIDC statements match the regional EKS issuer path with a 32-character ID and require the ownership tags for management. Their initial tag grant accepts only the three fixed ownership values and rejects a provider with conflicting existing ownership tags; a pre-existing provider lacking ownership tags on the same issuer path remains a residual risk. Inventory that path before publication and each apply, and keep IAM provisioning attached only for the required window. Do not add a permanent wildcard key-tag grant to close a permission gap.

The recorded state-access grant is inline and consumes no managed slot. Six workload service policies plus two IAM policies use eight of the default ten managed-policy attachments; the helper makes nine, and **one** of temporary bootstrap, preflight, or runtime inventory makes ten. Detach completed foundation-stage policies and rotate these optional windows instead of requesting more slots or keeping all grants active. The administrator checks actual attachments, policy versions, boundaries and service controls in the Console; `iam:ListAttachedUserPolicies` is denied to the deployer. Policy JSON parsing and Terraform plans do not prove effective permissions.

## Read-only preflight

EKS minor, all three add-on versions, managed-node AL2023 release, its SSM parameter version and AMI ID, and the relay AL2023 AMI are required Terraform inputs without defaults. The checked-in [example](version-inputs.tfvars.json.example) has deliberately invalid placeholders. With a working non-root `contact-form-deployer` login in account `203888389134`, Region `ap-southeast-1`, and workstation Python dependencies installed, run from the repository root:

```bash
umask 077
mkdir -p .local
chmod 700 .local
cp terraform/workload/version-inputs.tfvars.json.example .local/workload-candidate.tfvars.json
chmod 600 .local/workload-candidate.tfvars.json
# Edit the candidate to contain supported Singapore EKS/add-on/node and relay AMI choices.
python3 scripts/preflight.py --profile contact-form-deployer --versions-file .local/workload-candidate.tfvars.json
```

The trimmed [preflight read policy](../policies/workstation/preflight-read-policy.json) is attached to the deployer and grants no provisioning permission. A CLI read verified the effective Singapore Standard On-Demand quota is **8 vCPUs**. Preflight returned `READY` before the first attempt; rerun it before a rebuild because inputs and available capacity can change. The previous workload has been destroyed. Every required AWS read must succeed: account/Region, two available standard AZs, applied Standard EC2 vCPU quota `L-1216C47A`, current Standard instance occupancy, EKS support and add-on compatibility, Multi-AZ PostgreSQL 16 `db.t4g.small` orderability, and available Amazon-owned AL2023 AMIs. A fresh stack needs **6 free vCPUs** for two `t3.medium` workers and one `t3.micro` relay; simultaneous managed-node updates can reach **14 vCPUs**. Use `--require-update-headroom` when that update capacity must be available now. This is a fresh-stack quota check, not a repeat readiness test on a running stack or an instance-capacity guarantee.

For a first pin, preflight checks the current Singapore recommended node release and writes its SSM parameter version and AMI ID. For a frozen older release, supply **both** evidence fields from an earlier verified file; the script reads that exact parameter version and reports recommendation drift. `READY` (exit 0) atomically writes ignored mode-600 `.local/verified-workload.tfvars.json`; `BLOCKED` (2) means a prerequisite failed and `INCOMPLETE` (1) means a read, credential or response failed. A failed run preserves an existing verified file, and a different successful pin cannot overwrite it: choose a new `--verified-file` path and set `WORKLOAD_VARS` to that path. Copy the verified file securely to the rehearsal workstation, recheck it there as a separate candidate, and retain it through destroy. Expired credentials are `INCOMPLETE`, never readiness.

## Two target first creation and repeatable IAM

Complete the retained foundation and certificate stages, [backend/state reconciliation](../README.md#backend-initialization), read-only preflight, current Singapore cost and credit check, and **fresh saved-plan review before each apply**. Present the estimate and obtain the owner's confirmation before each new paid deployment. Keep a total paid-runtime clock. Reconcile an already managed resource rather than recreating it. Use the same verified inputs and S3 backend through both targets and the full plan. Old plans and kubeconfig do not apply to a new workload.

Before a paid target, an IAM administrator publishes the reusable drafts as reviewed default policy versions **once** and verifies attachments, IAM policy simulations and a direct `iam:GetRole` read for `AWSServiceRoleForAmazonEKSNodegroup`. The old published KMS, secret, OIDC and helper versions contain destroyed resource IDs; replace those versions with the tracked pattern-based drafts once. Check the actual account/Region, the retained Route 53 zone, the absence of unrelated resources matching the project patterns, and existing IAM boundaries. The separate role-write policy can update trust and arbitrary inline policies on four named roles without a permissions boundary; attach it only for monitored apply/change/destroy windows. [Policy scope and slot counts](#service-policy-scope) apply throughout. The deployer cannot publish policy versions.

For the first target, the administrator attaches the reviewed `ContactFormWorkloadBootstrapTemporary` policy for a short window. Its `kms:CreateKey` request must have the three fixed tags, Singapore Region, a symmetric encryption key and the specified origin. Its `kms:TagResource` grant still spans generated key IDs and can tag another key while attached if that key policy permits, regardless of its existing tags; inspect existing keys and detach this grant immediately after the target. The app-secret create/tag grant is limited to `contact-form/app-*` and the three requested ownership tags. Neither grant is needed in the later cluster or full plan. Check that the actual user has a free managed-policy slot before attaching.

From the repository root, keep plans in ignored, mode-600 `.local/` files. The first plan must contain **only** `aws_kms_key.eks` and `aws_secretsmanager_secret.app`, both creates, with the expected tags, seven-day key deletion window and secret metadata. Stop on any other action or a failed IAM or cost check:

```bash
umask 077
mkdir -p .local
chmod 700 .local
export AWS_PROFILE=contact-form-deployer AWS_REGION=ap-southeast-1 AWS_DEFAULT_REGION=ap-southeast-1
WORKLOAD_VARS="${WORKLOAD_VARS:-$PWD/.local/verified-workload.tfvars.json}"
BOOTSTRAP_PLAN="$PWD/.local/workload-bootstrap.tfplan"
test -s "$WORKLOAD_VARS" && git check-ignore -q "$BOOTSTRAP_PLAN" || exit 1
[[ "$(aws sts get-caller-identity --query Arn --output text)" == arn:aws:iam::203888389134:user/contact-form-deployer ]] || exit 1
terraform -chdir=terraform/workload init -input=false || exit 1
rm -f -- "$BOOTSTRAP_PLAN"
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" \
  -target=aws_kms_key.eks -target=aws_secretsmanager_secret.app -out="$BOOTSTRAP_PLAN" &&
chmod 600 "$BOOTSTRAP_PLAN" &&
terraform -chdir=terraform/workload show -no-color "$BOOTSTRAP_PLAN"
```

After reviewing the exact saved plan and confirming its approved scope and cost, apply it. The administrator then detaches the temporary policy **even if apply fails**. Retain it detached only after checking that its default version still matches this draft; deleting it is also acceptable, but a later recreation must use the same reviewed draft. If the target fails, reconcile state and AWS resources before continuing.

```bash
terraform -chdir=terraform/workload apply "$BOOTSTRAP_PLAN"
terraform -chdir=terraform/workload state show aws_kms_key.eks
terraform -chdir=terraform/workload state show aws_secretsmanager_secret.app
```

Verify the new key and secret ARNs, tags and Terraform addresses against read-only metadata. Their generated IDs are **runtime evidence**, never replacements in an IAM JSON file. The KMS draft grants only post-create operations on a key with all three tags. The secret/ECR draft grants only app-secret metadata and deletion on a matching prefix **and** those tags. The EKS create condition checks the regional/account key UUID shape; because it cannot inspect the referenced key's tags, also verify the separate `kms:DescribeKey`/`kms:CreateGrant` authorization resolves to this owned key. Stop if another key under the pattern carries the project tags or if an unrelated policy grants broader KMS authority.

Plan the cluster target with the durable service and IAM policies attached in their reviewed windows. The target may create a VPC, routes, NAT gateways and roles, and starts paid EKS time. Inspect every dependency and confirm the private-only API, encryption key and current cost before applying:

```bash
CLUSTER_PLAN="$PWD/.local/workload-cluster.tfplan"
git check-ignore -q "$CLUSTER_PLAN" || exit 1
rm -f -- "$CLUSTER_PLAN"
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" \
  -target=aws_eks_cluster.main -out="$CLUSTER_PLAN" &&
chmod 600 "$CLUSTER_PLAN" &&
terraform -chdir=terraform/workload show -no-color "$CLUSTER_PLAN"
```

After reviewing the saved plan against the approved scope and allowance:

```bash
terraform -chdir=terraform/workload apply "$CLUSTER_PLAN"
terraform -chdir=terraform/workload state show aws_eks_cluster.main
CLUSTER_NAME="$(terraform -chdir=terraform/workload output -raw cluster_name)"
OIDC_ISSUER="$(aws eks describe-cluster --region "$AWS_REGION" --name "$CLUSTER_NAME" --query 'cluster.identity.oidc.issuer' --output text)"
[[ "$OIDC_ISSUER" =~ ^https://oidc\.eks\.ap-southeast-1\.amazonaws\.com/id/[[:alnum:]]{32}$ ]] || exit 1
printf '%s\n' "$OIDC_ISSUER"
```

Compare the cluster name, private endpoint, encryption key and live issuer with state. The IAM provisioning policy's regional issuer pattern already covers the new 32-character ID; **do not publish a new policy version or paste this issuer into a policy**. Terraform's pod-role trust still contains the exact live issuer. The cluster target must not include the OIDC provider. For the full plan, inventory any pre-existing OIDC providers on the same regional path; the create-time tagging allowance can tag a provider lacking ownership tags if one exists, so stop and resolve that collision before apply.

Make a fresh full plan from post-cluster state. The key, app-secret metadata and cluster must remain in state without replacement. Review workers, relay, IRSA, ECR, RDS and OIDC provider, current IAM attachments and costs. The earlier plan failed on the node-group service-role lookup and was invalidated by teardown. Apply only the freshly reviewed plan:

```bash
FULL_PLAN="$PWD/.local/workload.tfplan"
git check-ignore -q "$FULL_PLAN" || exit 1
rm -f -- "$FULL_PLAN"
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" -out="$FULL_PLAN" &&
chmod 600 "$FULL_PLAN" &&
terraform -chdir=terraform/workload show -no-color "$FULL_PLAN"
```

After confirming the plan remains within the approved scope and allowance:

```bash
terraform -chdir=terraform/workload apply "$FULL_PLAN"
```

The reviewed saved plan embeds its inputs. For a fully deployed stack, after Ansible cleanup, set `umask 077`, save `plan -destroy -input=false -var-file="$WORKLOAD_VARS" -out="$PWD/.local/workload-destroy.tfplan"`, verify mode 600, review it with `show`, and apply that exact saved plan under the approved teardown window. If Terraform only partly deploys and no Ingress or ALB exists, use the verification gate below first.

## Lifecycle

The foundation owns `/aws/eks/contact-form-eks/cluster` and the fixed-name RDS `postgresql` and `upgrade` log groups with seven-day retention, so their logs survive runtime teardown. Workload planning requires the foundation's `rds_log_group_names` output to match both expected names. Check both actual states for prior RDS log-group ownership and complete any deliberate state handoff before applying; see [backend initialization](../README.md#backend-initialization). The setup Job and Flask use distinct IRSA roles. The app can read only the application secret; the setup Job can read the RDS master secret and read/write the app secret.

For a fully deployed stack, follow the [Ansible cleanup sequence](../../ansible/README.md#cleanup-before-terraform-destroy) before workload destroy: remove the application DNS alias and Ingress, then wait until the controller has deleted the ALB and target groups. Destroying this root deliberately deletes RDS and all submissions, the worker instances, NAT gateways, ECR images, and runtime secrets; KMS key deletion is scheduled. Keep the foundation and state bucket. Use the [scoped residual inventory](../../scripts/README.md#residual-inventory-and-retained-costs) and inspect any orphaned ALB, NAT, EIP, RDS, EBS or backup resources. For a fresh rebuild, rerun preflight, review both new targets and verify the reusable policy versions and current attachments before generating the full plan; never reuse an old plan or kubeconfig.

### Partial deployment teardown before Ansible

Use this path only when no application Ingress, ALB or Kubernetes workload was created; a partial Terraform apply may still have created RDS and the relay. From the repository root, confirm the AWS account/Region and inspect `terraform -chdir=terraform/workload state list`. State alone cannot prove that an out-of-band application or ALB is absent. Independently inspect the project cluster/VPC with scoped AWS reads or the Console: EKS node groups and Kubernetes namespace, Deployment, Service and Ingress resources; EC2 relay instances; ELBv2 load balancers and target groups; RDS instances; and the application Route 53 alias. Confirm no Ingress, ALB or app exists. If a required read is denied or an unexpected resource exists, get authorized evidence or stop and investigate; do not infer absence from a failed read. Skip inapplicable Ansible cleanup only after the absence checks succeed.

Then use the same verified variables and a **fresh full workload destroy plan**, not the earlier 50-addition plan or a targeted destroy. Review every proposed deletion and confirm that foundation resources are excluded. Stop if any precheck, plan, or inventory read fails; do not use an older plan:

```bash
cd /home/limch/projects/aws-contact-form-eks
umask 077
mkdir -p .local
chmod 700 .local
export AWS_PROFILE=contact-form-deployer AWS_REGION=ap-southeast-1 AWS_DEFAULT_REGION=ap-southeast-1
aws sts get-caller-identity
terraform -chdir=terraform/workload state list
WORKLOAD_VARS="$PWD/.local/verified-workload.tfvars.json"
DESTROY_PLAN="$PWD/.local/workload-partial-destroy.tfplan"
test -f "$WORKLOAD_VARS" && git check-ignore -q "$DESTROY_PLAN" &&
rm -f -- "$DESTROY_PLAN" &&
terraform -chdir=terraform/workload plan -destroy -input=false -var-file="$WORKLOAD_VARS" -out="$DESTROY_PLAN" &&
chmod 600 "$DESTROY_PLAN" &&
terraform -chdir=terraform/workload show -no-color "$DESTROY_PLAN"
```

Only after reviewing that exact plan against the already approved teardown scope, in the same shell run:

```bash
[[ "$(stat -c %a "$DESTROY_PLAN")" == 600 ]] &&
terraform -chdir=terraform/workload apply "$DESTROY_PLAN"
```

After apply, run `python3 scripts/check_residual.py --profile contact-form-deployer` and inspect the project VPC, NAT gateways/EIPs, EKS cluster, secret and KMS key status (including any scheduled key deletion). If a residual read is denied, cleanup is unverified; resolve access or check in the Console. Review [retained foundation costs](../../scripts/README.md#residual-inventory-and-retained-costs) separately; a clean workload result does not mean a zero bill.

### Recovery after a partial destroy

**Latest teardown finding:** The first full destroy deleted 70 of 72 planned resources, then both EIPs failed because Terraform called `ec2:DisassociateAddress` and the deployer was denied on `arn:aws:ec2:ap-southeast-1:203888389134:*/*`. NAT gateway deletion had already disassociated the addresses; a fresh plan containing only the two EIPs then released them. The [network draft](../policies/workload/deployer-workload-service-draft-ec2-network.json) now adds `ec2:DisassociateAddress` to the existing owned-network statement, scoped to the account/Region EIP resource pattern and existing Project/Lifecycle tags. AWS documents EIP resource and tag conditions for this action. `AssociationId` is the API input, not an IAM resource type; EC2 must resolve an active association to the tagged EIP for this statement to match. The prior `*/*` denial came after NAT deletion and may indicate that the stale association no longer resolved to an EIP. If EC2 authorizes against that literal wildcard context, this scoped statement will still deny. AWS also lists a network-interface resource for this action, which the existing statement does not cover; do not assume an EIP-only allow is sufficient without an effective-permission test. The next one-shot destroy is therefore unverified; use `--dry-run` on an active project association to check authorization without disassociating it, and retain the guarded two-EIP retry when needed. Do not replace this with an account-wide disassociation grant merely to silence that error. The administrator must publish and simulate this revised network draft once before the next paid build.

In an earlier teardown, the provider's EKS add-on and cluster deletion waiters received `AccessDenied` on `DescribeAddon` and `DescribeCluster` after the deletes. Its EIP cleanup then tried `DisassociateAddress` using stale association IDs after both NAT gateways had been deleted. Treat these as failed waiters or stale state, **not** proof of deletion. With authorized read-only AWS inventory or the Console, check the exact account, Region, cluster, add-on names, VPC, NAT gateways and allocation IDs. Remove an EKS resource address from Terraform state only after independent evidence shows that exact resource is absent. If any read is denied or the resource still exists, stop and fix the read permission or finish deletion; never use state removal to hide a live resource.

For each EIP, confirm its exact allocation ID and `Project=aws-contact-form-eks`, `ManagedBy=Terraform`, `Lifecycle=workload` tags; confirm its NAT gateway is deleted and the allocation has no `AssociationId` or network-interface ID. Only then release that **one exact allocation ID** with the existing scoped permission, verify its absence, and reconcile its specific stale state address if needed. Refresh and make a new full destroy plan before continuing. Do not grant broad `ec2:DisassociateAddress`, release a list of EIPs at once, or remove state for an unverified resource. The earlier denied snapshot read was resolved by the later read-only group grant; a subsequent scoped inventory completed and found no actionable workload resources. This does not confirm one-shot destroy or zero account charges.

For local checks with the provider already installed (no AWS access or state migration):

```bash
terraform -chdir=terraform/workload fmt -check
terraform -chdir=terraform/workload validate -no-color
```

A successful validate checks Terraform syntax and provider schema. It does not verify IAM permissions, pricing, quotas, Singapore engine versions, or live deployment.
