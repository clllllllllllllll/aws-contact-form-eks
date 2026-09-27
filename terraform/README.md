# Terraform roots

The three roots have different lifecycles:

| Root | Status | Purpose |
| --- | --- | --- |
| `bootstrap/` | Applied and verified in account `203888389134` | Persistent encrypted, versioned S3 bucket for Terraform state and lockfiles |
| `foundation/` | Stage 01 applied and verified in account `203888389134` on 27 September 2026; later stages pending | Resources retained between workload teardown and redeployment |
| `workload/` | Drafted and locally validated; not applied | Disposable VPC, EKS, RDS, IAM, ECR, and application secret metadata |

Bootstrap's state is local at `bootstrap/terraform.tfstate` and excluded from Git. Preserve it securely. Manual IAM policy handling is described in the [policy notes](policies/README.md). Foundation and workload both declare S3 backends, with distinct `foundation/terraform.tfstate` and `workload/terraform.tfstate` keys. Foundation stage 01 has remote state in the foundation key; the workload key remains unchecked and workload has not been applied. Recheck state before live init on each workstation.

The bootstrap plan reported `No changes` while the temporary bucket-setup policy was attached. That policy was then removed. To refresh or plan `terraform/bootstrap/` again, temporarily restore its setup/read permissions. The [state-access draft](policies/bootstrap/state-access-policy.json) scopes access to foundation and workload S3 state objects and locks; verify the actual grant and backend access before relying on it. Do not reapply or destroy bootstrap without reviewing the plan. Reattach the setup policy temporarily for deliberate bootstrap maintenance. Full state-bucket teardown also requires removing prevent_destroy and granting explicit deletion permissions after foundation and workload are gone.

The read-only runtime inventory policy draft at `policies/workstation/runtime-inventory-policy.json` covers the AWS Describe/List calls used by `scripts/check_residual.py` in Singapore. It is not attached. The first inventory attempt failed on missing `ec2:DescribeVpcs`; this must be resolved before claiming that teardown is clean.

