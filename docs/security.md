# Security hardening and AWS controls

**Scope:** AWS account `203888389134`, Region `ap-southeast-1`. Terraform configuration is in [foundation](../terraform/foundation/security.tf) and [workload](../terraform/workload/); Ansible and Kubernetes configuration is in [ansible](../ansible/). This report distinguishes configured controls from AWS results. It does **not** claim full FSBP compliance or CIS certification.

The live run verified two Ready workers in separate AZs, two Ready Flask pods, private encrypted Multi-AZ PostgreSQL, one HTTPS ALB, and a synthetic submission read back from PostgreSQL. A second Ansible deployment finished with `changed=0` and `failed=0`. After evidence capture, Ansible removed the public entry points. Terraform deleted the workload, but its first destroy stopped on two EIP disassociation permission errors; a fresh plan released both EIPs. Workload state is empty, and the scoped AWS inventory found no actionable resources or read errors. Four workload KMS keys are pending scheduled deletion. One-pass destroy was not demonstrated.

## Hardening status

| Area | Configured control | Live proof / remaining check |
| --- | --- | --- |
| Public entry | Ingress creates one public ALB; HTTP redirects to HTTPS using the ACM certificate. App pods stay on private workers. | Two Ready pods, Service, Ingress, one active public ALB, HTTPS certificate, two healthy targets, HTTP redirect and synthetic submission verified. |
| EKS management | Private-only API; workstation uses an authenticated SSM tunnel through a private relay without a public IP. One managed worker per AZ. | Private API, SSM tunnel and two Ready nodes in separate AZs verified. |
| Database and transport | Isolated private RDS subnets, encrypted Multi-AZ PostgreSQL 16, one-day backup retention; clients use `sslmode=verify-full` with the RDS CA. | Available PostgreSQL, Multi-AZ, encryption and no public access verified. The Ansible Job read back the matching synthetic row from RDS. |
| Secrets and IAM | RDS manages its master secret. A separate application secret holds the restricted SQL login; Flask IRSA can read only that app secret. Setup/readback use a separate role. No credential is hard-coded in source or manifests. | Both distinct secret **metadata** entries and the Flask ServiceAccount IRSA role verified. The app login's SQL privileges were not independently queried. Never display secret values. |
| Containers and RBAC | Flask runs as UID/GID 10001, without privilege escalation or Linux capabilities, with a read-only root filesystem, runtime-default seccomp and CPU/memory requests and limits. | Deployment pod settings and resource requests/limits verified. |
| Logging and foundation | Five EKS control-plane log types, RDS PostgreSQL/upgrade exports, seven-day log groups, Config recorder, FSBP v1.0.0, and a project management CloudTrail trail. State/evidence buckets use versioning, SSE-S3, public-access blocks and TLS-only policies. | Config recording `SUCCESS`, FSBP `READY`, CloudTrail logging, EKS log-group retention and recent EKS/RDS event delivery were checked. The project-filtered findings are below. A matching ALB access-log object was observed; this does not satisfy S3.9. |

**Documented exceptions:** The deployer has EKS cluster administrator access and direct IAM policy attachments for this short assignment. Worker security-group self-traffic and outbound `0.0.0.0/0` are broad; RDS port 5432 accepts the shared worker security group. TLS ends at the ALB, and the ALB-to-pod VPC hop uses HTTP. RDS and ALB deletion protection are disabled for ordered teardown of synthetic data. The readback Job uses the privileged setup role, while Flask uses the restricted app login. The relay is single-AZ and log retention is seven days. These are not claims of least privilege for a long-lived production deployment.

## AWS Config and FSBP findings

AWS Config recording and the AWS Foundational Security Best Practices **v1.0.0** subscription were verified in Singapore. During the live run, the [project-filtered findings reader](../scripts/show_findings.py) returned **95 active resource findings: 76 passed and 19 failed** at **14:23 SGT on 29 September 2026**. This is a point-in-time project snapshot, not an account-wide score or the post-teardown result. Passed workload controls include EKS.2/8/9, RDS.2/3/5/9/36 and ELB.5/12/13. Destroyed-workload findings may later be archived; that is not a pass. [AWS FSBP control definitions](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-controls-reference.html).

All 19 results below are genuine `FAILED` control findings. Some reflect a short-lived design choice or a key already pending deletion; those explanations do not turn a failure into a pass. No remediation has been verified.

