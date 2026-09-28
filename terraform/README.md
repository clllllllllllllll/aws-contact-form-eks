# Terraform roots

The three roots have different lifecycles:

| Root | Status | Purpose |
| --- | --- | --- |
| `bootstrap/` | Applied and verified in account `203888389134` | Persistent encrypted, versioned S3 bucket for Terraform state and lockfiles |
| `foundation/` | Stages 01–03 applied and verified in account `203888389134` on 27 September 2026 | Resources retained between workload teardown and redeployment |
| `workload/` | Full deployment and two-step teardown on 28 September 2026; Terraform tracks no managed workload resources | Disposable VPC, EKS, RDS, IAM, ECR, and application secret metadata |

Bootstrap's state is local at `bootstrap/terraform.tfstate` and excluded from Git. Preserve it securely. Manual IAM policy handling is described in the [policy notes](policies/README.md). Foundation and workload both declare S3 backends, with distinct `foundation/terraform.tfstate` and `workload/terraform.tfstate` keys. Foundation stages 01–03 have remote state in the foundation key. After the full workload teardown and two-EIP retry, `terraform -chdir=terraform/workload state list` showed no managed resources. The versioned S3 state still records historical versions; check the current object and state before using another workstation.

The bootstrap plan reported `No changes` while the temporary bucket-setup policy was attached. That policy was then removed. To refresh or plan `terraform/bootstrap/` again, temporarily restore its setup/read permissions. The [state-access draft](policies/bootstrap/state-access-policy.json) scopes access to foundation and workload S3 state objects and locks; verify the actual grant and backend access before relying on it. Do not reapply or destroy bootstrap without reviewing the plan. Reattach the setup policy temporarily for deliberate bootstrap maintenance. Full state-bucket teardown also requires removing prevent_destroy and granting explicit deletion permissions after foundation and workload are gone.

