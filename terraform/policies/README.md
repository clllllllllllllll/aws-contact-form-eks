# Operator IAM policy drafts

These JSON files are manual IAM policy sources; they are not Terraform-managed IAM resources, and bootstrap Terraform does not load them. Tracking a file alone does not establish effective permissions. The stage 01 foundation policy was published and attached for its approved 27 September 2026 apply; later policy drafts still need their own review and attachment windows.

- `bootstrap/`: state-bucket setup and state access.
- `foundation/`: inventory and foundation service drafts.
- `workload/`: IAM provisioning, role writes and workload service drafts.
- `workstation/`: preflight, residual inventory and deployment helper drafts.

The [stage 01 foundation policy source](foundation/deployer-foundation-stage-01.json) combines only the DNS, exact evidence-bucket and three named log-group permissions for `01-base.tfvars` (all three feature flags false). Customer-managed `ContactFormFoundationStage01` was attached for the approved stage. After a partial apply failure, it was updated to include `logs:TagLogGroup` alongside the existing `logs:TagResource`; a fresh plan showed three additions only and the apply succeeded with three added. Stage 01 now has 11 foundation resources in remote state. Confirm whether this temporary policy remains attached and detach it after the completed window. Later foundation stages require separately reviewed refresh + apply drafts. State-backend access is separate.

The trimmed `workstation/preflight-read-policy.json` was attached to the deployer and successfully read the Singapore EC2 Standard On-Demand vCPU quota by CLI. The effective quota is 8 vCPUs. Recheck the quota and effective permissions before any further paid provisioning.
