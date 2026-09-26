# Security controls and evidence

**Status, 27 September 2026:** Only the Terraform state bucket has been applied and directly verified. The controls below describe the intended runtime configuration and how to test it. Foundation security services, EKS, RDS, and the ALB have not been deployed. No Security Hub finding is recorded as passed, failed, or remediated without a dated AWS result.

## Access and data paths

| Boundary | Configured design | Evidence to capture after deployment |
| --- | --- | --- |
| Public entry | One controller-created ALB in public subnets; ports 80 (redirect) and 443; ACM certificate and TLS 1.2/1.3 policy | ALB listeners, certificate, public subnet IDs, healthy targets, `curl -I https://cheelong.xyz/health/ready` |
| Kubernetes API | Private EKS endpoint. The workstation enters through an authenticated SSM tunnel and a private relay with no public IP or inbound port | EKS endpoint settings, relay network interface, relay security group, successful TLS-verifying `kubectl get nodes` |
| Application | Two Flask pods on private nodes in separate AZs. The worker security group allows port 8000 from the ALB security group and all traffic from itself, so ALB access is not the only possible source inside the worker group | Node labels, pod placements, pod ENI security groups, and live worker/ALB ingress rules |
| Database | RDS in isolated subnets, no public address, Multi-AZ, encrypted storage. Port 5432 accepts the shared worker security group; it is not restricted to the Flask pods alone | RDS settings, subnet routes, DB ingress rule, pod/instance security-group membership and SQL permissions |
| Database transport | PostgreSQL 16 defaults `rds.force_ssl=1`; app, setup, and readback clients use `sslmode=verify-full` with the RDS CA bundle | RDS parameter value and a successful verified client connection; [RDS TLS documentation](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html) |
| Secrets | RDS manages the master secret. A separate app secret holds a restricted SQL credential. Flask's service-account IAM role reads only the app secret; setup/readback jobs use a separate master-secret role | Secret metadata only, IAM policy/trust inspection, app-role denial against the master secret; never print secret values |
| Container | UID/GID 10001, read-only root filesystem, no privilege escalation, dropped Linux capabilities, runtime-default seccomp, CPU/memory requests and limits | Live pod security context and image user |
| Audit | Five EKS control-plane log types and PostgreSQL/upgrade logs with seven-day retention; optional project CloudTrail if existing coverage is insufficient | Log-group retention and recent delivery, trail inventory; do not claim log coverage until events arrive |
| State/evidence | State bucket: SSE-S3, versioning, public-access block, bucket-owner enforcement, TLS-only policy. Foundation evidence bucket is drafted with analogous controls and 30-day expiry for service logs | Direct S3 settings and Terraform drift check |

The ALB-to-pod connection is HTTP inside the VPC. The worker security group has a self-referencing all-protocol ingress rule for node/pod communication, plus port 8000 from the ALB; RDS accepts port 5432 from that same shared worker group. Security groups therefore limit traffic to these groups, but do not isolate Flask from every other workload on those nodes. SQL credentials and Kubernetes workload placement supply separate boundaries. EKS also creates a cluster security group; inspect all effective rules and pod ENIs live. Nodes have outbound `0.0.0.0/0` through NAT for ECR, AWS APIs and updates; this broad egress remains an exception. The controller's scoped inline policy removes security-group mutation actions, but needs live simulation and reconciliation. The local deployer has cluster administrator access for this short assignment, broader than a routine operator role.

## Foundational controls

The foundation has opt-in Terraform switches for AWS Config recording and AWS Security Hub Foundational Security Best Practices (FSBP). They default off to avoid taking over an existing account-wide recorder or incurring unreviewed charges. Before enabling them, inventory existing Config, Security Hub and CloudTrail resources in Singapore and review [costs](cost.md). The intended subscription is FSBP version 1.0.0; this is not a claim of CIS certification. If account-wide services already exist, reuse them instead of creating a duplicate recorder or trail.