| Failed control (findings) | What it means here | Disposition |
| --- | --- | --- |
| CloudTrail.2, CloudTrail.5 (2) | The project trail uses SSE-S3 rather than a KMS key and does not deliver to CloudWatch Logs. | Retained hardening gaps. |
| EC2.17 (2) | Two worker instances have multiple network interfaces. | EKS workload exception; no control remediation verified. |
| ECR.3 (1) | The disposable image repository has no lifecycle policy. | Unremediated gap. |
| ELB.6 (1) | ALB deletion protection is off. | Intentional for Ansible-led teardown. |
| IAM.2 (1) | The deployer has directly attached policies. | Scoped assignment access; temporary grants are removed after use. |
| KMS.3 (3) | Three keys from the earlier workload were pending deletion when the snapshot was taken. | Cleanup in progress; still failed findings. A fourth key from the latest teardown is now pending deletion. |
| RDS.6, RDS.8 (2) | Enhanced monitoring and deletion protection are off. | Disposable database exception; CloudWatch PostgreSQL logs are enabled separately. |
| RDS.10, RDS.11, RDS.23 (3) | IAM database authentication is off; backup retention is one day, below the control's seven-day threshold; PostgreSQL uses default port 5432. | App credentials are in Secrets Manager; data is synthetic and short-lived; port 5432 is restricted to workers. Controls remain failed. |
| S3.9, S3.13 (3) | Neither project bucket has server access logging; the state bucket lacks a noncurrent-version lifecycle rule. | Retained hardening gaps; ALB access logs are a separate feature. |
| SecretsManager.1 (1) | The application secret has no automatic rotation. | Short-lived secret; unremediated gap. |

The full read includes each resource and its `UpdatedAt` timestamp; the [summary screenshot](evidence/09-fsbp-findings.png) shows every failed control ID and count. Findings may lag resource changes. A missing or archived finding is not evidence of a pass. The retained CloudTrail, S3 and IAM gaps need separate reviewed changes.

## Live PNG evidence

The screenshots were captured on **29 September 2026** in account `203888389134`, Region `ap-southeast-1`. They use synthetic form data and metadata views only; no secret values, tokens or passwords are shown.

- [Private EKS and two AZs](evidence/01-eks-private-two-az.png) — Active cluster with public API disabled and two Ready workers in separate AZs.
- [Private Multi-AZ RDS](evidence/02-rds-private-multiaz.png) — Available PostgreSQL, encrypted, Multi-AZ and not publicly accessible.
- [Master and application secret metadata](evidence/03-secrets-metadata.png) — Active RDS-managed master secret and separate application secret entry; no values are shown.
- [Ansible deployment and Kubernetes resources](evidence/04-ansible-pods-ingress.png) — Successful Ansible recap and two Flask pods behind a ClusterIP Service and ALB Ingress.
- [ALB, HTTPS and healthy targets](evidence/05-alb-https-targets.png) — One internet-facing ALB, ACM certificate on port 443, two healthy targets, HTTP redirect and verified HTTPS response.
- [HTTPS form submission](evidence/06-https-form.png) — Public contact form returned “Message saved” for a synthetic submission.
- [PostgreSQL readback](evidence/07-postgres-readback.png) — `ansible/verify.yml` returned the matching synthetic name, email and message from private RDS.
- [Pod hardening, IRSA, Config and FSBP subscription](evidence/08a-pod-irsa-config.png) — Non-root runtime controls, resource limits, app IRSA role, successful Config recording and FSBP subscription.
- [Security groups and log delivery](evidence/08b-network-logs.png) — Relevant ingress rules and recent EKS/RDS log timestamps; worker self-traffic remains broad.
- [FSBP findings during the live run](evidence/09-fsbp-findings.png) — Project-filtered 76 passed and 19 failed resource findings, including the failed control IDs and counts.

The screenshot set is complete. The second Ansible deployment was idempotent (`changed=0`, `failed=0`). Workload cleanup required a second saved Terraform plan for two EIPs; one-pass teardown was not demonstrated.

The optional [foundation standby stage](../terraform/foundation/stages/04-standby-project-trail.tfvars) has not been applied. A separately reviewed plan may pause Config recording and Security Hub/FSBP while retaining DNS, certificate, buckets, logs and CloudTrail. Re-enable Config and FSBP before a later live demo and allow time for fresh findings.
