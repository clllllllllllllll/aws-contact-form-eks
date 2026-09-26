# Terraform roots

The three roots have different lifecycles:

| Root | Status | Purpose |
| --- | --- | --- |
| `bootstrap/` | Applied and verified in account `203888389134` | Persistent encrypted, versioned S3 bucket for Terraform state and lockfiles |
| `foundation/` | Drafted and locally validated; not applied | Resources retained between workload teardown and redeployment |
| `workload/` | Drafted and locally validated; not applied | Disposable VPC, EKS, RDS, IAM, ECR, and application secret metadata |

Bootstrap's state is local at `bootstrap/terraform.tfstate` and excluded from Git. Preserve it securely. Foundation has a local S3 backend file and a drafted, locally validated resource configuration. It has not been applied or written a state object. Workload has a backend example and a locally validated resource draft. The two roots use different S3 keys.

The bootstrap plan reported `No changes` while the temporary bucket-setup policy was attached. That policy was then removed. To refresh or plan `terraform/bootstrap/` again, temporarily restore its setup/read permissions; the ongoing state-access policy alone only covers the foundation and workload S3 state objects and locks. Do not reapply or destroy bootstrap without reviewing the plan. Test the separate backend access using the ongoing state-access policy alone. Reattach the setup policy temporarily for deliberate bootstrap maintenance. Full state-bucket teardown also requires removing prevent_destroy and granting explicit deletion permissions after foundation and workload are gone.

The read-only runtime inventory policy draft at `bootstrap/runtime-inventory-policy.json` covers the AWS Describe/List calls used by `scripts/check_residual.py` in Singapore. It is not attached. The first inventory attempt failed on missing `ec2:DescribeVpcs`; this must be resolved before claiming that teardown is clean.

Review the actual Singapore cost and teardown plan separately before any foundation or workload apply.