Relevant FSBP checks include private RDS access (RDS.2), encryption at rest (RDS.3), Multi-AZ (RDS.5), deletion protection (RDS.8), published logs (RDS.9/RDS.36), backups (RDS.11), and PostgreSQL transport encryption (RDS.38). [AWS control definitions](https://docs.aws.amazon.com/securityhub/latest/userguide/rds-controls.html). The draft exports PostgreSQL and upgrade logs to CloudWatch. These controls can report `NO_DATA` or pending results until evaluation; neither means pass.

### Evidence capture after paid deployment

Run from the workstation with the intended non-root profile. Commands below read metadata, not secret values:

```bash
export AWS_PROFILE=contact-form-deployer
aws sts get-caller-identity --profile "$AWS_PROFILE"
aws configservice describe-configuration-recorders --region ap-southeast-1
aws configservice describe-configuration-recorder-status --region ap-southeast-1
aws securityhub get-enabled-standards --region ap-southeast-1
aws securityhub get-findings --region ap-southeast-1 --filters '{"RecordState":[{"Value":"ACTIVE","Comparison":"EQUALS"}]}' --query 'Findings[].{id:Id,control:Compliance.SecurityControlId,status:Compliance.Status,resource:Resources[0].Id,updated:UpdatedAt}'
aws eks describe-cluster --region ap-southeast-1 --name contact-form-eks --query 'cluster.{public:resourcesVpcConfig.endpointPublicAccess,private:resourcesVpcConfig.endpointPrivateAccess,logging:logging.clusterLogging}'
aws rds describe-db-instances --region ap-southeast-1 --db-instance-identifier contact-form-postgres --query 'DBInstances[0].{public:PubliclyAccessible,multiAZ:MultiAZ,encrypted:StorageEncrypted,backupDays:BackupRetentionPeriod,logs:EnabledCloudwatchLogsExports,deletionProtection:DeletionProtection}'
aws logs describe-log-groups --region ap-southeast-1 --log-group-name-prefix /aws/rds/instance/contact-form-postgres/
```

Record the command time, account, Region, control ID, resource ID, status and finding `UpdatedAt`. Redact any customer data from saved evidence. Re-run the same query after remediation; a Terraform setting alone is not proof that Security Hub evaluated it.

## Findings register

| Control / resource | Observed status and time | Remediation | Retest status and time |
| --- | --- | --- | --- |
| Pending first deployment | Not evaluated | Capture actual Singapore findings after Config and FSBP run | Pending |

Do not replace the pending row with guessed results. Findings elsewhere in the account must be attributed to their actual resources and owners, rather than claimed as project results.

## Known design exceptions to confirm live

| Control or practice | Reason and scope | Follow-up |
| --- | --- | --- |
| RDS.8 deletion protection | Disabled on the disposable demo RDS instance to permit a rehearsed `terraform destroy`; the database contains synthetic data only and has one-day automated backups while running | Expect a failed RDS.8 finding if evaluated. Record the actual finding ID/status. Enable deletion protection and retain final backups before any long-lived or real-data use. |
| ALB-to-pod TLS | HTTP only on the restricted VPC hop | Use pod-side TLS or another approved encryption pattern for a long-lived environment. |
| Broad node egress | Private workers require several AWS/public endpoints through same-AZ NAT | Scope egress or add appropriate VPC endpoints if the stack becomes long-lived; price endpoints first. |
| Seven-day audit-log retention | Short assignment and cost control | Increase to the organization's retention requirement for real operations. |
| Privileged database readback Job | Short-lived Job uses the setup role to show one synthetic row in the live demo; Flask remains INSERT-only | Use a dedicated read-only SQL identity for long-lived operational querying. |
| Availability of management relay | One private relay in one AZ; failure interrupts management, not serving | Add a second relay or managed access solution if required. |

All exceptions are limited to this short-lived assignment and need to be compared with actual Security Hub findings. The read-only teardown inventory reports owned EBS volumes/snapshots, retained RDS backups, and workload KMS keys. Keys in `PendingDeletion` are shown as expected pending cleanup; other key states remain actionable. A denied read is inconclusive; exit 0 covers only the names and tags the checker declares. Worker and relay root-volume tags are now specified locally but need live verification. See [final cleanup](final-cleanup.md) for retained foundation and cost decisions.
