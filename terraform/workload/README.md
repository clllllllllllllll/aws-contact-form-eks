# Disposable workload

This Terraform root has been partially applied in AWS. On 27 September 2026 in `ap-southeast-1`, the first target created `aws_kms_key.eks` and `aws_secretsmanager_secret.app` metadata. Live AWS checks confirmed the symmetric customer-managed KMS key is `Enabled`, has rotation enabled and `Project`/`ManagedBy`/`Lifecycle` tags, and uses the default `Allow` key-policy statement for principal `arn:aws:iam::203888389134:root` on `kms:*` (account-root IAM delegation). The app secret exists with the `contact-form/app-` prefix and those tags; no secret-version resource was in the applied plan. Foundation stages and the `cheelong.xyz` certificate were applied earlier. The separately approved cluster target also applied after a partial permission failure and fresh retry. Direct AWS reads confirmed `contact-form-eks` `ACTIVE` at 1.36 with a private-only API, five control-plane log types enabled and Secrets encryption, and two NAT gateways `available`, one per AZ. No worker, RDS, ALB or AWS application has been deployed. EKS, NAT and their public IPv4 addresses are accruing charges now. Review current Singapore costs, credits and permissions before each further paid apply; approval of the cluster target does not approve the full workload.

`backend.tf` declares the encrypted S3 state key `workload/terraform.tfstate` with S3 lockfiles and an account restriction. The backend was initialized for the first target. Before future initialization or apply, inspect local and S3 state as described in [Terraform roots](../README.md#backend-initialization). The earlier `init -backend=false` was for syntax checks only; do not treat its provider cache as initialized remote state.

The intended runtime contains a VPC across two AZs, two public ALB/NAT subnets, two private worker subnets, two isolated RDS subnets, one EKS managed worker per AZ, a private-only EKS API, a private SSM relay, Multi-AZ PostgreSQL, ECR, and application-secret metadata. RDS manages the master secret. A later Kubernetes setup Job initializes the database and writes the restricted application secret. No database password is a Terraform input or output.

## Controller and Ingress contract

The controller role has an inline IAM policy using exact account and region ARNs plus the cluster and Ingress stack ownership tags for writes. The inline form fits IAM's 10,240-character aggregate role limit; the rendered size must be checked before deployment. It omits security-group mutations and unused capacity reservation, WAF, Shield, and Cognito permissions. The pinned controller v2.14.1 sends listener and rule tags in its create calls; create-time `AddTags` is scoped to the matching creation actions. Ansible must install chart `1.14.0` with `image.tag=v2.14.1` and `enableBackendSecurityGroup=false` and `enableManageBackendSecurityGroupRules=false`. The Ingress must:

- use `alb.ingress.kubernetes.io/security-groups` with Terraform's `alb_security_group_id` output;
- set `alb.ingress.kubernetes.io/manage-backend-security-group-rules: "false"`;
- use `alb.ingress.kubernetes.io/target-type: ip`, port 8000 and `/health/ready`;
- use the two `public_subnet_ids`, the foundation's ACM certificate, and no WAF/Shield annotations.

Terraform provides the ALB security group, worker security-group rules and the controller IAM role/policy. Ansible applies the Ingress; the controller creates and owns the **single physical ALB**, listeners and target groups. Terraform declares no ALB resource. The controller will not create or modify security groups under this contract. Review the rendered policy and live reconciliation before deployment; the scoped draft has not been simulated or attached. See [preflight](#read-only-preflight) and [service policy scope](#service-policy-scope).

## Service policy scope

The six durable workload service policy drafts and the [temporary first-creation draft](../policies/workload/deployer-workload-bootstrap-temporary-draft.json) are separate from the [IAM and attachment windows](../README.md#iam-and-service-policy-windows). The temporary managed policy was attached for the successful first target; the user confirmed its detach from `contact-form-deployer` and deletion on 27 September 2026, without an independent deployer CLI attachment-list check. Exact-ARN KMS, EKS and secret/ECR review copies under ignored `.local/` were prepared. The user reported all three attached; direct KMS and application-secret `DescribeSecret` metadata reads succeeded. The cluster target used a staged EC2 network grant; its missing `ec2:DescribeAddressesAttribute` read was added and directly verified before the retry. IAM simulation and a current attachment-slot review still require administrator attention. Their scope is:

| Draft | Planned resource scope |
| --- | --- |
| [Temporary bootstrap](../policies/workload/deployer-workload-bootstrap-temporary-draft.json) | Short customer-managed policy attachment used for tagged symmetric key and `contact-form/app-*` secret creation, creation tags, and post-create read/rotation; detached from `contact-form-deployer` and deleted on 27 September 2026 (user-confirmed) |
| [EC2 network](../policies/workload/deployer-workload-service-draft-ec2-network.json) | VPC, six subnets, NAT/EIPs, routes and regional refresh reads |
| [EC2 compute](../policies/workload/deployer-workload-service-draft-ec2-compute.json) | Project security groups/rules, relay, worker launch template and root-volume tags |
| [EKS](../policies/workload/deployer-workload-service-draft-eks.json) | Private cluster, deployer access, three add-ons and two node groups; first cluster creation requires the exact key ARN |
| [KMS](../policies/workload/deployer-workload-service-draft-kms.json) | Post-bootstrap management of the one exact workload key, including `CreateGrant` for EKS and seven-day deletion scheduling; no `CreateKey`. `CreateGrant` permits grantee choice; keep it only for cluster creation and remove it from the policy version afterward |
| [RDS](../policies/workload/deployer-workload-service-draft-rds.json) | Named private Multi-AZ database and subnet group, with RDS-managed master secret |
| [Secrets Manager/ECR](../policies/workload/deployer-workload-service-draft-secret-ecr.json) | Post-bootstrap exact application-secret read/metadata management and named ECR repository; no application-secret creation. The user confirmed `ContactFormWorkloadSecretECR` attached; direct `DescribeSecret` metadata read succeeded. Review the published version and simulate value-write actions before full apply |

The RDS policy restricts requested create storage to 20 GiB and requested modify storage to at most 40 GiB with class `db.t4g.small`. IAM has no condition for `MaxAllocatedStorage`: Terraform sets its autoscaling ceiling to 40 GiB, but IAM does **not** enforce a hard 40-GiB ceiling. Review both storage values in the exact saved plan and keep the RDS write grant attached only for a time-limited apply or destroy window; monitor actual storage and charges.

The provider tags owned resources `Project=aws-contact-form-eks`, `ManagedBy=Terraform`, and `Lifecycle=workload`. Generated IDs, tag-on-create behavior, EKS-managed security-group context, KMS grants, RDS dependencies, service-linked roles, boundaries and quotas still need live validation for the remaining resources. An access denial requires review of the exact call, not a blanket service grant. With the recorded state-access policy inline, the six durable workload policies plus two IAM drafts would use 9 of the default 10 managed user-policy slots if one other managed policy is attached directly. The temporary bootstrap grant occupied one managed attachment slot during its window; its removal was user-confirmed on 27 September. `iam:ListAttachedUserPolicies` is denied on the deployer, so an IAM administrator must check actual attachments and available slots in the Console, detach completed foundation-stage or other obsolete grants, and recheck slots before later exact-ARN grants.

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

The trimmed [preflight read policy](../policies/workstation/preflight-read-policy.json) is attached to the deployer and grants no provisioning permission. A CLI read verified the effective Singapore Standard On-Demand quota is **8 vCPUs**. The full preflight returned `READY` before the first target; recheck it before later provisioning if inputs or availability have changed. The EKS cluster and two NAT gateways are now live; no worker, relay or RDS instance has been created. Every required AWS read must succeed: account/Region, two available standard AZs, applied Standard EC2 vCPU quota `L-1216C47A`, current Standard instance occupancy, EKS support and add-on compatibility, Multi-AZ PostgreSQL 16 `db.t4g.small` orderability, and available Amazon-owned AL2023 AMIs. A fresh stack needs **6 free vCPUs** for two `t3.medium` workers and one `t3.micro` relay; simultaneous managed-node updates can reach **14 vCPUs**. Use `--require-update-headroom` when that update capacity must be available now. This is a fresh-stack quota check, not a repeat readiness test on a running stack or an instance-capacity guarantee.

For a first pin, preflight checks the current Singapore recommended node release and writes its SSM parameter version and AMI ID. For a frozen older release, supply **both** evidence fields from an earlier verified file; the script reads that exact parameter version and reports recommendation drift. `READY` (exit 0) atomically writes ignored mode-600 `.local/verified-workload.tfvars.json`; `BLOCKED` (2) means a prerequisite failed and `INCOMPLETE` (1) means a read, credential or response failed. A failed run preserves an existing verified file, and a different successful pin cannot overwrite it: choose a new `--verified-file` path and set `WORKLOAD_VARS` to that path. Copy the verified file securely to the rehearsal workstation, recheck it there as a separate candidate, and retain it through destroy. Expired credentials are `INCOMPLETE`, never readiness.

## Two target first creation and OIDC binding

Complete foundation and certificate staging, [backend/state reconciliation](../README.md#backend-initialization), read-only preflight, actual permission review, a current Singapore cost/credit check, and a separately approved saved plan **for each paid apply**. Keep one less-than-ten-hour total paid-runtime clock. If either target is already in workload state, stop and reconcile instead of recreating it. Use the **same** frozen verified file and reconciled workload S3 backend for both targets and the later full plan.

**Current run:** Both targets were separately approved and applied on 27 September. The first target's temporary policy removal was user-confirmed. The cluster target's original 20-create plan partly failed because `ec2:DescribeAddressesAttribute` was denied after the VPC, subnets, internet gateway, public routing, two tagged EIPs and role had been created. The live EIPs were verified with project tags and safely untainted after the missing read action was added and tested. A fresh retry plan with seven creates, zero changes and zero destroys completed, yielding a private EKS cluster and two available NAT gateways. The first-target and cluster-target commands below are retained for a fresh build or rebuild; do not reapply their 27 September plans against current state.

For the first target, the root/account administrator uses the **IAM Console** (no separate administrator CLI profile) to review the [temporary bootstrap policy](../policies/workload/deployer-workload-bootstrap-temporary-draft.json). This is account-prerequisite IAM setup; Terraform manages the workload resources, not this policy. The deployer cannot call `iam:ListAttachedUserPolicies` or `access-analyzer:ValidatePolicy`, so check its actual policies, groups, boundary and attachment slots in the Console. Use the IAM Console policy editor's validation under the administrator login and simulate allowed and denied create, tag, read and rotation actions with correct/wrong tags, secret names and Regions. For a fresh bootstrap attachment, validate and simulate this draft in the IAM Console; the successful 27 September apply alone does not establish its full IAM scope.

For a fresh build or rebuild, in **IAM → Policies → Create policy → JSON**, paste the reviewed draft and create customer-managed `ContactFormWorkloadBootstrapTemporary`. In **IAM → Users → contact-form-deployer → Permissions**, detach `ContactFormFoundationStage01` if its completed window is over, confirm a managed attachment slot is free, then attach the temporary policy and verify its exact ARN on the user. Do not alter the existing state-access or preflight inline policies. If the slot, validation, simulation or attachment check fails, stop. The [IAM user inline aggregate limit](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html) is why this temporary grant is customer-managed.

This is a short-lived grant. KMS requires `Resource: "*"` for `CreateKey`, and the creator can supply the initial key policy; IAM cannot constrain it to one key. Creation tagging uses a key ARN wildcard and three required request tags. The secret grant covers only `contact-form/app-*`, but that prefix can match more than one secret and `CreateSecret` can include an initial value even though this Terraform resource declares metadata only. Tags are not proof of Terraform ownership. Review the exact saved plan, keep the attachment window brief, and remove the grant after this target even if apply stops partway through. The new KMS and secret policies must never overlap this grant.

From the repository root, use the existing deployer CLI identity. `terraform -chdir` resolves a relative `-out` under `terraform/workload`, so use an absolute path in Git-ignored `.local/`. For a fresh build or rebuild, inspect any existing saved copy's mode, current state and inputs before using it; never reuse the 27 September applied plan. For every newly saved plan, set `umask 077` first:

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

**Current run:** The user confirmed on 27 September that `ContactFormWorkloadBootstrapTemporary` was detached from `contact-form-deployer` and deleted. The three exact-ARN review copies are prepared under ignored `.local/`; the user reported KMS, EKS and `ContactFormWorkloadSecretECR` policies attached. Direct KMS and application-secret `DescribeSecret` metadata reads succeeded. The tracked secret/ECR draft and exact-ARN review copy both exclude `secretsmanager:UpdateSecret`, and static parity review passed. The user confirmed the default `ContactFormIAMProvisioning` JSON contains the live issuer in all four OIDC statements and is attached to `contact-form-deployer`; a direct exact-ARN `GetOpenIDConnectProvider` returned `NoSuchEntity`, confirming authorized read while the provider remains uncreated. The current `ContactFormIAMRoleWrites` attachment status, IAM simulations and remaining service grants still require review before the full apply.

For a fresh build or rebuild only, switch to the deployer and make a **separate** saved cluster target plan with the same `WORKLOAD_VARS`. The current cluster is already in state; do not run this block for the current deployment:

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

For that fresh build or rebuild, after checking every dependency, current cost and separate explicit approval for the cluster target:

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

For a fresh build or rebuild, the cluster target can create VPC, subnets, routes, NAT gateways and roles; it starts paid EKS time and must **not** contain the OIDC provider. Inspect the exact dependency set, update the Singapore estimate and credits, and obtain separate explicit approval **before** its apply. In the current run, direct AWS reads confirmed the cluster is `ACTIVE` at 1.36, its API is private-only, five control-plane log types and Secrets encryption are enabled, and both NAT gateways are `available`. Compare the state cluster name, account, Region and read-only EKS issuer; stop on any failed read or mismatch. Never guess an issuer or use `id/*`.

For a fresh build or rebuild, an administrator creates `.local/deployer-iam-provisioning.json` from the **inert tracked template**, leaving that template unchanged. Re-read the issuer in the same session and reject an old or mixed issuer. The copy must be Git-ignored, mode 600, and contain the new exact provider ARN in precisely `ReadClusterOidcProviders`, `CreateTaggedClusterOidcProvider`, `TagNewClusterOidcProviderAtCreate`, and `ManageTaggedClusterOidcProvider`:

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

**Current run:** The ignored mode-600 `.local/deployer-iam-provisioning.json` copy was prepared with the issuer ending `CA1A506A94A42855899E0176A0F40FE7` in all four required OIDC statements. The user confirmed that the default `ContactFormIAMProvisioning` JSON now has those four live-issuer statements and is attached to the deployer. A direct exact-ARN `GetOpenIDConnectProvider` call returned `NoSuchEntity`: the read was authorized, but Terraform has not created the provider. This read does not verify OIDC create/tag permissions, and IAM simulation remains unverified. The tracked template remains inert. Regenerate the copy from the live issuer on rebuild.

The deployer has no administrator CLI profile, and `access-analyzer:ValidatePolicy` is denied to it. For a fresh build or policy update, an account administrator uses the **IAM Console** to publish or verify the local review copy; the current default version and attachment were user-confirmed:

1. Open `.local/deployer-iam-provisioning.json` on the workstation and copy its complete JSON. In IAM → Policies, open the project IAM provisioning policy. Review its current version and create a new policy version from this copy; if the policy does not exist, create it from this copy. Never publish the tracked placeholder template or an older review copy.
2. Use the IAM Console policy editor validation and IAM Policy Simulator. Test allowed and denied OIDC Create plus dependent initial Tag with the three required request tags and only the `Project`, `ManagedBy`, `Lifecycle` keys. Test missing/wrong/extra tags, another issuer, and later Manage with matching and absent existing ownership tags. Check any permissions boundary and service controls.
3. Set the approved new version as default. Reopen that published version and verify that precisely four OIDC statements contain the live provider ARN. Check the managed policy attachment slot, attach this policy to `contact-form-deployer` for the approved window if needed, and verify it appears on that user. Stop if validation, simulation, version publication or attachment fails.

The IAM policy change is one-time account access setup for this workload run; Terraform still creates the workload IAM roles, OIDC provider and infrastructure. Do not use a stale issuer from another cluster build.

The deployer does not create policy versions. Keep the role-write attachment brief as described in [IAM and service policy windows](../README.md#iam-and-service-policy-windows). A failed validation, simulation, publication or attachment stops the full plan. An old or mixed issuer stops a rebuild.

Only after both targets and policy binding, switch to the deployer and make a **fresh full** plan from the post-cluster state. The key, app-secret metadata and cluster must already be in workload state and must not be planned for replacement. In the current run, a refreshed full plan succeeded with **50 additions, zero changes and zero destroys**. It has **not** been applied or cost-approved; no workers, RDS, ALB or AWS application are live. Review the exact remaining workers, relay, IRSA, ECR, RDS and OIDC provider, finish IAM simulation, update cost/credits, then apply only an explicitly approved saved plan. From the repository root:

```bash
export AWS_PROFILE=contact-form-deployer AWS_REGION=ap-southeast-1 AWS_DEFAULT_REGION=ap-southeast-1
aws sts get-caller-identity --profile "$AWS_PROFILE"
WORKLOAD_VARS="${WORKLOAD_VARS:-$PWD/.local/verified-workload.tfvars.json}"
umask 077
mkdir -p .local
chmod 700 .local
FULL_PLAN="$PWD/.local/workload.tfplan"
# Precondition: both approved targets are in state; review current exact-ARN grants and IAM simulations before apply.
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

The reviewed saved plan embeds these inputs. For a fully deployed stack, after Ansible cleanup, set `umask 077`, save `plan -destroy -input=false -var-file="$WORKLOAD_VARS" -out="$PWD/.local/workload-destroy.tfplan"`, verify mode 600, review it with `show`, and apply that exact saved plan only after its own cost and approval gate. For the current partial deployment, use the verification gate below first.

## Lifecycle

The foundation owns `/aws/eks/contact-form-eks/cluster` and the fixed-name RDS `postgresql` and `upgrade` log groups with seven-day retention, so their logs survive runtime teardown. Workload planning requires the foundation's `rds_log_group_names` output to match both expected names. Check both actual states for prior RDS log-group ownership and complete any deliberate state handoff before applying; see [backend initialization](../README.md#backend-initialization). The setup Job and Flask use distinct IRSA roles. The app can read only the application secret; the setup Job can read the RDS master secret and read/write the app secret.

For a fully deployed stack, follow the [Ansible cleanup sequence](../../ansible/README.md#cleanup-before-terraform-destroy) before workload destroy: remove the application DNS alias and Ingress, then wait until the controller has deleted the ALB and target groups. Destroying this root deliberately deletes RDS and all submissions, the worker instances, NAT gateways, ECR images, and runtime secrets; KMS key deletion is scheduled. Keep the foundation and state bucket. Use the [scoped residual inventory](../../scripts/README.md#residual-inventory-and-retained-costs) and inspect any orphaned ALB, NAT, EIP, RDS, EBS or backup resources. For a fresh rebuild, rerun preflight, both separately approved targets, exact KMS/secret rebinding and a new four-statement OIDC review copy for the new issuer before generating the full plan; never reuse an old policy version or plan.

### Partial deployment teardown (current cluster-only state)

Use this path only if the full workload plan and Ansible deployment were never applied. From the repository root, confirm the AWS account/Region and inspect `terraform -chdir=terraform/workload state list`; it should show only the first and cluster target resources. State alone cannot prove that an out-of-band application or ALB is absent. Independently inspect the project cluster/VPC with scoped AWS reads or the Console: EKS node groups and Kubernetes namespace, Deployment, Service and Ingress resources; EC2 relay instances; ELBv2 load balancers and target groups; RDS instances; and the application Route 53 alias. Confirm no Ingress, ALB, app or RDS exists. If any read is denied or unavailable, or any unexpected resource exists, **stop** and investigate or use the normal Ansible cleanup; do not infer absence from a failed read. Skip inapplicable Ansible cleanup only after the absence checks succeed.

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

Only after reviewing and approving that exact plan, in the same shell run:

```bash
[[ "$(stat -c %a "$DESTROY_PLAN")" == 600 ]] &&
terraform -chdir=terraform/workload apply "$DESTROY_PLAN"
```

After apply, run `python3 scripts/check_residual.py --profile contact-form-deployer` and inspect the project VPC, NAT gateways/EIPs, EKS cluster, secret and KMS key status (including any scheduled key deletion). If a residual read is denied, cleanup is unverified; resolve access or check in the Console. Review [retained foundation costs](../../scripts/README.md#residual-inventory-and-retained-costs) separately; a clean workload result does not mean a zero bill.

For local checks with the provider already installed (no AWS access or state migration):

```bash
terraform -chdir=terraform/workload fmt -check
terraform -chdir=terraform/workload validate -no-color
```

A successful validate checks Terraform syntax and provider schema. It does not verify IAM permissions, pricing, quotas, Singapore engine versions, or live deployment.
