# Terraform roots

The three roots have different lifecycles:

| Root | Status | Purpose |
| --- | --- | --- |
| `bootstrap/` | Applied and verified in account `203888389134` | Persistent encrypted, versioned S3 bucket for Terraform state and lockfiles |
| `foundation/` | Stages 01–03 applied and verified in account `203888389134` on 27 September 2026 | Resources retained between workload teardown and redeployment |
| `workload/` | Rebuilt and torn down on 29 September 2026; Terraform tracks no managed workload resources | Disposable VPC, EKS, RDS, IAM, ECR, and application secret metadata |

Bootstrap's state is local at `bootstrap/terraform.tfstate` and excluded from Git. Preserve it securely. Manual IAM policy handling is described in the [policy notes](policies/README.md). Foundation and workload both declare S3 backends, with distinct `foundation/terraform.tfstate` and `workload/terraform.tfstate` keys. Foundation stages 01–03 have remote state in the foundation key. After the full workload teardown and two-EIP retry, `terraform -chdir=terraform/workload state list` showed no managed resources. The versioned S3 state still records historical versions; check the current object and state before using another workstation.

The bootstrap plan reported `No changes` while the temporary bucket-setup policy was attached. That policy was then removed. To refresh or plan `terraform/bootstrap/` again, temporarily restore its setup/read permissions. The [state-access draft](policies/bootstrap/state-access-policy.json) scopes access to foundation and workload S3 state objects and locks; verify the actual grant and backend access before relying on it. Do not reapply or destroy bootstrap without reviewing the plan. Reattach the setup policy temporarily for deliberate bootstrap maintenance. Full state-bucket teardown also requires removing prevent_destroy and granting explicit deletion permissions after foundation and workload are gone.

