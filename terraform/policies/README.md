# Operator IAM policy drafts

These JSON files are drafts for manual IAM review, tailoring, validation and attachment. They are not Terraform-managed IAM resources; bootstrap Terraform does not load them. Tracking a draft does not establish effective permissions.

- `bootstrap/`: state-bucket setup and state access.
- `foundation/`: inventory and foundation service drafts.
- `workload/`: IAM provisioning, role writes and workload service drafts.
- `workstation/`: preflight, residual inventory and deployment helper drafts.

The trimmed `workstation/preflight-read-policy.json` was attached to the deployer and successfully read the Singapore EC2 Standard vCPU quota. The applied quota is 5; an increase to 8 is pending. Recheck the quota and effective permissions before any paid provisioning.