The read-only [demo evidence and runtime inventory policy](policies/README.md#read-only-demo-evidence-grant) is effective through an inline group grant. A post-teardown read of the checker's named/tagged Singapore scope completed without denied calls and found no actionable workload resources; three project KMS keys were pending deletion. This does not prove a zero bill because foundation and other resources remain outside that scope.

The [IAM and service policy windows](#iam-and-service-policy-windows) below map Terraform resources to the stage 01 policy used for its completed apply and to later customer managed policy drafts. The later drafts do not establish effective provisioning access.

## Cost and apply gate

The state bucket and foundation stages 01–03 remain applied. The full workload was destroyed on 28 September after a two-EIP retry; no managed workload resources remain in current Terraform state. Its KMS key is `PendingDeletion`, scheduled for 5 October 2026. CLI read the effective Singapore Standard On-Demand quota as 8 vCPUs on 27 September; recheck it before rebuilding. The owner's full deployment and teardown approval covered an estimated **US$0.50–1.00 per hour** and a **US$10–20 planning allowance before credits** for less than ten total hours. These are estimates, not a cap or a bill. Before another paid apply, check the current plan, Singapore prices, credits, quota, remaining runtime and teardown route. The US$10 budget and US$5 actual-cost email alert do not stop spending. DNS, state, evidence, retained logs and account security services can continue to cost money after workload destroy; see [residual inventory and retained costs](../scripts/README.md#residual-inventory-and-retained-costs).

Obtain explicit confirmation for each new paid deployment after presenting its fresh plan, estimate and expected runtime; a new cluster target starts EKS, NAT and public IPv4 charges. Stop on a failed prerequisite read, unexpected plan action or unresolved IAM denial; do not use `-auto-approve`. Today's deployment verified two Ready workers, two Ready Flask pods, one Ingress ALB, HTTPS and RDS persistence. A fresh rebuild and one-shot teardown remain unverified.

**Recorded attempt and teardown (27–28 September 2026):** The first target created a KMS key and app-secret metadata. A cluster-target retry created a private EKS API, two NAT gateways and supporting network resources after a missing `ec2:DescribeAddressesAttribute` read was fixed. The approved full plan was **partially applied**: it created a private SSM relay, private Multi-AZ PostgreSQL RDS with an RDS-managed master secret, ECR and a pushed image. The workstation reached EKS `/readyz` through the TLS-verifying SSM tunnel. Both node groups stopped before worker launch because the deployer was denied `iam:GetRole` for the EKS node-group service-linked role. There was no Flask deployment or ALB. The partial workload was then destroyed; no managed workload resources remain in Terraform state. EKS deletion waiters and EIP release required [guarded recovery](workload/README.md#recovery-after-a-partial-destroy). The incomplete residual checker remains an open verification gap.

**Verified full deployment and teardown (28 September 2026):** The later full workload reached two Ready workers and pods, one Ingress-created ALB, HTTPS `200`, POST `/thanks`, and RDS readback `id=1`. An Ansible rerun reported `changed=0`. The first Terraform destroy deleted 70 of 72 resources but both EIPs failed on `ec2:DisassociateAddress`; NAT deletion had disassociated them, and a fresh two-EIP plan released them. Workload state is empty, and scoped residual inventory later completed. This does not demonstrate a one-shot destroy or a fresh rebuild. Security Hub finding reads now work, but project control results remain to be classified. Keep the cost and plan gates for another paid run.

## IAM and service policy windows

An administrator inspects the real non-root principal, attached and inline policies, boundaries, service controls, named project roles and service-linked roles. Publish the reviewed [workload service drafts](workload/README.md#service-policy-scope), [IAM provisioning draft](policies/workload/deployer-iam-provisioning-draft.json), and [workstation helper](policies/workstation/deployer-helper-service-draft.json) as reusable default versions **once**. Their account/Region/name patterns cover newly generated KMS, secret, OIDC and relay IDs, so future workload rebuilds need no policy JSON rebinding or new policy versions. Previously published copies tied to destroyed IDs must be replaced during this one-time migration. Verify `iam:GetRole` for `AWSServiceRoleForAmazonEKSNodegroup` with the deployer identity before another paid apply; a role or `NoSuchEntity` result confirms the read was authorized, whereas `AccessDenied` does not. The separate [role-write draft](policies/workload/deployer-iam-role-writes-draft.json) can change trust and write inline policies on four named roles without a permissions boundary. Attach it only for monitored apply/change/destroy windows.

| Window | Drafts and attachment action |
| --- | --- |
| Completed foundation stage 01 | `ContactFormFoundationStage01` was attached for the approved stage; confirm its removal after that window. |
| Future foundation change or teardown | Review the foundation refresh plus apply or destroy draft; keep only the needed write window attached. |
| Workload first target on every fresh build | Attach [temporary bootstrap](policies/workload/deployer-workload-bootstrap-temporary-draft.json) around the reviewed KMS key and app-secret metadata creates; detach immediately after, including on failure. Retain it detached if desired. |
| Workload cluster target, full apply and destroy | Attach only the needed six workload service policies and IAM pair; verify reusable default versions, tags, effective grants and attachment slots. |
| Read-only preflight, runtime inventory and workstation helpers | Rotate [preflight](policies/workstation/preflight-read-policy.json), [runtime inventory](policies/workstation/runtime-inventory-policy.json) and [helper](policies/workstation/deployer-helper-service-draft.json) for their separate operations. |

The foundation service drafts contain no IAM or state-bucket permissions; [state access](policies/bootstrap/state-access-policy.json) is separate. The approved stage 01 policy was updated with `logs:TagLogGroup` after a partial failure; a fresh plan then showed three additions only and the apply succeeded. Future foundation writes need separately reviewed refresh plus apply or destroy drafts. Preserve unrelated account controls. Foundation `prevent_destroy` protects the retained zone, evidence bucket and log groups; final retirement requires a separate owner decision and plan.

The recorded `ContactFormTerraformStateAccess` policy is inline and consumes no managed attachment slot. Six workload service policies plus two IAM policies occupy eight of the default ten direct user slots; helper makes nine and one temporary, preflight or runtime-inventory policy makes ten. Check the actual attachment list and group grants in the IAM Console before each window. A policy file or previous screenshot is not proof of an effective grant. Validate published JSON, the 6,144 nonwhitespace-character managed-policy limit, allowed and denied tag/ARN cases, OIDC create plus dependent initial Tag, SSM document check, `iam:PassRole` and the node-group linked-role read. Successful local parsing and Terraform planning do not establish effective AWS permissions. The revised network draft includes tagged-EIP `ec2:DisassociateAddress` for the teardown denial; publish and test it once before relying on a one-shot destroy. [Policy publication and residual risks](policies/README.md#one-time-publication-for-repeatable-workload-builds) give the detailed checks.

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

Read-only preflight returned `READY` before the **previous** workload attempt; that result is not proof of current quota, versions or capacity. Run the [read-only preflight](workload/README.md#read-only-preflight) again for a rebuild with chosen versions. It writes `.local/verified-workload.tfvars.json` only after every required read succeeds. From the repository root, initialize the workload backend after the backend check and foundation certificate stage. Keep the verified file through destroy; rerun preflight before the next demo rehearsal on this workstation.

```bash
terraform -chdir=terraform/workload init
```

The disposable workload currently has **no managed resources in Terraform state**. Follow the [two-target first-creation and repeatable IAM procedure](workload/README.md#two-target-first-creation-and-repeatable-iam): fresh KMS/app-secret target, then fresh network/EKS cluster target, with new saved plans, reviewed permissions, and cost checks. Before cluster creation, retest `iam:GetRole` for the EKS node-group service-linked role. After cluster creation, verify its live issuer and exact Terraform role trust; the reusable IAM policy already covers its regional issuer shape. Before the full apply, review current resource tags, attachment slots and IAM simulations. The earlier **50-addition plan was approved and partially applied**, then invalidated by teardown; do not reuse it. Present the current estimate and obtain confirmation before another paid build.

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
