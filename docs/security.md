# Security controls and evidence

**Status, 28 September 2026:** The Terraform state bucket and foundation stages 01–03 remain applied. AWS Config reported the `contact-form-recorder` recording with `SUCCESS`; CloudTrail reported logging without a delivery error; and the AWS Foundational Security Best Practices subscription reported `READY`. A complete disposable workload was deployed and tested: two Ready EKS workers in separate Availability Zones, a private encrypted Multi-AZ PostgreSQL RDS instance, two Ready Flask replicas, and one controller-created ALB. The HTTPS health check returned `200`; a synthetic form submission reached `/thanks`, and an in-cluster readback Job found its row in RDS. A second Ansible deployment finished with `changed=0`. Ansible then removed the application entry points, and Terraform destroyed the workload. State is empty. Direct regional reads show no project VPC, allocated Elastic IP, EKS cluster, RDS instance, ALB or tagged EBS volume; NAT gateways are `deleted` and worker/relay instances are `terminated`. Snapshot, backup, ECR, secret and Security Hub findings reads were denied, so complete residual-cost and findings audits remain open. No individual FSBP control is claimed as passed or remediated.

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
| State/evidence | Bootstrap state bucket: SSE-S3, versioning, public-access block, bucket-owner enforcement, TLS-only policy. Foundation evidence bucket was applied with analogous controls; versioned service logs have 30-day current and noncurrent expiry rules plus expired-marker cleanup | Direct S3 settings, [ALB log verification](#alb-access-log-verification), and Terraform drift check |

The ALB-to-pod connection is HTTP inside the VPC. The worker security group has a self-referencing all-protocol ingress rule for node/pod communication, plus port 8000 from the ALB; RDS accepts port 5432 from that same shared worker group. Security groups therefore limit traffic to these groups, but do not isolate Flask from every other workload on those nodes. SQL credentials and Kubernetes workload placement supply separate boundaries. EKS also creates a cluster security group; inspect all effective rules and pod ENIs live. Nodes have outbound `0.0.0.0/0` through NAT for ECR, AWS APIs and updates; this broad egress remains an exception. The controller's scoped inline policy removes security-group mutation actions, but needs live simulation and reconciliation. The local deployer has cluster administrator access for this short assignment, broader than a routine operator role.

## Deployment and cleanup evidence

The complete 28 September rehearsal used a private SSM tunnel to the EKS API. Kubernetes reported one Ready worker in each selected AZ and two Ready Flask pods. The public `https://cheelong.xyz/health/ready` endpoint returned `{"status":"ok"}` through the ALB with certificate validation; the workstation DNS cache was stale, so the check connected through the ALB hostname while retaining the public domain for TLS verification. A browser-style POST with a session cookie, CSRF token and same-origin referrer returned `200` at `/thanks`. The private readback Job returned row `id=1` for `demo@example.com`. No real customer data was used. A local, ignored verification note records the command results.

Ansible removed the Route 53 alias and Ingress, waited for the controller to delete the ALB, and then removed the controller and application namespace. Terraform's first destroy applied all but two EIP deletions: the caller lacked `ec2:DisassociateAddress`. AWS had already disassociated both addresses when the NAT gateways were deleted. A fresh saved plan containing exactly those two EIP deletions released them, leaving no managed workload resources in Terraform state. Direct AWS reads confirmed the principal runtime resources are absent or terminated. The customer-managed EKS KMS key is `PendingDeletion`, scheduled for 5 October 2026. The state bucket and foundation services remain intentionally deployed.

### Earlier partial deployment

On 28 September, the first workload was destroyed before any node group, Flask pod or ALB was created. Terraform's deletion waiters lost read access late in EKS add-on and cluster deletion. Obsolete state entries were removed after the add-on list became empty and the cluster's network interfaces were absent; the project VPC was subsequently deleted. Both NAT gateways were deleted. Their Elastic IPs became unassociated and were released by exact allocation ID after Terraform's release path was denied `ec2:DisassociateAddress`.

The workload state now lists no managed resources. Direct regional reads returned empty project inventories for VPCs, active NAT gateways, Elastic IPs, active EC2 instances, tagged EBS volumes, RDS instances and ALBs. The workload KMS key is `PendingDeletion`, scheduled for 5 October 2026. The full residual checker stopped at a denied `ec2:DescribeSnapshots` call; RDS automated-backup and Secrets Manager inventory reads were also denied. These gaps require a temporary read-only inventory grant or an equivalent account-level check before claiming complete cleanup or a zero-charge account. The retained state bucket, DNS, logs, Config, CloudTrail and Security Hub are separate from workload teardown.

## Foundational controls

The foundation has three required flags for certificate, security-service, and project-CloudTrail creation; none has a Terraform default. The initial [stage file](../terraform/foundation/stages/01-base.tfvars) explicitly sets all three to false, and later stage files set them only after the relevant ownership, delegation, and cost checks. Omitting a stage file with `plan -input=false` fails instead of silently selecting account-wide ownership. Before enabling Config, Security Hub Foundational Security Best Practices (FSBP), or a project CloudTrail, inventory existing services in Singapore and review the [cost gate](../README.md#prerequisites-and-cost-gate). The intended FSBP subscription is version 1.0.0; this is not a claim of CIS certification. If account-wide services already exist, reuse them instead of creating a duplicate recorder or trail.

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

The Ingress requests ALB access logs in the retained evidence bucket under `service-logs/alb/`. The ALB ran during the complete rehearsal, but a post-teardown listing was denied because `contact-form-deployer` lacks `s3:ListBucket` on the evidence bucket. Log-object delivery therefore remains unverified. The bucket uses SSE-S3, public-access blocks, and a TLS-only policy. The log-delivery service can write only to the account path under that prefix from load balancers in the intended account and Region. [AWS access-log setup](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/enable-access-logging.html).

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
| FSBP subscription | `READY` in ap-southeast-1 before the full rehearsal | No subscription change required | Individual control status not verified |
| AWS Config rule compliance | Recorder reported `SUCCESS`; `config:DescribeComplianceByConfigRule` was denied to `contact-form-deployer` on 28 September | Obtain a scoped read grant or account-level screenshot and record dated rule results | Pending |
| Workload findings | `securityhub:GetFindings` denied to `contact-form-deployer` on 28 September; no project finding captured | Obtain a scoped read grant or account-level screenshot, then record dated control IDs and statuses during the next deployment | Pending |
| ALB access logs | `s3:ListBucket` on the retained evidence bucket was denied after teardown; log delivery was not confirmed | Obtain a scoped bucket-list grant, then inspect object metadata for the rehearsal window | Pending |
| RDS.8 deletion protection | Terraform disabled deletion protection for the disposable database; no Security Hub finding was read | Keep the short-lived demo exception documented and compare it with the actual finding | Pending |

Do not replace the pending row with guessed results. Findings elsewhere in the account must be attributed to their actual resources and owners, rather than claimed as project results.

## Evidence screenshots

Add dated, redacted screenshots from the live deployment under `docs/evidence/` and embed them here after verifying the matching AWS account, Region and resource. Useful views include the private EKS endpoint and worker placement, private encrypted Multi-AZ RDS settings, HTTPS ALB listener and healthy targets, and actual Security Hub FSBP findings. No screenshots have been captured yet. Hide secret values, personal data and unrelated account resources before committing images.

## Known design exceptions to confirm live

| Control or practice | Reason and scope | Follow-up |
| --- | --- | --- |
| RDS.8 deletion protection | Disabled on the disposable demo RDS instance to permit a rehearsed `terraform destroy`; the database contains synthetic data only and has one-day automated backups while running | Expect a failed RDS.8 finding if evaluated. Record the actual finding ID/status. Enable deletion protection and retain final backups before any long-lived or real-data use. |
| ALB-to-pod TLS | HTTP only on the restricted VPC hop | Use pod-side TLS or another approved encryption pattern for a long-lived environment. |
| Broad node egress | Private workers require several AWS/public endpoints through same-AZ NAT | Scope egress or add appropriate VPC endpoints if the stack becomes long-lived; price endpoints first. |
| Seven-day audit-log retention | Short assignment and cost control | Increase to the organization's retention requirement for real operations. |
| Privileged database readback Job | Short-lived Job uses the setup role to show one synthetic row in the live demo; Flask remains INSERT-only | Use a dedicated read-only SQL identity for long-lived operational querying. |
| Availability of management relay | One private relay in one AZ; failure interrupts management, not serving | Add a second relay or managed access solution if required. |

All exceptions are limited to this short-lived assignment and need to be compared with actual Security Hub findings. The read-only teardown inventory reports owned EBS volumes/snapshots, retained RDS backups, and workload KMS keys. Keys in `PendingDeletion` are shown as expected pending cleanup; other key states remain actionable. A denied read is inconclusive; exit 0 covers only the names and tags the checker declares. Worker and relay root-volume tags are now specified locally but need live verification. See [final cleanup](../README.md#final-cleanup-of-retained-resources) for retained foundation and cost decisions.
