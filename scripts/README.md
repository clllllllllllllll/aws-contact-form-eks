# Workstation deployment helpers

These scripts are local deployment helpers. In the latest live run, `open_tunnel.py` reached the private EKS API with TLS verification, `publish_image.py` pushed an immutable image to ECR, and the alias helper managed the single Ingress ALB's Route 53 record. After teardown, the scoped residual inventory found no actionable workload resources or read errors; four project KMS keys are pending deletion.

| Script | Purpose |
| --- | --- |
| check_plan.py | Read-only review of saved first, cluster and full workload plans. Checks exact resource sets, destructive actions, selected security settings and known startup metadata drift; prints no secret values. |
| open_tunnel.py | Check the account, read Terraform outputs, write a TLS-verifying kubeconfig and start an SSM port forward to the private EKS API. |
| publish_image.py | Use the committed app tree as an immutable ECR tag, then return the image digest. A temporary Docker credential directory is removed after publishing. |
| manage_alb.py | Create/remove the Route 53 apex alias only for the tagged Ingress ALB, and block workload teardown while that ALB exists. |
| check_residual.py | Read-only Singapore inventory after workload teardown. Reports the named runtime resources, tagged EBS volumes/snapshots, retained RDS automated backups, and tagged workload KMS keys with deletion state. |
| show_findings.py | Read-only, project-filtered Security Hub FSBP findings. The full view prints control, status, resource and update time; `--summary` prints compact control counts for a readable screenshot. Neither view prints secret values. |

The scripts read resource identifiers and secret ARNs, not secret values. Run them through the Ansible playbooks where possible. Generated kubeconfig and the non-secret alias ownership record are stored under Git-ignored .local/.

After each saved workload plan, run `python scripts/check_plan.py first|cluster|full <saved-plan-path>` with the matching stage name. Proceed only on `PLAN CHECK PASS` and after the cost/plan approval gate. A `FAIL` requires inspection with `terraform show -no-color <saved-plan-path>` and a corrected new plan; the helper checks the expected resource set and selected critical settings, not every provider attribute.

Before image, tunnel or ALB helper use, check that the Session Manager plugin is installed in WSL, the non-root AWS profile has the required permissions, and the Terraform workload has been applied. Preflight runs before workload creation; residual inventory runs after teardown. The scripts do not replace the cost review or the Terraform plan.

## Helper permission window

The [helper policy draft](../terraform/policies/workstation/deployer-helper-service-draft.json) covers image publication to the exact `contact-form` ECR repository, SSM tunneling to a Singapore relay instance with `Name=contact-form-ssm-relay` and the three workload ownership tags, ELB metadata reads, and only `CREATE`/`DELETE` of the `cheelong.xyz` apex `A` alias in hosted zone `Z0153068M1DZTUZ2CE23`. It grants no Terraform provisioning, preflight, runtime inventory, or Kubernetes authorization. The AWS-owned `AWS-StartPortForwardingSessionToRemoteHost` document is the only allowed session document. `scripts/open_tunnel.py` reads the **current** relay instance ID from Terraform output and passes that document explicitly; replacing the relay does not require publishing a new helper policy version.

Before another build, verify the published helper policy still matches the reviewed source. Confirm the current relay ID with `terraform -chdir=terraform/workload output -raw relay_instance_id`, its live Name/Project/ManagedBy/Lifecycle tags, the retained hosted zone ID, account and Region. Simulate an allowed tagged relay, an untagged or mistagged instance, the context key present as `false`, another document, another hosted zone, and invalid DNS record name/type/action including `UPSERT`. The earlier live tunnel required `BoolIfExists`: a strict `Bool` denied it when the context key was absent. An omitted context key passes this condition, so the separate document ARN check remains important; do not claim that this condition alone blocks a default shell session. The forwarding document does not restrict the requested remote host or port, and Route 53 IAM conditions do not verify the alias target; retain the local ownership checks and `.local/alb-alias.json` record. Check the non-root identity, effective attachment and 12-policy quota before use. An access denial is a review point, not a reason to broaden the policy.

The trimmed [preflight read policy](../terraform/policies/workstation/preflight-read-policy.json) is separate; its EC2 quota read succeeded previously. The [runtime inventory policy](../terraform/policies/workstation/runtime-inventory-policy.json) is effective as `ContactFormDemoEvidenceRead`, an inline grant on `contact-form-provisioners`; residual inventory and Security Hub reads succeeded during the latest run. The [state access policy](../terraform/policies/bootstrap/state-access-policy.json) is recorded as inline; recheck the actual grant and backend access.

## Project security findings

From the repository root with the assignment virtual environment active, run:

```bash
python scripts/show_findings.py --profile contact-form-deployer
python scripts/show_findings.py --profile contact-form-deployer --summary
```

It reads only `ACTIVE` AWS Foundational Security Best Practices findings in the fixed account and Singapore Region, then selects resources by the project's exact names or ownership tag. The full view lists control ID, status, resource ID and `UpdatedAt`; `--summary` groups counts. It excludes unrelated account findings and does not print finding descriptions. A finding that has not finished evaluating is absent, so a zero count is **not** proof of compliance. The live 29 September snapshot had 76 passes and 19 failures; [security.md](../docs/security.md#aws-config-and-fsbp-findings) records the controls and exceptions. Re-run the reader while each later workload is live, before teardown.

## Residual inventory and retained costs

After [Ansible removes the alias and Ingress and waits for ALB deletion](../ansible/README.md#cleanup-before-terraform-destroy), review and apply the workload destroy plan. Then run `python3 scripts/check_residual.py --profile contact-form-deployer` from the assignment virtualenv with the reviewed [read-only evidence policy](../terraform/policies/README.md#read-only-demo-evidence-grant) effective through the provisioners group. The latest complete read reported no actionable named/tagged workload resources, no read errors and four project KMS keys pending deletion. Exit 0 means no **actionable** resources within the checker's declared Singapore names and tags; `PendingDeletion` workload KMS keys appear separately in `expected_pending_cleanup`. Exit 2 lists actionable remnants, including keys in other states. Exit 1 means an inventory read failed and cleanup is unproven. Resolve exit 1 or 2 before declaring the workload gone.

The checker looks for the named VPC, NAT gateways/EIPs, workers and relay, EKS cluster, RDS instance and snapshots, controller ALB, ECR repository and app secrets; it also checks retained `contact-form-postgres` automated backups, tagged EBS volumes/snapshots, and tagged workload KMS keys and deletion state. Worker/relay root-volume tags are specified in Terraform but have not been verified live. Untagged/manual EBS assets, other accounts/Regions, and resources outside the declared names and tags are outside the scan. Record root-volume IDs before destroy and inspect untagged resources separately if needed. A scoped exit 0 is **not** a zero-bill claim.

The state bucket and its local bootstrap state, Route 53 zone and domain, foundation evidence bucket, seven-day EKS/RDS log groups, certificate, and any project-owned Config, Security Hub or CloudTrail setup have separate lifecycles. Versioned state/evidence and service logs under `service-logs/alb/` may persist after workload destroy; optional security recording and checks can continue. Preserve unrelated account-wide controls. Before final foundation/bootstrap removal, the owner decides which DNS, state, audit evidence and security services to retain, checks actual billing and object versions, and reviews a separate plan and permissions. The [Terraform root notes](../terraform/README.md#foundation-stages) and [security evidence](../docs/security.md) cover their current ownership and verification. The state bucket and foundation stages 01–03 have been applied and verified in AWS; final retention decisions are pending owner review.