The [IAM and service policy windows](#iam-and-service-policy-windows) below map Terraform resources to the stage 01 policy used for its completed apply and to later customer managed policy drafts. The later drafts do not establish effective provisioning access.

## Cost and apply gate

The state bucket and foundation stage 01 resources are known to have been applied in AWS. CLI read the effective Singapore Standard On-Demand quota as 8 vCPUs on 27 September 2026. The Singapore runtime estimate is a planning allowance: about US$0.50 per hour, or US$5 for ten hours of baseline EKS, EC2, Multi-AZ RDS, NAT, ALB and public IPv4 charges, before variable usage. US$10–20 for the whole planned run before credits is neither a cap nor an AWS quote. Check current Singapore Pricing Calculator rates, Billing credits, eligibility and expiry, and the US$10 budget/US$5 alert before any paid apply; the alert is not a hard stop. Count provisioning, deletion, setup, rehearsal and demo against one **less-than-ten-hour total** paid-runtime target. DNS, state, evidence, retained logs and optional account security services can continue to cost money after workload destroy; see [residual inventory and retained costs](../scripts/README.md#residual-inventory-and-retained-costs).

Before **each** further paid foundation stage, trusted key/app-secret target, deployer cluster target, full workload apply, or rebuild, review the exact saved plan, current estimate, credits, quota, ownership and teardown schedule and obtain explicit approval. The cluster target may create NAT gateways and starts EKS billing. Stop on a failed read, unexpected plan action or unresolved IAM simulation; never use `-auto-approve`. Stage 01 is applied; no later foundation stage or workload apply is verified.

## IAM and service policy windows

An administrator must inspect the real non-root principal, attached and inline policies, boundaries, service control policies, existing service-linked roles and named project roles. The [IAM resource/pass-role draft](policies/workload/deployer-iam-provisioning-draft.json) covers the current named roles, OIDC provider, relay instance profile and listed first-use service-linked roles. Its four OIDC statements remain inert until the issuer is known. The separate [role-write draft](policies/workload/deployer-iam-role-writes-draft.json) can change trust and write arbitrary inline policy content on four named roles **without a permissions boundary**; it is privilege sensitive. Have a trusted administrator review the actual trust and inline documents, create/version the customer managed policies, validate them with IAM Access Analyzer, simulate allowed and denied calls for the real principal, and attach role-write only for a monitored, time-limited apply/change/destroy window. Detach it immediately afterward; reattach only for another reviewed window. If that window cannot be enforced, the administrator executes Terraform. These IAM drafts grant no non-IAM provisioning actions.

| Window | Drafts to review and attach for that window |
| --- | --- |
| Completed foundation stage 01 plan/apply | Customer-managed `ContactFormFoundationStage01`, based on the [stage 01 policy](policies/foundation/deployer-foundation-stage-01.json), was attached for the approved stage |
| Later foundation plan/apply | [refresh](policies/foundation/deployer-foundation-service-draft-refresh.json) + [apply](policies/foundation/deployer-foundation-service-draft-apply.json), plus the approved IAM pair where the plan needs IAM |
| Optional foundation teardown | refresh + [destroy](policies/foundation/deployer-foundation-service-draft-destroy.json), replacing apply, plus needed IAM |
| Workload first create, full plan or destroy | Six [workload service drafts](workload/README.md#service-policy-scope) plus needed IAM, after exact ARN binding for the relevant stage |
| Read-only preflight, runtime inventory, workstation helpers | The trimmed [preflight](policies/workstation/preflight-read-policy.json) policy is attached; separate [runtime inventory](policies/workstation/runtime-inventory-policy.json) and [helper](policies/workstation/deployer-helper-service-draft.json) drafts need reviewed windows; none grants Terraform apply access |

The foundation service drafts contain no IAM or state-bucket permissions; [state access](policies/bootstrap/state-access-policy.json) is separate. For the approved 27 September stage 01 apply, customer-managed `ContactFormFoundationStage01` was attached and updated to allow `logs:TagLogGroup` alongside its existing `logs:TagResource` grant after a partial failure. A fresh plan then showed three additions only, and apply succeeded with three added. Confirm whether the temporary policy is still attached and detach it after its completed window. Later stages need separately reviewed **refresh + apply** for plan/apply, or **refresh + destroy** for a partial teardown. Do not keep both write policies attached. Inspect Config, Security Hub and CloudTrail ownership before selecting stage 02; preserve unrelated account controls. The three later foundation service drafts now scope hosted-zone access to `arn:aws:route53:::hostedzone/Z0153068M1DZTUZ2CE23`. Once ACM returns validation options, narrow `_*.cheelong.xyz` to the exact normalized CNAME in later apply/destroy policy versions, especially before teardown. The initial certificate request and tag-on-create paths need their own reviewed, short attachment window. Foundation `prevent_destroy` protects the zone, evidence bucket and retained log groups; the draft destroy policy does not authorize their full removal. Final retirement needs a separate owner decision and plan.

The recorded `ContactFormTerraformStateAccess` user policy is **inline** and consumes no managed attachment slot. A 27 September console screenshot shows `IAMUserChangePassword` attached directly to the user and `SignInLocalDevelopmentAccess` attached through the group; recheck the actual grants and quota before each window. With that one direct managed attachment, two IAM plus six workload policies would use **9/10** default user slots; adding the helper would use 10, so another directly attached managed policy requires rotation. Count `ContactFormFoundationStage01` as one more direct attachment if it remains attached. The group attachment has its own group quota. A later foundation window with the IAM pair plus refresh and apply (or destroy) would use 5 user slots, including the existing direct attachment, after the stage 01 policy is detached. If state access becomes managed, add one slot to each count. Rotate foundation, workload and helper policies by stage; count all actual attached policies before every attachment. An administrator validates final JSON against IAM's 6,144 nonwhitespace-character managed-policy limit and simulates both allowed and denied request tags, resource ARNs, `iam:PassRole`, OIDC create and dependent initial Tag, later tagged writes, and service actions. Local JSON parsing and Terraform validation alone do not establish AWS authorization. Apart from the stage 01 service policy, later IAM and provisioning drafts remain unverified live; the separate preflight grant has a successful quota read only.

## Backend initialization

Before another workstation runs `terraform init`, verify the non-root AWS identity and check both local state files and the exact S3 state keys. The workload's existing `.terraform/` directory came from a syntax-only `init -backend=false`; provider cache is not resource state. Run these checks with working AWS credentials; an access error does not mean an S3 key is empty:

```bash
find terraform/foundation terraform/workload -maxdepth 1 -name 'terraform.tfstate*' -print
aws sts get-caller-identity --profile contact-form-deployer
aws s3api list-object-versions --profile contact-form-deployer --region ap-southeast-1 --bucket aws-contact-form-eks-tfstate-203888389134-ap-southeast-1 --prefix foundation/terraform.tfstate
aws s3api list-object-versions --profile contact-form-deployer --region ap-southeast-1 --bucket aws-contact-form-eks-tfstate-203888389134-ap-southeast-1 --prefix workload/terraform.tfstate
```

Inspect the exact state keys, including current versions and delete markers; the prefix also matches lockfiles. The ongoing state-access policy includes `s3:ListBucketVersions`. If local state is absent and the remote check is clear, use ordinary `terraform -chdir=terraform/foundation init` or `terraform -chdir=terraform/workload init`. An existing current S3 state must be reused and checked with `terraform state list` before planning. If local state exists and the corresponding S3 key has no version history, keep a private backup and use `terraform init -migrate-state` for that root, then verify the migrated resources. If both copies exist, the exact key has a delete marker or older version but no current state, or an S3 check fails, stop and reconcile before init. Do not use `-reconfigure` or `-force-copy` to bypass a state conflict. Foundation stage 01 remote state now exists; workload state and any state migration remain unverified.

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

Stage 01 applied 11 resources in account `203888389134`, `ap-southeast-1`: hosted zone `cheelong.xyz` (`Z0153068M1DZTUZ2CE23`), evidence bucket `aws-contact-form-evidence-203888389134-ap-southeast-1` and its six configuration resources, and three seven-day EKS/RDS log groups. Registrar delegation is pending; no later foundation stage is verified.

Use the same branch of stage 02 and 03. If Config or Security Hub is already configured, resolve ownership or import before selecting a security stage. Never return to an earlier stage file after applying a later one: the earlier flags would propose deleting enabled resources. Use the current stage file for every later foundation plan. The commands below document the stage 01 procedure; in this account, select the next reviewed stage for further changes. From the repository root, after the backend checks and cost approval:

```bash
export AWS_PROFILE=contact-form-deployer
umask 077
terraform -chdir=terraform/foundation init
FOUNDATION_STAGE=stages/01-base.tfvars
terraform -chdir=terraform/foundation plan -input=false -var-file="$FOUNDATION_STAGE" -out=foundation.tfplan
terraform -chdir=terraform/foundation show -no-color foundation.tfplan
terraform -chdir=terraform/foundation apply foundation.tfplan
```

For each later stage, set `FOUNDATION_STAGE` to its table entry and repeat the plan, show, and apply commands. Apply only a newly generated plan after reviewing its resource changes; stop if planning fails. The ignored plan file is local and may contain sensitive deployment details. Workload planning follows a completed certificate stage and its own backend check.

After stage 01, compare all four `terraform -chdir=terraform/foundation output -json name_servers` values with public `dig NS cheelong.xyz +noall +answer`, allowing only case/trailing-dot differences. Enter the zone's nameservers at Exabytes and wait for public delegation before stage 03; an output alone is not DNS proof. After the selected stage 03, set `CERT_ARN="$(terraform -chdir=terraform/foundation output -raw certificate_arn)"` and use `aws acm describe-certificate --region ap-southeast-1 --certificate-arn "$CERT_ARN"` to confirm `ISSUED` before workload creation. Preserve the latest applied stage file and trail branch for future foundation plans. Record actual Config/FSBP findings in [security evidence](../docs/security.md); an enabled subscription or unevaluated control is not a pass.

## Workload version inputs

Before the first workload plan, run the [read-only preflight](workload/README.md#read-only-preflight) with chosen versions. It writes `.local/verified-workload.tfvars.json` only after every required read succeeds. From the repository root, initialize the workload backend after the backend check and foundation certificate stage. Keep the verified file through destroy and securely copy it for laptop rehearsal.

```bash
terraform -chdir=terraform/workload init
```

Before the full deployer plan below, complete **both target stages** in the [first-create and OIDC binding procedure](workload/README.md#two-target-first-creation-and-oidc-binding), with separate saved plans, cost reviews and approvals. A trusted administrator first creates `aws_kms_key.eks` and `aws_secretsmanager_secret.app` in the same reconciled backend, then binds their exact ARNs in the KMS, EKS and secret policy reviews. With all four OIDC statements still inert, the deployer applies a separately approved `aws_eks_cluster.main` target using the **same verified variables**. The administrator binds the new issuer to all four statements in an ignored mode-600 copy of the IAM policy template and activates that reviewed version. Only then make a fresh full workload plan. Repeat both targets and regenerate the review copy on rebuild.

```bash
WORKLOAD_VARS="${WORKLOAD_VARS:-$PWD/.local/verified-workload.tfvars.json}"
# Precondition: both approved targets, exact KMS/secret/OIDC rebinding, and policy attachment are complete.
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" -out=workload.tfplan
terraform -chdir=terraform/workload show -no-color workload.tfplan
# Apply only this reviewed saved plan after the cost/credit check and explicit approval.
terraform -chdir=terraform/workload apply workload.tfplan
```

The saved plan includes the version inputs. For teardown, follow the [ordered Ansible cleanup](../ansible/README.md#cleanup-before-terraform-destroy) to remove the DNS alias and controller-owned ALB first. Then use the same verified file for `plan -destroy -input=false -var-file="$WORKLOAD_VARS" -out=workload-destroy.tfplan`; inspect it with `show` and apply that saved plan in a reviewed permission window. Run the [scoped residual inventory](../scripts/README.md#residual-inventory-and-retained-costs) afterward. Keep the verified file securely with the workstation's deployment records through teardown and rebuild.
