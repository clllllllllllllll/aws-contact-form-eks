# Terraform roots

The three roots have different lifecycles:

| Root | Status | Purpose |
| --- | --- | --- |
| `bootstrap/` | Applied and verified in account `203888389134` | Persistent encrypted, versioned S3 bucket for Terraform state and lockfiles |
| `foundation/` | Drafted and locally validated; not applied | Resources retained between workload teardown and redeployment |
| `workload/` | Drafted and locally validated; not applied | Disposable VPC, EKS, RDS, IAM, ECR, and application secret metadata |

Bootstrap's state is local at `bootstrap/terraform.tfstate` and excluded from Git. Preserve it securely. Foundation and workload both declare S3 backends, with distinct `foundation/terraform.tfstate` and `workload/terraform.tfstate` keys. Neither root has been applied per the project record, and no local state files were present at this checkpoint; remote S3 state has not been freshly verified. Recheck state before the first live init on each workstation.

The bootstrap plan reported `No changes` while the temporary bucket-setup policy was attached. That policy was then removed. To refresh or plan `terraform/bootstrap/` again, temporarily restore its setup/read permissions; the ongoing state-access policy alone only covers the foundation and workload S3 state objects and locks. Do not reapply or destroy bootstrap without reviewing the plan. Test the separate backend access using the ongoing state-access policy alone. Reattach the setup policy temporarily for deliberate bootstrap maintenance. Full state-bucket teardown also requires removing prevent_destroy and granting explicit deletion permissions after foundation and workload are gone.

The read-only runtime inventory policy draft at `bootstrap/runtime-inventory-policy.json` covers the AWS Describe/List calls used by `scripts/check_residual.py` in Singapore. It is not attached. The first inventory attempt failed on missing `ec2:DescribeVpcs`; this must be resolved before claiming that teardown is clean.

The [deployer permission review](../docs/deployer-permissions.md) maps the current IAM resources to two unattached customer managed policy drafts: one for pass-role, OIDC, instance profiles, and first-use service-linked roles, and one for named role writes. The second permits arbitrary inline policy content on four project roles and therefore requires a trusted administrator, a time-limited attachment, and live simulation before apply or destroy. These IAM drafts do not supply other AWS provisioning actions.

Review the actual Singapore cost and teardown plan separately before any foundation or workload apply.

## Backend initialization

Before the first live `terraform init`, verify the non-root AWS identity and check both local state files and the exact S3 state keys. The workload's existing `.terraform/` directory came from a syntax-only `init -backend=false`; provider cache is not resource state. Run these checks with working AWS credentials; an access error does not mean an S3 key is empty:

```bash
find terraform/foundation terraform/workload -maxdepth 1 -name 'terraform.tfstate*' -print
aws sts get-caller-identity --profile contact-form-deployer
aws s3api list-object-versions --profile contact-form-deployer --region ap-southeast-1 --bucket aws-contact-form-eks-tfstate-203888389134-ap-southeast-1 --prefix foundation/terraform.tfstate
aws s3api list-object-versions --profile contact-form-deployer --region ap-southeast-1 --bucket aws-contact-form-eks-tfstate-203888389134-ap-southeast-1 --prefix workload/terraform.tfstate
```

Inspect the exact state keys, including current versions and delete markers; the prefix also matches lockfiles. The ongoing state-access policy includes `s3:ListBucketVersions`. If local state is absent and the remote check is clear, use ordinary `terraform -chdir=terraform/foundation init` or `terraform -chdir=terraform/workload init`. An existing current S3 state must be reused and checked with `terraform state list` before planning. If local state exists and the corresponding S3 key has no version history, keep a private backup and use `terraform init -migrate-state` for that root, then verify the migrated resources. If both copies exist, the exact key has a delete marker or older version but no current state, or an S3 check fails, stop and reconcile before init. Do not use `-reconfigure` or `-force-copy` to bypass a state conflict. No migration or live backend init has been run for this checkpoint.

The fixed-name RDS `postgresql` and `upgrade` log groups now belong to foundation. Before either root's next apply, inspect both actual states for `aws_cloudwatch_log_group.rds` addresses. If workload state tracks either group, stop and arrange a deliberate, reviewed cross-root state migration or import with state backups; do not allow a workload plan to destroy it or assume this code move transfers state. If foundation state already tracks a group, verify that ownership and avoid duplicate management. Apply foundation and verify its `rds_log_group_names` output before planning workload.

## Foundation stages

Each checked-in stage file sets all three feature flags. The flags have no defaults; `plan -input=false` fails if a stage file is omitted instead of prompting for values. Select the next stage only after reviewing the account-wide service inventory, Terraform ownership, DNS delegation, and cost as applicable:

| Stage file under `foundation/stages/` | Use when |
| --- | --- |
| `01-base.tfvars` | Initial DNS zone, evidence bucket, and retained EKS and RDS log groups |
| `02-security-existing-trail.tfvars` | Config and Security Hub can be managed here; a suitable management-event trail already exists |
| `02-security-project-trail.tfvars` | Config and Security Hub can be managed here; a new project trail is needed |
| `03-ready-existing-trail.tfvars` | Registrar delegation is verified; continue the existing-trail branch and request the ACM certificate |
| `03-ready-project-trail.tfvars` | Registrar delegation is verified; continue the project-trail branch and request the ACM certificate |

Use the same branch of stage 02 and 03. If Config or Security Hub is already configured, resolve ownership or import before selecting a security stage. Never return to an earlier stage file after applying a later one: the earlier flags would propose deleting enabled resources. Use the current stage file for every later foundation plan. From the repository root, after the backend checks and cost approval:

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

## Workload version inputs

Before the first workload plan, run the [read-only preflight](../docs/preflight.md) with chosen versions. It writes `.local/verified-workload.tfvars.json` only after every required read succeeds. From the repository root, initialize the workload backend after the backend check and foundation certificate stage.

Before the full deployer plan below, complete the [trusted first-create stage](../docs/workload-permissions.md#required-trusted-bootstrap-and-demo-guide-change) under the [live-demo approval gates](../docs/live-demo.md#4-read-only-pins-and-fresh-runtime-plan). In the same reconciled backend, a separate trusted administrator must review and, after Singapore cost/credit review and explicit approval, apply a saved Terraform plan targeted at `aws_kms_key.eks` and `aws_secretsmanager_secret.app`. Read both exact ARNs from state, replace every exact-ARN placeholder in the KMS, EKS and Secrets Manager/ECR drafts, then validate/simulate and attach the final policies. Switch back to the deployer for a fresh full plan; earlier full plans are stale. Repeat this stage with new ARNs on rebuild.

```bash
WORKLOAD_VARS="$PWD/.local/verified-workload.tfvars.json"
terraform -chdir=terraform/workload init
# On a fresh build or rebuild, complete trusted first-create and policy attachment first.
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" -out=workload.tfplan
terraform -chdir=terraform/workload show -no-color workload.tfplan
# Apply only this reviewed saved plan after the cost/credit check and explicit approval.
terraform -chdir=terraform/workload apply workload.tfplan
```

The saved plan includes the version inputs. For teardown, remove the ALB through Ansible first, then use the same verified file for `plan -destroy -input=false -var-file="$WORKLOAD_VARS" -out=workload-destroy.tfplan`; inspect it with `show` and apply that saved plan. Keep the verified file securely with the workstation's deployment records through teardown and rebuild.
