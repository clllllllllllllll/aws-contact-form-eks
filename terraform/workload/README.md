# Disposable workload

This Terraform root is a locally validated draft. It has **not** been applied in AWS. A live targeted plan was reported to contain exactly two creates, `aws_kms_key.eks` and `aws_secretsmanager_secret.app`; it has not been applied. Apply the persistent foundation first, including the validated certificate for `cheelong.xyz`, and review Singapore costs and permissions before any workload apply.

`backend.tf` declares the encrypted S3 state key `workload/terraform.tfstate` with S3 lockfiles and an account restriction. Before a live `terraform init`, inspect local and S3 state as described in [Terraform roots](../README.md#backend-initialization). The earlier `init -backend=false` was for syntax checks only; do not treat its provider cache as initialized remote state.

The intended runtime contains a VPC across two AZs, two public ALB/NAT subnets, two private worker subnets, two isolated RDS subnets, one EKS managed worker per AZ, a private-only EKS API, a private SSM relay, Multi-AZ PostgreSQL, ECR, and an empty application secret. RDS manages the master secret. A later Kubernetes setup Job initializes the database and writes the restricted application secret. No database password is a Terraform input or output.

## Controller and Ingress contract

The controller role has an inline IAM policy using exact account and region ARNs plus the cluster and Ingress stack ownership tags for writes. The inline form fits IAM's 10,240-character aggregate role limit; the rendered size must be checked before deployment. It omits security-group mutations and unused capacity reservation, WAF, Shield, and Cognito permissions. The pinned controller v2.14.1 sends listener and rule tags in its create calls; create-time `AddTags` is scoped to the matching creation actions. Ansible must install chart `1.14.0` with `image.tag=v2.14.1` and `enableBackendSecurityGroup=false` and `enableManageBackendSecurityGroupRules=false`. The Ingress must:

- use `alb.ingress.kubernetes.io/security-groups` with Terraform's `alb_security_group_id` output;
- set `alb.ingress.kubernetes.io/manage-backend-security-group-rules: "false"`;
- use `alb.ingress.kubernetes.io/target-type: ip`, port 8000 and `/health/ready`;
- use the two `public_subnet_ids`, the foundation's ACM certificate, and no WAF/Shield annotations.

Terraform provides the ALB security group, worker security-group rules and the controller IAM role/policy. Ansible applies the Ingress; the controller creates and owns the **single physical ALB**, listeners and target groups. Terraform declares no ALB resource. The controller will not create or modify security groups under this contract. Review the rendered policy and live reconciliation before deployment; the scoped draft has not been simulated or attached. See [preflight](#read-only-preflight) and [service policy scope](#service-policy-scope).

## Service policy scope

The six durable workload service policy drafts and one [temporary first-creation draft](../policies/workload/deployer-workload-bootstrap-temporary-draft.json) are separate from the [IAM and attachment windows](../README.md#iam-and-service-policy-windows). None has been created, attached, simulated or exercised in AWS. Their current scope is:

| Draft | Planned resource scope |
| --- | --- |
| [Temporary bootstrap](../policies/workload/deployer-workload-bootstrap-temporary-draft.json) | Short customer-managed policy attachment on the deployer for tagged symmetric key and `contact-form/app-*` secret creation, creation tags, and post-create read/rotation; detach and delete immediately after the first target |
| [EC2 network](../policies/workload/deployer-workload-service-draft-ec2-network.json) | VPC, six subnets, NAT/EIPs, routes and regional refresh reads |
| [EC2 compute](../policies/workload/deployer-workload-service-draft-ec2-compute.json) | Project security groups/rules, relay, worker launch template and root-volume tags |
| [EKS](../policies/workload/deployer-workload-service-draft-eks.json) | Private cluster, deployer access, three add-ons and two node groups; first cluster creation requires the exact key ARN |
| [KMS](../policies/workload/deployer-workload-service-draft-kms.json) | Post-bootstrap management of the one exact workload key, including EKS grant and seven-day deletion scheduling; no `CreateKey` |
| [RDS](../policies/workload/deployer-workload-service-draft-rds.json) | Named private Multi-AZ database and subnet group, with RDS-managed master secret |
| [Secrets Manager/ECR](../policies/workload/deployer-workload-service-draft-secret-ecr.json) | Post-bootstrap exact application-secret metadata and named ECR repository; no application-secret creation |

The provider tags owned resources `Project=aws-contact-form-eks`, `ManagedBy=Terraform`, and `Lifecycle=workload`. Generated IDs, tag-on-create behavior, EKS-managed security-group context, KMS grants, RDS dependencies, service-linked roles, boundaries and quotas still need live validation. An access denial requires review of the exact call, not a blanket service grant. A 27 September console screenshot shows one managed policy attached directly to the deployer. With the recorded state-access policy inline, the six durable workload policies plus two IAM drafts would use 9 of the default 10 managed user-policy slots. The temporary bootstrap grant needs one managed attachment slot only during its own window. `iam:ListAttachedUserPolicies` is denied on the deployer, so an IAM administrator must check actual attachments and available slots in the Console; detach the completed foundation stage policy or another obsolete stage grant before attaching this grant, and recheck slots before later exact-ARN grants.

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

The trimmed [preflight read policy](../policies/workstation/preflight-read-policy.json) is attached to the deployer and grants no provisioning permission. A CLI read verified the effective Singapore Standard On-Demand quota is **8 vCPUs**. Rerun the full preflight before workload provisioning; no paid EKS, EC2, NAT, or RDS workload has started. Every required AWS read must succeed: account/Region, two available standard AZs, applied Standard EC2 vCPU quota `L-1216C47A`, current Standard instance occupancy, EKS support and add-on compatibility, Multi-AZ PostgreSQL 16 `db.t4g.small` orderability, and available Amazon-owned AL2023 AMIs. A fresh stack needs **6 free vCPUs** for two `t3.medium` workers and one `t3.micro` relay; simultaneous managed-node updates can reach **14 vCPUs**. Use `--require-update-headroom` when that update capacity must be available now. This is a fresh-stack quota check, not a repeat readiness test on a running stack or an instance-capacity guarantee.

For a first pin, preflight checks the current Singapore recommended node release and writes its SSM parameter version and AMI ID. For a frozen older release, supply **both** evidence fields from an earlier verified file; the script reads that exact parameter version and reports recommendation drift. `READY` (exit 0) atomically writes ignored mode-600 `.local/verified-workload.tfvars.json`; `BLOCKED` (2) means a prerequisite failed and `INCOMPLETE` (1) means a read, credential or response failed. A failed run preserves an existing verified file, and a different successful pin cannot overwrite it: choose a new `--verified-file` path and set `WORKLOAD_VARS` to that path. Copy the verified file securely to the rehearsal workstation, recheck it there as a separate candidate, and retain it through destroy. Expired credentials are `INCOMPLETE`, never readiness.

## Two target first creation and OIDC binding

Complete foundation and certificate staging, [backend/state reconciliation](../README.md#backend-initialization), read-only preflight, actual permission review, a current Singapore cost/credit check, and a separately approved saved plan **for each paid apply**. Keep one less-than-ten-hour total paid-runtime clock. If either target is already in workload state, stop and reconcile instead of recreating it. Use the **same** frozen verified file and reconciled workload S3 backend for both targets and the later full plan.

For the first target, the root/account administrator uses the **IAM Console** (no separate administrator CLI profile) to review the [temporary bootstrap policy](../policies/workload/deployer-workload-bootstrap-temporary-draft.json). This is account-prerequisite IAM setup; Terraform manages the workload resources, not this policy. The deployer cannot call `iam:ListAttachedUserPolicies` or `access-analyzer:ValidatePolicy`, so check its actual policies, groups, boundary and attachment slots in the Console. Use the IAM Console policy editor's validation under the administrator login and simulate allowed and denied create, tag, read and rotation actions with correct/wrong tags, secret names and Regions. The draft has passed local JSON checks only; live IAM validation and simulation remain pending.

In **IAM → Policies → Create policy → JSON**, paste the reviewed draft and create customer-managed `ContactFormWorkloadBootstrapTemporary`. In **IAM → Users → contact-form-deployer → Permissions**, detach `ContactFormFoundationStage01` if its completed window is over, confirm a managed attachment slot is free, then attach the temporary policy and verify its exact ARN on the user. Do not alter the existing state-access or preflight inline policies. If the slot, validation, simulation or attachment check fails, stop. The [IAM user inline aggregate limit](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html) is why this temporary grant is customer-managed.

This is a short-lived grant. KMS requires `Resource: "*"` for `CreateKey`, and the creator can supply the initial key policy; IAM cannot constrain it to one key. Creation tagging uses a key ARN wildcard and three required request tags. The secret grant covers only `contact-form/app-*`, but that prefix can match more than one secret and `CreateSecret` can include an initial value even though this Terraform resource declares metadata only. Tags are not proof of Terraform ownership. Review the exact saved plan, keep the attachment window brief, and remove the grant after this target even if apply stops partway through. The new KMS and secret policies must never overlap this grant.

From the repository root, use the existing deployer CLI identity. `terraform -chdir` resolves a relative `-out` under `terraform/workload`, so use an absolute path in Git-ignored `.local/`. The reported live target plan already has exactly two creates; inspect any existing saved copy's mode, current state and inputs before using it. For every newly saved plan, set `umask 077` first:

```bash
umask 077
mkdir -p .local
chmod 700 .local
WORKLOAD_VARS="${WORKLOAD_VARS:-$PWD/.local/verified-workload.tfvars.json}"
BOOTSTRAP_PLAN="$PWD/.local/workload-bootstrap.tfplan"
test -f "$WORKLOAD_VARS" || { printf 'Verified workload variables are missing; stop.\n' >&2; exit 1; }
git check-ignore -q "$BOOTSTRAP_PLAN" || { printf 'Saved plan path is not ignored; stop.\n' >&2; exit 1; }
export AWS_PROFILE=contact-form-deployer AWS_REGION=ap-southeast-1 AWS_DEFAULT_REGION=ap-southeast-1
CALLER_ARN="$(aws sts get-caller-identity --query Arn --output text)" || exit 1
[[ "$CALLER_ARN" == arn:aws:iam::203888389134:user/contact-form-deployer ]] || { printf 'Wrong AWS identity; stop.\n' >&2; exit 1; }
printf '%s in %s\n' "$CALLER_ARN" "$AWS_REGION"
rm -f -- "$BOOTSTRAP_PLAN" || exit 1
terraform -chdir=terraform/workload init -input=false &&
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" \
  -target=aws_kms_key.eks -target=aws_secretsmanager_secret.app \
  -out="$BOOTSTRAP_PLAN" &&
chmod 600 "$BOOTSTRAP_PLAN" &&
[[ "$(stat -c %a "$BOOTSTRAP_PLAN")" == 600 ]] &&
terraform -chdir=terraform/workload show -no-color "$BOOTSTRAP_PLAN"
```

Inspect `terraform -chdir=terraform/workload show -json "$BOOTSTRAP_PLAN"`: the only managed resource changes must be `aws_kms_key.eks` and `aws_secretsmanager_secret.app`, each with `actions: ["create"]`. Check the key's effective three provider tags and rotation, and the empty secret metadata and generated name prefix. Any extra create, update, destroy or replacement stops the target. A plan proves proposed changes, not effective IAM permissions. AWS lists the customer-managed key at [US$1/month prorated hourly](https://aws.amazon.com/kms/pricing/) and the secret at [US$0.40/month prorated hourly](https://aws.amazon.com/secrets-manager/pricing/), plus applicable API charges; key storage is not charged while scheduled for deletion. Confirm current Singapore pricing, credits and the target's duration, then obtain **separate explicit approval for this costed apply**. No approval is inferred from the plan or temporary attachment.

Only after that approval, in the same verified identity and Region, apply the exact reviewed saved plan:

```bash
BOOTSTRAP_PLAN="${BOOTSTRAP_PLAN:-$PWD/.local/workload-bootstrap.tfplan}"
[[ "$(stat -c %a "$BOOTSTRAP_PLAN")" == 600 ]] || { printf 'Saved plan mode is not 600; stop.\n' >&2; exit 1; }
aws sts get-caller-identity
terraform -chdir=terraform/workload apply "$BOOTSTRAP_PLAN"
```

Immediately after the target finishes, including after a partial failure, the administrator **detaches** `ContactFormWorkloadBootstrapTemporary` from the deployer, deletes the temporary customer-managed policy in the IAM Console, and confirms both removal and a free attachment slot. If apply failed, reconcile state and any created resources before requesting another brief grant and a fresh plan; do not proceed to the cluster target. After a successful target, read the two full `arn` values from state, including the secret's generated six-character suffix. In administrator-reviewed policy copies, replace **every** `arn:aws:kms:ap-southeast-1:203888389134:key/00000000-0000-0000-0000-000000000000` in the [KMS draft](../policies/workload/deployer-workload-service-draft-kms.json) and the [EKS draft](../policies/workload/deployer-workload-service-draft-eks.json) `CreateCluster` condition with the key ARN. Replace **every** `arn:aws:secretsmanager:ap-southeast-1:203888389134:secret:contact-form/app-BOOTSTRAP-PLACEHOLDER-000000` in the [secret/ECR draft](../policies/workload/deployer-workload-service-draft-secret-ecr.json) with the exact app-secret ARN. Keep the review copies in ignored mode-600 `.local/` files and publish from those copies only; leave the tracked drafts inert. Verify account, Region, resource type, Terraform address, ownership tags and key-policy IAM delegation; reject any remaining placeholder or wildcard key-management grant. In the Console, the IAM administrator validates, simulates allowed and denied cases, versions and attaches those exact KMS/EKS/secret policies plus the reviewed IAM and other stage grants. The [tracked IAM template](../policies/workload/deployer-iam-provisioning-draft.json) still has **all four** OIDC `Resource` values at inert `id/BOOTSTRAP-PLACEHOLDER`; do not bind an issuer yet.

Next, switch to the deployer and make a **separate** saved cluster target plan with the same `WORKLOAD_VARS`:

```bash
export AWS_PROFILE=contact-form-deployer AWS_REGION=ap-southeast-1 AWS_DEFAULT_REGION=ap-southeast-1
aws sts get-caller-identity --profile "$AWS_PROFILE"
umask 077
mkdir -p .local
chmod 700 .local
CLUSTER_PLAN="$PWD/.local/workload-cluster.tfplan"
rm -f -- "$CLUSTER_PLAN" || exit 1
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" \
  -target=aws_eks_cluster.main -out="$CLUSTER_PLAN" &&
chmod 600 "$CLUSTER_PLAN" &&
[[ "$(stat -c %a "$CLUSTER_PLAN")" == 600 ]] &&
terraform -chdir=terraform/workload show -no-color "$CLUSTER_PLAN"
```

After checking every dependency, current cost and separate explicit approval for the cluster target:

```bash
CLUSTER_PLAN="${CLUSTER_PLAN:-$PWD/.local/workload-cluster.tfplan}"
terraform -chdir=terraform/workload apply "$CLUSTER_PLAN"
terraform -chdir=terraform/workload state show aws_eks_cluster.main
CLUSTER_NAME="$(terraform -chdir=terraform/workload output -raw cluster_name)"
OIDC_ISSUER="$(aws eks describe-cluster --region "$AWS_REGION" --name "$CLUSTER_NAME" --query 'cluster.identity.oidc.issuer' --output text)"
[[ "$OIDC_ISSUER" =~ ^https://oidc\.eks\.ap-southeast-1\.amazonaws\.com/id/[[:alnum:]]+$ ]] || { printf 'Unexpected issuer; stop.\n' >&2; exit 1; }
OIDC_PROVIDER_ARN="arn:aws:iam::203888389134:oidc-provider/${OIDC_ISSUER#https://}"
printf '%s\n' "$OIDC_PROVIDER_ARN"
```

The cluster target can create VPC, subnets, routes, NAT gateways and roles; it starts paid EKS time and must **not** contain the OIDC provider. Inspect the exact dependency set, update the Singapore estimate and credits, and obtain separate explicit approval **before** its apply. Compare the state cluster name, account, Region and read-only EKS issuer; stop on any failed read or mismatch. Never guess an issuer or use `id/*`.

An administrator now creates `.local/deployer-iam-provisioning.json` from the **inert tracked template**, leaving that template unchanged. Re-read the issuer in the same session and reject an old or mixed issuer. The copy must be Git-ignored, mode 600, and contain the new exact provider ARN in precisely `ReadClusterOidcProviders`, `CreateTaggedClusterOidcProvider`, `TagNewClusterOidcProviderAtCreate`, and `ManageTaggedClusterOidcProvider`:

```bash
: "${CLUSTER_NAME:?Read the current cluster name from workload state}"
: "${OIDC_ISSUER:?Read the current issuer from EKS}"
: "${OIDC_PROVIDER_ARN:?Construct the exact provider ARN}"
CURRENT_ISSUER="$(aws eks describe-cluster --region "$AWS_REGION" --name "$CLUSTER_NAME" --query 'cluster.identity.oidc.issuer' --output text)" || exit 1
[[ "$CURRENT_ISSUER" == "$OIDC_ISSUER" ]] || { printf 'Issuer changed; stop.\n' >&2; exit 1; }
[[ "$OIDC_PROVIDER_ARN" == "arn:aws:iam::203888389134:oidc-provider/${CURRENT_ISSUER#https://}" ]] || exit 1
umask 077
mkdir -p .local
chmod 700 .local
OIDC_POLICY=.local/deployer-iam-provisioning.json
git check-ignore -q "$OIDC_POLICY" || { printf 'Review copy is not ignored; stop.\n' >&2; exit 1; }
[[ ! -L "$OIDC_POLICY" ]] || { printf 'Review copy is a symlink; stop.\n' >&2; exit 1; }
python3 - "$OIDC_PROVIDER_ARN" <<'PY'
import json, os, pathlib, re, sys, tempfile
source = pathlib.Path('terraform/policies/workload/deployer-iam-provisioning-draft.json')
target = pathlib.Path('.local/deployer-iam-provisioning.json')
new_arn = sys.argv[1]
if not re.fullmatch(r'arn:aws:iam::203888389134:oidc-provider/oidc\.eks\.ap-southeast-1\.amazonaws\.com/id/[A-Za-z0-9]+', new_arn):
    raise SystemExit('Invalid new OIDC provider ARN; stop')
document = json.loads(source.read_text())
sids = {'ReadClusterOidcProviders', 'CreateTaggedClusterOidcProvider', 'TagNewClusterOidcProviderAtCreate', 'ManageTaggedClusterOidcProvider'}
statements = [s for s in document['Statement'] if s.get('Sid') in sids]
if len(statements) != 4 or {s['Sid'] for s in statements} != sids:
    raise SystemExit('Expected exactly four OIDC statements; stop')
if any('oidc-provider/' in json.dumps(s) for s in document['Statement'] if s.get('Sid') not in sids):
    raise SystemExit('Unexpected OIDC statement; stop')
placeholder = 'arn:aws:iam::203888389134:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/BOOTSTRAP-PLACEHOLDER'
if {s['Resource'] for s in statements} != {placeholder}:
    raise SystemExit('Mixed, wildcard or old issuer in template; stop')
for statement in statements:
    statement['Resource'] = new_arn
rendered = json.dumps(document, indent=2) + '\n'
if rendered.count('oidc-provider/') != 4 or placeholder in rendered or 'id/*' in rendered:
    raise SystemExit('Mixed or stale issuer in review copy; stop')
if sum(not c.isspace() for c in rendered) >= 6144:
    raise SystemExit('Managed policy exceeds 6,144 nonwhitespace characters; stop')
with tempfile.NamedTemporaryFile(mode='w', dir=target.parent, prefix='.oidc-review-', delete=False) as handle:
    os.chmod(handle.name, 0o600)
    handle.write(rendered)
    temporary = handle.name
os.replace(temporary, target)
PY
[[ "$(stat -c %a "$OIDC_POLICY")" == 600 ]] || { printf 'Review copy mode is not 600; stop.\n' >&2; exit 1; }
python3 -m json.tool "$OIDC_POLICY" >/dev/null
```

The deployer has no administrator CLI profile, and `access-analyzer:ValidatePolicy` is denied to it. An account administrator uses the **IAM Console** to publish the local review copy:

1. Open `.local/deployer-iam-provisioning.json` on the workstation and copy its complete JSON. In IAM → Policies, open the project IAM provisioning policy. Review its current version and create a new policy version from this copy; if the policy does not exist, create it from this copy. Never publish the tracked placeholder template or an older review copy.
2. Use the IAM Console policy editor validation and IAM Policy Simulator. Test allowed and denied OIDC Create plus dependent initial Tag with the three required request tags and only the `Project`, `ManagedBy`, `Lifecycle` keys. Test missing/wrong/extra tags, another issuer, and later Manage with matching and absent existing ownership tags. Check any permissions boundary and service controls.
3. Set the approved new version as default. Reopen that published version and verify that precisely four OIDC statements contain the live provider ARN. Check the managed policy attachment slot, attach this policy to `contact-form-deployer` for the approved window if needed, and verify it appears on that user. Stop if validation, simulation, version publication or attachment fails.

The IAM policy change is one-time account access setup for this workload run; Terraform still creates the workload IAM roles, OIDC provider and infrastructure. Do not use a stale issuer from another cluster build.

The deployer does not create policy versions. Keep the role-write attachment brief as described in [IAM and service policy windows](../README.md#iam-and-service-policy-windows). A failed validation, simulation, publication or attachment stops the full plan. An old or mixed issuer stops a rebuild.

Only after both targets and policy binding, switch to the deployer and make a **fresh full** plan from the post-cluster state. The key, app-secret metadata and cluster must already be in workload state and must not be planned for replacement. Review its exact remaining workers, relay, IRSA, ECR, RDS and OIDC provider, update cost/credits, then apply only its approved saved plan. From the repository root:

```bash
export AWS_PROFILE=contact-form-deployer AWS_REGION=ap-southeast-1 AWS_DEFAULT_REGION=ap-southeast-1
aws sts get-caller-identity --profile "$AWS_PROFILE"
WORKLOAD_VARS="${WORKLOAD_VARS:-$PWD/.local/verified-workload.tfvars.json}"
umask 077
mkdir -p .local
chmod 700 .local
FULL_PLAN="$PWD/.local/workload.tfplan"
# Precondition: both approved targets, exact KMS/secret/OIDC rebinding, and policy attachment are complete.
rm -f -- "$FULL_PLAN" || exit 1
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" -out="$FULL_PLAN" &&
chmod 600 "$FULL_PLAN" &&
[[ "$(stat -c %a "$FULL_PLAN")" == 600 ]] &&
terraform -chdir=terraform/workload show -no-color "$FULL_PLAN"
```

After reviewing this fresh full plan, current cost/credits and explicit approval:

```bash
FULL_PLAN="${FULL_PLAN:-$PWD/.local/workload.tfplan}"
terraform -chdir=terraform/workload apply "$FULL_PLAN"
```

The reviewed saved plan embeds these inputs. For teardown, after Ansible cleanup, set `umask 077`, save `plan -destroy -input=false -var-file="$WORKLOAD_VARS" -out="$PWD/.local/workload-destroy.tfplan"`, verify mode 600, review it with `show`, and apply that exact saved plan only after its own cost and approval gate.

## Lifecycle

The foundation owns `/aws/eks/contact-form-eks/cluster` and the fixed-name RDS `postgresql` and `upgrade` log groups with seven-day retention, so their logs survive runtime teardown. Workload planning requires the foundation's `rds_log_group_names` output to match both expected names. Check both actual states for prior RDS log-group ownership and complete any deliberate state handoff before applying; see [backend initialization](../README.md#backend-initialization). The setup Job and Flask use distinct IRSA roles. The app can read only the application secret; the setup Job can read the RDS master secret and read/write the app secret.

Before `terraform destroy`, follow the [Ansible cleanup sequence](../../ansible/README.md#cleanup-before-terraform-destroy): remove the application DNS alias and Ingress, then wait until the controller has deleted the ALB and target groups. Destroying this root deliberately deletes RDS and all submissions, the worker instances, NAT gateways, ECR images, and runtime secrets; KMS key deletion is scheduled. Keep the foundation and state bucket. Use the [scoped residual inventory](../../scripts/README.md#residual-inventory-and-retained-costs) and inspect any orphaned ALB, NAT, EIP, RDS, EBS or backup resources. For a fresh rebuild, rerun preflight, both separately approved targets, exact KMS/secret rebinding and a new four-statement OIDC review copy for the new issuer before generating the full plan; never reuse an old policy version or plan.

For local checks with the provider already installed (no AWS access or state migration):

```bash
terraform -chdir=terraform/workload fmt -check
terraform -chdir=terraform/workload validate -no-color
```

A successful validate checks Terraform syntax and provider schema. It does not verify IAM permissions, pricing, quotas, Singapore engine versions, or live deployment.
