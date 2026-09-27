# Terraform roots

The three roots have different lifecycles:

| Root | Status | Purpose |
| --- | --- | --- |
| `bootstrap/` | Applied and verified in account `203888389134` | Persistent encrypted, versioned S3 bucket for Terraform state and lockfiles |
| `foundation/` | Stages 01–03 applied and verified in account `203888389134` on 27 September 2026 | Resources retained between workload teardown and redeployment |
| `workload/` | Partial deployment destroyed on 28 September 2026; Terraform tracks no managed workload resources | Disposable VPC, EKS, RDS, IAM, ECR, and application secret metadata |

Bootstrap's state is local at `bootstrap/terraform.tfstate` and excluded from Git. Preserve it securely. Manual IAM policy handling is described in the [policy notes](policies/README.md). Foundation and workload both declare S3 backends, with distinct `foundation/terraform.tfstate` and `workload/terraform.tfstate` keys. Foundation stages 01–03 have remote state in the foundation key. After the partial workload teardown, `terraform -chdir=terraform/workload state list` showed only a data source and no managed resources. The versioned S3 state still records historical versions; check the current object and state before using another workstation.

The bootstrap plan reported `No changes` while the temporary bucket-setup policy was attached. That policy was then removed. To refresh or plan `terraform/bootstrap/` again, temporarily restore its setup/read permissions. The [state-access draft](policies/bootstrap/state-access-policy.json) scopes access to foundation and workload S3 state objects and locks; verify the actual grant and backend access before relying on it. Do not reapply or destroy bootstrap without reviewing the plan. Reattach the setup policy temporarily for deliberate bootstrap maintenance. Full state-bucket teardown also requires removing prevent_destroy and granting explicit deletion permissions after foundation and workload are gone.

The read-only [runtime inventory policy draft](policies/workstation/runtime-inventory-policy.json) covers the AWS Describe/List calls used by `scripts/check_residual.py` in Singapore. It was not attached for the final check. That check stopped at denied `ec2:DescribeSnapshots`; RDS automated-backup and Secrets Manager inventory reads were also denied after deletion. Direct project-scoped reads were empty for VPCs, active NAT gateways, EIPs, active EC2 instances, tagged EBS volumes, RDS instances and ALBs, but they do not complete the residual inventory or prove a zero bill.

