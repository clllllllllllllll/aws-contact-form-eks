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
| Audit | Foundation-owned EKS control-plane and RDS PostgreSQL/upgrade log groups with seven-day retention; optional project CloudTrail if existing coverage is insufficient | Log-group retention and recent delivery, trail inventory; do not claim log coverage until events arrive |
| State/evidence | Bootstrap state bucket: SSE-S3, versioning, public-access block, bucket-owner enforcement, TLS-only policy. Foundation evidence bucket is drafted with analogous controls; versioned service logs have 30-day current and noncurrent expiry rules plus expired-marker cleanup | Direct S3 settings, [ALB log verification](#alb-access-log-verification), and Terraform drift check |

The ALB-to-pod connection is HTTP inside the VPC. The worker security group has a self-referencing all-protocol ingress rule for node/pod communication, plus port 8000 from the ALB; RDS accepts port 5432 from that same shared worker group. Security groups therefore limit traffic to these groups, but do not isolate Flask from every other workload on those nodes. SQL credentials and Kubernetes workload placement supply separate boundaries. EKS also creates a cluster security group; inspect all effective rules and pod ENIs live. Nodes have outbound `0.0.0.0/0` through NAT for ECR, AWS APIs and updates; this broad egress remains an exception. The controller's scoped inline policy removes security-group mutation actions, but needs live simulation and reconciliation. The local deployer has cluster administrator access for this short assignment, broader than a routine operator role.

## Foundational controls

The foundation has three required flags for certificate, security-service, and project-CloudTrail creation; none has a Terraform default. The initial [stage file](../terraform/foundation/stages/01-base.tfvars) explicitly sets all three to false, and later stage files set them only after the relevant ownership, delegation, and cost checks. Omitting a stage file with `plan -input=false` fails instead of silently selecting account-wide ownership. Before enabling Config, Security Hub Foundational Security Best Practices (FSBP), or a project CloudTrail, inventory existing services in Singapore and review [costs](cost.md). The intended FSBP subscription is version 1.0.0; this is not a claim of CIS certification. If account-wide services already exist, reuse them instead of creating a duplicate recorder or trail.

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

## ALB access log verification

The Ingress requests ALB access logs in the retained evidence bucket under `service-logs/alb/`. This is a local configuration draft; delivery is unverified until the ALB runs after cost approval. The bucket uses SSE-S3, public-access blocks, and a TLS-only policy. The log-delivery service can write only to the account path under that prefix from load balancers in the intended account and Region. [AWS access-log setup](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/enable-access-logging.html).

After sending only synthetic requests through the live HTTPS site, allow for delivery delay and list object metadata:

```bash
export AWS_PROFILE=contact-form-deployer
ALB_LOG_BUCKET="$(terraform -chdir=terraform/foundation output -raw alb_access_log_bucket_name)"
aws s3api list-objects-v2 --profile "$AWS_PROFILE" --region ap-southeast-1 --bucket "$ALB_LOG_BUCKET" --prefix service-logs/alb/AWSLogs/203888389134/elasticloadbalancing/ap-southeast-1/ --query 'Contents[].[Key,LastModified,Size]' --output table
```

Record the first recent `.log.gz` key and its `LastModified`, and match its `app.<load-balancer-id>` segment to the deployed ALB. `ELBAccessLogTestFile` confirms bucket permissions only; it is not an access log. Access logs can include client IPs and URLs, so do not retrieve or share log bodies or use real submissions for this check. [AWS access-log file format](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-access-logs.html).

The `service-logs/` lifecycle rule expires current versions after 30 days and noncurrent versions 30 days after they become noncurrent. In a versioned bucket, a current-version expiration creates a delete marker, so old object versions can remain beyond 30 days total; a separate rule removes expired markers once no versions remain.

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