The read-only [demo evidence and runtime inventory policy](policies/README.md#read-only-demo-evidence-grant) is effective through an inline group grant. After the latest teardown, the scoped Singapore inventory completed without denied reads or actionable workload resources; four project KMS keys are pending deletion. Foundation and other resources remain outside that scope and may incur charges.

The [IAM and service policy windows](#iam-and-service-policy-windows) below map Terraform resources to the stage 01 policy used for its completed apply and to later customer managed policy drafts. The later drafts do not establish effective provisioning access.

## Cost and apply gate

The state bucket and foundation stages 01–03 remain applied. The latest workload was destroyed on 29 September after a two-EIP retry; no managed workload resources remain in current Terraform state. Four workload KMS keys are pending deletion on 5–6 October. The Singapore Standard On-Demand quota was 8 vCPUs at the latest preflight; recheck it before rebuilding. The previous deployment estimate was **US$0.50–1.00 per hour** with a **US$10–20 planning allowance before credits**. These are estimates, not a cap or a bill. Before another paid apply, check the current plan, Singapore prices, credits, quota, expected runtime and teardown route. The budget alerts do not stop spending. DNS, state, evidence, retained logs and account security services can continue to cost money after workload destroy; see [residual inventory and retained costs](../scripts/README.md#residual-inventory-and-retained-costs).

Obtain explicit confirmation for each new paid deployment after presenting its fresh plan, estimate and expected runtime; a new cluster target starts EKS, NAT and public IPv4 charges. Stop on a failed prerequisite read, unexpected plan action or unresolved IAM denial; do not use `-auto-approve`. Two complete deployments verified EKS, RDS, Ansible, one HTTPS ALB and PostgreSQL readback. The latest Ansible rerun had `changed=0`. In both full teardowns, the first Terraform destroy left two EIPs because of an `ec2:DisassociateAddress` denial after NAT deletion; a fresh plan released them. One-pass destroy remains unverified. The [security report](../docs/security.md) records the live FSBP results.

## IAM and service policy windows

An administrator inspects the real non-root principal, attached and inline policies, boundaries, service controls, named project roles and service-linked roles. The reviewed [workload service drafts](workload/README.md#service-policy-scope), [IAM provisioning draft](policies/workload/deployer-iam-provisioning-draft.json), and [workstation helper](policies/workstation/deployer-helper-service-draft.json) were published as reusable default versions before the latest build. Their account/Region/name patterns cover newly generated KMS, secret, OIDC and relay IDs, so future workload rebuilds need no generated-ID edits when those versions remain current. Verify `iam:GetRole` for `AWSServiceRoleForAmazonEKSNodegroup` with the deployer identity before another paid apply; a role or `NoSuchEntity` result confirms the read was authorized, whereas `AccessDenied` does not. The separate [role-write draft](policies/workload/deployer-iam-role-writes-draft.json) can change trust and write inline policies on four named roles without a permissions boundary. Attach it only for monitored apply/change/destroy windows.

| Window | Drafts and attachment action |
| --- | --- |
| Completed foundation stage 01 | `ContactFormFoundationStage01` was attached for the approved stage; confirm its removal after that window. |
| Future foundation change or teardown | Review the foundation refresh plus apply or destroy draft; keep only the needed write window attached. |
| Workload first target on every fresh build | Attach [temporary bootstrap](policies/workload/deployer-workload-bootstrap-temporary-draft.json) around the reviewed KMS key and app-secret metadata creates; detach immediately after, including on failure. Retain it detached if desired. |
| Workload cluster target, full apply and destroy | Attach only the needed six workload service policies and IAM pair; verify reusable default versions, tags, effective grants and attachment slots. |
| Read-only preflight, runtime inventory and workstation helpers | Rotate [preflight](policies/workstation/preflight-read-policy.json), [runtime inventory](policies/workstation/runtime-inventory-policy.json) and [helper](policies/workstation/deployer-helper-service-draft.json) for their separate operations. |

The foundation service drafts contain no IAM or state-bucket permissions; [state access](policies/bootstrap/state-access-policy.json) is separate. The approved stage 01 policy was updated with `logs:TagLogGroup` after a partial failure; a fresh plan then showed three additions only and the apply succeeded. Future foundation writes need separately reviewed refresh plus apply or destroy drafts. Preserve unrelated account controls. Foundation `prevent_destroy` protects the retained zone, evidence bucket and log groups; final retirement requires a separate owner decision and plan.

The recorded `ContactFormTerraformStateAccess` policy is inline and consumes no managed attachment slot. The account-level managed-policy-per-user quota was increased to 12; ten managed policies were last shown attached, including the workstation helper. The Bootstrap policy was attached briefly for the first target and detached afterward without a policy swap. The group inline [scoped self-attachment policy](policies/workstation/scoped-self-attachment-policy.json) limits this CLI action to named policies; its source alone grants nothing. Validate effective grants and attachment slots before future applies. The current tagged-EIP `ec2:DisassociateAddress` statement did not authorize Terraform's stale-association request on `*/*`; follow the guarded retry in the [main teardown instructions](../README.md#7-tear-down-only-the-workload). [Policy publication and residual risks](policies/README.md#one-time-publication-for-repeatable-workload-builds) give detailed checks.

## Backend initialization

Before another workstation runs `terraform init`, verify the non-root AWS identity and check both local state files and the exact S3 state keys. The workload S3 backend was initialized for the first target; `.terraform/` alone is not proof of current resource state. Run these checks with working AWS credentials; an access error does not mean an S3 key is empty:

```bash
find terraform/foundation terraform/workload -maxdepth 1 -name 'terraform.tfstate*' -print
aws sts get-caller-identity --profile contact-form-deployer
aws s3api list-object-versions --profile contact-form-deployer --region ap-southeast-1 --bucket aws-contact-form-eks-tfstate-203888389134-ap-southeast-1 --prefix foundation/terraform.tfstate
aws s3api list-object-versions --profile contact-form-deployer --region ap-southeast-1 --bucket aws-contact-form-eks-tfstate-203888389134-ap-southeast-1 --prefix workload/terraform.tfstate
```

Inspect the exact state keys, including current versions and delete markers; the prefix also matches lockfiles. The ongoing state-access policy includes `s3:ListBucketVersions`. If local state is absent and the remote check is clear, use ordinary `terraform -chdir=terraform/foundation init` or `terraform -chdir=terraform/workload init`. An existing current S3 state must be reused and checked with `terraform state list` before planning. If local state exists and the corresponding S3 key has no version history, keep a private backup and use `terraform init -migrate-state` for that root, then verify the migrated resources. If both copies exist, the exact key has a delete marker or older version but no current state, or an S3 check fails, stop and reconcile before init. Do not use `-reconfigure` or `-force-copy` to bypass a state conflict. Foundation remote state contains stages 01–03. The workload's **current** state was emptied of managed resources after the 29 September teardown; older S3 object versions record earlier deployments and are not the desired state. Recheck both current states on the workstation used for a rebuild.

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
| `04-standby-project-trail.tfvars` | After saving live evidence and destroying the workload, stop Config recording and disable Security Hub/FSBP while retaining their configuration, the logging project CloudTrail trail, certificate and core foundation |

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

### Low-cost standby between submission and a later live demo

The account currently uses the **project-trail** branch. Save dated Config, Security Hub and CloudTrail evidence first; then confirm the workload state and scoped residual inventory are empty. The dedicated `04-standby-project-trail.tfvars` keeps the issued certificate and retained DNS, buckets, log groups, Config recorder/delivery configuration and **logging** CloudTrail management trail. It stops the recorder and disables the project Security Hub account/FSBP subscription. The first copy of CloudTrail management-event delivery has no CloudTrail charge; small S3 storage/request charges remain, and keeping the trail preserves audit coverage. A policy attachment used for the workload does not by itself grant these foundation changes; verify the authorized operator's effective permissions before planning or applying. Do not use `01-base.tfvars` or `terraform destroy` for standby. [CloudTrail pricing](https://aws.amazon.com/cloudtrail/pricing/).

Create a **new ignored, mode-600 saved plan** for standby. Review every planned action and stop if it changes the Route 53 zone, ACM certificate, buckets, log groups, Config recorder/delivery configuration, CloudTrail logging/trail definition, or unrelated resources. Apply the exact saved plan only after that review and the user's approval. The stage file alone does not change AWS. Re-enable the project-trail branch with `03-ready-project-trail.tfvars` before the later demo, allowing time for Config recording and fresh FSBP evaluations. A paused service cannot supply current findings. Retained Route 53 and S3 resources may still incur charges.

## Workload version inputs

Read-only preflight returned `READY` before the **previous** workload attempt; that result is not proof of current quota, versions or capacity. Run the [read-only preflight](workload/README.md#read-only-preflight) again for a rebuild with chosen versions. It writes `.local/verified-workload.tfvars.json` only after every required read succeeds. From the repository root, initialize the workload backend after the backend check and foundation certificate stage. Keep the verified file through destroy; rerun preflight before the next demo rehearsal on this workstation.

```bash
terraform -chdir=terraform/workload init
```

The disposable workload currently has **no managed resources in Terraform state**. Follow the [two-target first-creation and repeatable IAM procedure](workload/README.md#two-target-first-creation-and-repeatable-iam): fresh KMS/app-secret target, then fresh network/EKS cluster target, with new saved plans, reviewed permissions, and cost checks. Before cluster creation, retest `iam:GetRole` for the EKS node-group service-linked role. After cluster creation, verify its live issuer and exact Terraform role trust; the reusable IAM policy already covers its regional issuer shape. Before the full apply, review current resource tags, attachment slots and IAM simulations. Earlier saved plans were applied and invalidated by teardown; do not reuse them. Present the current estimate and obtain confirmation before another paid build.

```bash
umask 077
WORKLOAD_VARS="${WORKLOAD_VARS:-$PWD/.local/verified-workload.tfvars.json}"
FULL_PLAN="$PWD/.local/workload.tfplan"
# Precondition: both fresh targets are in state; verify resource tags and IAM simulations.
test -s "$WORKLOAD_VARS" && git check-ignore -q "$FULL_PLAN" &&
rm -f -- "$FULL_PLAN" &&
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" -out="$FULL_PLAN" &&
chmod 600 "$FULL_PLAN" &&
terraform -chdir=terraform/workload show -no-color "$FULL_PLAN"
```

Stop if any command fails. Check the plan's proposed actions, effective IAM grants and runtime estimate. Only after obtaining confirmation for this build, apply **that same** saved plan:

```bash
test "$(stat -c %a "$FULL_PLAN")" = 600 &&
terraform -chdir=terraform/workload apply "$FULL_PLAN"
```

The saved plan includes the version inputs. For a full deployment, follow the [ordered Ansible cleanup](../ansible/README.md#cleanup-before-terraform-destroy) to remove the DNS alias and controller-owned ALB first; if no Ingress or ALB was created, use the [partial-deployment teardown gate](workload/README.md#partial-deployment-teardown-before-ansible). Then use the same verified file for a **new** `plan -destroy -input=false -var-file="$WORKLOAD_VARS" -out="$PWD/.local/workload-destroy.tfplan"`; inspect and apply that exact saved plan in a reviewed permission window. If deletion waiters fail or EIP state becomes stale, follow [guarded recovery](workload/README.md#recovery-after-a-partial-destroy). Run the [scoped residual inventory](../scripts/README.md#residual-inventory-and-retained-costs) afterward with the needed read permissions; a denied read is inconclusive. Keep the verified file securely through teardown and rebuild. The retained foundation and state bucket have separate cleanup and possible ongoing charges.