The [IAM and service policy windows](#iam-and-service-policy-windows) below map Terraform resources to the stage 01 policy used for its completed apply and to later customer managed policy drafts. The later drafts do not establish effective provisioning access.

## Cost and apply gate

The state bucket and foundation stages 01–03 remain applied. The partial workload was destroyed on 28 September; no project EKS cluster, NAT gateway or EIP remains in the direct inventories described above. Its KMS key is `PendingDeletion`, scheduled for 5 October 2026. CLI read the effective Singapore Standard On-Demand quota as 8 vCPUs on 27 September; recheck it before rebuilding. The owner's full deployment and teardown approval covered an estimated **US$0.50–1.00 per hour** and a **US$10–20 planning allowance before credits** for less than ten total hours. These are estimates, not a cap or a bill. Before another paid apply, check the current plan, Singapore prices, credits, quota, remaining runtime and teardown route. The US$10 budget and US$5 actual-cost email alert do not stop spending. DNS, state, evidence, retained logs and account security services can continue to cost money after workload destroy; see [residual inventory and retained costs](../scripts/README.md#residual-inventory-and-retained-costs).

The existing approval covers a rebuild **within the same resource scope and cost range**. Seek renewed explicit approval if a new plan or estimate exceeds either. Review each fresh saved plan and its expected runtime before applying; a new cluster target starts EKS, NAT and public IPv4 charges. Stop on a failed prerequisite read, unexpected plan action or unresolved IAM denial; do not use `-auto-approve`. No workers, Flask pods or ALB have been verified in AWS, and no application end-to-end demo has succeeded.

**Recorded attempt and teardown (27–28 September 2026):** The first target created a KMS key and app-secret metadata. A cluster-target retry created a private EKS API, two NAT gateways and supporting network resources after a missing `ec2:DescribeAddressesAttribute` read was fixed. The approved full plan was **partially applied**: it created a private SSM relay, private Multi-AZ PostgreSQL RDS with an RDS-managed master secret, ECR and a pushed image. The workstation reached EKS `/readyz` through the TLS-verifying SSM tunnel. Both node groups stopped before worker launch because the deployer was denied `iam:GetRole` for the EKS node-group service-linked role. There was no Flask deployment or ALB. The partial workload was then destroyed; no managed workload resources remain in Terraform state. EKS deletion waiters and EIP release required [guarded recovery](workload/README.md#recovery-after-a-partial-destroy). The incomplete residual checker remains an open verification gap.

## IAM and service policy windows

An administrator must inspect the real non-root principal, attached and inline policies, boundaries, service control policies, existing service-linked roles and named project roles. The [IAM resource/pass-role draft](policies/workload/deployer-iam-provisioning-draft.json) covers named roles, the OIDC provider, the relay instance profile and listed first-use service-linked roles. Its four OIDC resource values are inert placeholders in the tracked template. The previously published copy was bound to the **destroyed** cluster's issuer and cannot be reused. The revised tracked draft adds a read-only alternate ARN for the node-group service-linked role; its effectiveness has **not** been verified. Before rebuilding, an administrator must publish a reviewed default version, confirm its attachment, and test `iam:GetRole` for `AWSServiceRoleForAmazonEKSNodegroup` with the deployer CLI profile. A returned role or `NoSuchEntity` distinguishes an authorized read from `AccessDenied`; only then can cluster creation proceed. After a **new** EKS cluster exists, bind all four OIDC statements to its new issuer in an ignored mode-600 copy, publish and verify that default version, and simulate the required create/tag calls. The separate [role-write draft](policies/workload/deployer-iam-role-writes-draft.json) can change trust and write arbitrary inline policy content on four named roles **without a permissions boundary**; it is privilege sensitive. Have a trusted administrator validate it and attach it only for a monitored, time-limited apply/change/destroy window, then detach it. These IAM drafts grant no non-IAM provisioning actions.

| Window | Drafts to review and attach for that window |
| --- | --- |
| Completed foundation stage 01 plan/apply | Customer-managed `ContactFormFoundationStage01`, based on the [stage 01 policy](policies/foundation/deployer-foundation-stage-01.json), was attached for the approved stage |
| Future foundation change | [refresh](policies/foundation/deployer-foundation-service-draft-refresh.json) + [apply](policies/foundation/deployer-foundation-service-draft-apply.json), plus the approved IAM pair where the plan needs IAM |
| Optional foundation teardown | refresh + [destroy](policies/foundation/deployer-foundation-service-draft-destroy.json), replacing apply, plus needed IAM |
| Completed workload first target | Temporary managed `ContactFormWorkloadBootstrapTemporary` was attached for the approved two-create apply; the user confirmed its detach from `contact-form-deployer` and deletion on 27 September 2026 |
| Rebuild targets, full apply and destroy | Review the six [workload service drafts](workload/README.md#service-policy-scope), the IAM pair, actual default versions and attachment slots. Bind fresh exact KMS, secret, OIDC and relay identifiers at the appropriate stages |
| Read-only preflight, runtime inventory, workstation helpers | The trimmed [preflight](policies/workstation/preflight-read-policy.json) policy supported the earlier readiness check; review current attachment. The [runtime inventory](policies/workstation/runtime-inventory-policy.json) and [helper](policies/workstation/deployer-helper-service-draft.json) have separate windows; neither grants Terraform apply access |

The foundation service drafts contain no IAM or state-bucket permissions; [state access](policies/bootstrap/state-access-policy.json) is separate. For the approved 27 September stage 01 apply, customer-managed `ContactFormFoundationStage01` was attached and updated to allow `logs:TagLogGroup` alongside its existing `logs:TagResource` grant after a partial failure. A fresh plan then showed three additions only, and apply succeeded with three added. Confirm whether the temporary policy is still attached and detach it after its completed window. Future foundation changes need separately reviewed **refresh + apply** for plan/apply, or **refresh + destroy** for a partial teardown. Do not keep both write policies attached. Inspect Config, Security Hub and CloudTrail ownership before future changes; preserve unrelated account controls. The three later foundation service drafts now scope hosted-zone access to `arn:aws:route53:::hostedzone/Z0153068M1DZTUZ2CE23`. For future apply/destroy policy versions, narrow `_*.cheelong.xyz` to the exact normalized validation CNAME, especially before teardown. A fresh certificate request and tag-on-create path need their own reviewed, short attachment window. Foundation `prevent_destroy` protects the zone, evidence bucket and retained log groups; the draft destroy policy does not authorize their full removal. Final retirement needs a separate owner decision and plan.

The recorded `ContactFormTerraformStateAccess` user policy is **inline** and consumes no managed attachment slot. The deployer reached the managed-policy attachment quota during the first run, and some direct attachments were rotated. Do not infer the present list from a prior screenshot or Terraform files: check the IAM Console's attached entities and default JSON versions before each window. The old KMS/secret/OIDC and relay identifiers refer to destroyed resources. Rotate foundation, workload, helper and temporary grants as needed, preserving the state-access grant. An administrator checks the 6,144 nonwhitespace-character managed-policy limit and simulates both allowed and denied request tags, resource ARNs, `iam:PassRole`, OIDC create with its dependent initial Tag, service-linked-role reads, and service actions. Successful JSON parsing and Terraform planning do not establish effective AWS permissions. The earlier preflight returned `READY`, but a new build needs another preflight and current policy review.

## Backend initialization

Before another workstation runs `terraform init`, verify the non-root AWS identity and check both local state files and the exact S3 state keys. The workload S3 backend was initialized for the first target; `.terraform/` alone is not proof of current resource state. Run these checks with working AWS credentials; an access error does not mean an S3 key is empty:

```bash
find terraform/foundation terraform/workload -maxdepth 1 -name 'terraform.tfstate*' -print
aws sts get-caller-identity --profile contact-form-deployer
aws s3api list-object-versions --profile contact-form-deployer --region ap-southeast-1 --bucket aws-contact-form-eks-tfstate-203888389134-ap-southeast-1 --prefix foundation/terraform.tfstate
aws s3api list-object-versions --profile contact-form-deployer --region ap-southeast-1 --bucket aws-contact-form-eks-tfstate-203888389134-ap-southeast-1 --prefix workload/terraform.tfstate
```

Inspect the exact state keys, including current versions and delete markers; the prefix also matches lockfiles. The ongoing state-access policy includes `s3:ListBucketVersions`. If local state is absent and the remote check is clear, use ordinary `terraform -chdir=terraform/foundation init` or `terraform -chdir=terraform/workload init`. An existing current S3 state must be reused and checked with `terraform state list` before planning. If local state exists and the corresponding S3 key has no version history, keep a private backup and use `terraform init -migrate-state` for that root, then verify the migrated resources. If both copies exist, the exact key has a delete marker or older version but no current state, or an S3 check fails, stop and reconcile before init. Do not use `-reconfigure` or `-force-copy` to bypass a state conflict. Foundation remote state contains stages 01–03. The workload's **current** state was emptied of managed resources after the 28 September teardown; older S3 object versions record the partial deployment and are not the desired state. Recheck both current states on the workstation used for a rebuild.

The fixed-name RDS `postgresql` and `upgrade` log groups were applied in foundation stage 01. Before either root's next apply, inspect both actual states for `aws_cloudwatch_log_group.rds` addresses. If workload state tracks either group, stop and arrange a deliberate, reviewed cross-root state migration or import with state backups; do not allow a workload plan to destroy it or assume this code move transfers state. Verify foundation state ownership and its `rds_log_group_names` output before planning workload.

## Foundation stages

Each checked-in stage file sets all three feature flags. The flags have no defaults; `plan -input=false` fails if a stage file is omitted instead of prompting for values. Select the next stage only after reviewing the account-wide service inventory, Terraform ownership, DNS delegation, and cost as applicable:

| Stage file under `foundation/stages/` | Use when |
| --- | --- |
| `01-base.tfvars` | Applied 27 September 2026: DNS zone, evidence bucket, and retained EKS and RDS log groups |
| `02-security-existing-trail.tfvars` | Config and Security Hub can be managed here; a suitable management-event trail already exists |
| `02-security-project-trail.tfvars` | Config and Security Hub can be managed here; a new project trail is needed |
| `03-ready-existing-trail.tfvars` | Registrar delegation is verified; continue the existing-trail branch and request the ACM certificate |
| `03-ready-project-trail.tfvars` | Registrar delegation is verified; continue the project-trail branch and request the ACM certificate |

Stage 01 applied 11 resources in account `203888389134`, `ap-southeast-1`: hosted zone `cheelong.xyz` (`Z0153068M1DZTUZ2CE23`), evidence bucket `aws-contact-form-evidence-203888389134-ap-southeast-1` and its six configuration resources, and three seven-day EKS/RDS log groups. Stages 02 and 03 also applied on 27 September: public Route 53 delegation was verified, AWS Config is recording, CloudTrail is logging, Security Hub FSBP is `READY`, and the ACM certificate is `ISSUED`.

For a fresh build, use the same branch of stage 02 and 03. If Config or Security Hub is already configured, resolve ownership or import before selecting a security stage. Never return to an earlier stage file after applying a later one: the earlier flags would propose deleting enabled resources. Use the current stage file for every later foundation plan. The commands below document the stage 01 procedure for a fresh build; in this account, retain the latest applied stage file and trail branch for further changes. From the repository root, after the backend checks and cost approval:

```bash
export AWS_PROFILE=contact-form-deployer
umask 077
terraform -chdir=terraform/foundation init
FOUNDATION_STAGE=stages/01-base.tfvars
terraform -chdir=terraform/foundation plan -input=false -var-file="$FOUNDATION_STAGE" -out=foundation.tfplan
terraform -chdir=terraform/foundation show -no-color foundation.tfplan
terraform -chdir=terraform/foundation apply foundation.tfplan
```

For a fresh build, set `FOUNDATION_STAGE` to each later stage entry and repeat the plan, show, and apply commands. Apply only a newly generated plan after reviewing its resource changes; stop if planning fails. The ignored plan file is local and may contain sensitive deployment details. Workload planning follows a completed certificate stage and its own backend check.

For a fresh build, after stage 01, compare all four `terraform -chdir=terraform/foundation output -json name_servers` values with public `dig NS cheelong.xyz +noall +answer`, allowing only case/trailing-dot differences. Enter the zone's nameservers at Exabytes and wait for public delegation before stage 03; an output alone is not DNS proof. After the selected stage 03, set `CERT_ARN="$(terraform -chdir=terraform/foundation output -raw certificate_arn)"` and use `aws acm describe-certificate --region ap-southeast-1 --certificate-arn "$CERT_ARN"` to confirm `ISSUED` before workload creation. Preserve the latest applied stage file and trail branch for future foundation plans. Record actual Config/FSBP findings in [security evidence](../docs/security.md); an enabled subscription or unevaluated control is not a pass.

## Workload version inputs

Read-only preflight returned `READY` before the **previous** workload attempt; that result is not proof of current quota, versions or capacity. Run the [read-only preflight](workload/README.md#read-only-preflight) again for a rebuild with chosen versions. It writes `.local/verified-workload.tfvars.json` only after every required read succeeds. From the repository root, initialize the workload backend after the backend check and foundation certificate stage. Keep the verified file through destroy and securely copy it for laptop rehearsal.

```bash
terraform -chdir=terraform/workload init
```

The disposable workload currently has **no managed resources in Terraform state**. Follow the [two-target first-creation and OIDC binding procedure](workload/README.md#two-target-first-creation-and-oidc-binding) from the beginning: fresh KMS/app-secret target, then fresh network/EKS cluster target, with new saved plans, reviewed permissions, and cost checks at each step. Before cluster creation, resolve and retest the caller's `iam:GetRole` access for the EKS node-group service-linked role. After the new cluster exists, bind its **new OIDC issuer** in all four statements of the IAM provisioning policy. Before the full apply, review exact current KMS/secret policy ARNs, attachment slots and IAM simulations. The earlier **50-addition plan was approved and partially applied**, then invalidated by teardown; do not reuse it or the old issuer-bound policy. The existing deployment and teardown approval continues to cover a rebuild within its stated scope and cost range.

```bash
umask 077
WORKLOAD_VARS="${WORKLOAD_VARS:-$PWD/.local/verified-workload.tfvars.json}"
FULL_PLAN="$PWD/.local/workload.tfplan"
# Precondition: both fresh targets are in state; review exact-ARN grants and IAM simulations.
test -s "$WORKLOAD_VARS" && git check-ignore -q "$FULL_PLAN" &&
rm -f -- "$FULL_PLAN" &&
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" -out="$FULL_PLAN" &&
chmod 600 "$FULL_PLAN" &&
terraform -chdir=terraform/workload show -no-color "$FULL_PLAN"
```

Stop if any command fails. Check the plan's proposed actions, effective IAM grants and runtime estimate. Only after confirming the plan remains within the existing costed approval, apply **that same** saved plan:

```bash
test "$(stat -c %a "$FULL_PLAN")" = 600 &&
terraform -chdir=terraform/workload apply "$FULL_PLAN"
```

The saved plan includes the version inputs. For a full deployment, follow the [ordered Ansible cleanup](../ansible/README.md#cleanup-before-terraform-destroy) to remove the DNS alias and controller-owned ALB first; if no Ingress or ALB was created, use the [partial-deployment teardown gate](workload/README.md#partial-deployment-teardown-before-ansible). Then use the same verified file for a **new** `plan -destroy -input=false -var-file="$WORKLOAD_VARS" -out="$PWD/.local/workload-destroy.tfplan"`; inspect and apply that exact saved plan in a reviewed permission window. If deletion waiters fail or EIP state becomes stale, follow [guarded recovery](workload/README.md#recovery-after-a-partial-destroy). Run the [scoped residual inventory](../scripts/README.md#residual-inventory-and-retained-costs) afterward with the needed read permissions; a denied read is inconclusive. Keep the verified file securely through teardown and rebuild. The retained foundation and state bucket have separate cleanup and possible ongoing charges.
