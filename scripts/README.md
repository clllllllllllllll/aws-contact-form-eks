# Workstation deployment helpers

These scripts are local deployment helpers. They are drafted and have not been exercised against the AWS workload.

| Script | Purpose |
| --- | --- |
| open_tunnel.py | Check the account, read Terraform outputs, write a TLS-verifying kubeconfig and start an SSM port forward to the private EKS API. |
| publish_image.py | Use the committed app tree as an immutable ECR tag, then return the image digest. A temporary Docker credential directory is removed after publishing. |
| manage_alb.py | Create/remove the Route 53 apex alias only for the tagged Ingress ALB, and block workload teardown while that ALB exists. |
| check_residual.py | Read-only Singapore inventory after workload teardown. Reports the named runtime resources, tagged EBS volumes/snapshots, retained RDS automated backups, and tagged workload KMS keys with deletion state. |

The scripts read resource identifiers and secret ARNs, not secret values. Run them through the Ansible playbooks where possible. Generated kubeconfig and the non-secret alias ownership record are stored under Git-ignored .local/.

Before use, check that the Session Manager plugin is installed in WSL, that the non-root AWS profile has the required permissions, and that the Terraform workload has been applied. The scripts do not replace the cost review or the Terraform plan.

For teardown inventory, run `python3 scripts/check_residual.py --profile contact-form-deployer` with current credentials and reviewed read permissions from `terraform/bootstrap/runtime-inventory-policy.json`. Exit 0 means no **actionable** resources were found within the checker's declared names and tags; `PendingDeletion` workload KMS keys appear separately in `expected_pending_cleanup`. Exit 2 lists actionable remnants, including keys in other states. Exit 1 means a read failed and cleanup is unproven. The policy draft is not attached or tested live. Untagged EBS resources are outside the scan; worker and relay root-volume tags are specified locally but not verified in AWS. A clean scoped result is not a zero-bill claim. Review [final cleanup](../docs/final-cleanup.md) for persistent foundation costs and ownership.
