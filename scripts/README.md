# Workstation deployment helpers

These scripts are local deployment helpers. They are drafted and have not been exercised against the AWS workload.

| Script | Purpose |
| --- | --- |
| open_tunnel.py | Check the account, read Terraform outputs, write a TLS-verifying kubeconfig and start an SSM port forward to the private EKS API. |
| publish_image.py | Use the committed app tree as an immutable ECR tag, then return the image digest. A temporary Docker credential directory is removed after publishing. |
| manage_alb.py | Create/remove the Route 53 apex alias only for the tagged Ingress ALB, and block workload teardown while that ALB exists. |

The scripts read resource identifiers and secret ARNs, not secret values. Run them through the Ansible playbooks where possible. Generated kubeconfig and the non-secret alias ownership record are stored under Git-ignored .local/.

Before use, check that the Session Manager plugin is installed in WSL, that the non-root AWS profile has the required permissions, and that the Terraform workload has been applied. The scripts do not replace the cost review or the Terraform plan.
