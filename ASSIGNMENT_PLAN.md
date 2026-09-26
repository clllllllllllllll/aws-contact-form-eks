# AWS Contact Form on EKS — Implementation Plan

**Status (27 September 2026):** The application and container were verified locally, and the S3 state bucket was applied and verified in AWS. Three local code checkpoints for setup Job recovery, retained RDS logs, and ALB access logging passed review; the combined workstation/helper suite passed 30 offline tests. Foundation and workload Terraform, Ansible, read-only preflight, and cleanup remain local drafts; none has been applied to the workload account. This project has not provisioned EKS, RDS, NAT gateways, an ALB, or an AWS application deployment; account-wide inventory remains unverified. Current AWS login is expired and Docker is unavailable in WSL.

**Objective:** Deploy a Flask contact form accepting name, email and message, with persistence in RDS PostgreSQL. Provision AWS infrastructure through Terraform and deploy the application through Ansible, entirely from the local workstation. Application infrastructure is provisioned from the workstation, not manually in the AWS Console. Initial IAM access policies were attached in the Console as an account prerequisite.

**Official deadline:** Tuesday 29 September 2026, 18:00 Singapore time. **Personal target:** Sunday 27 September 2026, 23:59, with a 20:00 internal aim for fixes. The personal target is at risk while AWS login, Docker, permissions, pricing approval, deployment and rehearsal remain open.

## 1. Resume context

- Repository: https://github.com/clllllllllllllll/aws-contact-form-eks
- Verified laptop checkout: `/home/limch/projects/aws-contact-form-eks` in WSL Ubuntu; branch `main`, tracking `origin/main`. Independently verify the PC checkout.
- Primary development: PC. Possible live demo: laptop. Use the same Git revision and pinned tool versions; complete a full laptop rehearsal.
- Use AWS account **`203888389134`** in **Singapore, `ap-southeast-1`**.
- PC WSL CLI identity was verified as `arn:aws:iam::203888389134:user/contact-form-deployer` in `ap-southeast-1`. Recheck the profile before future applies and separately verify the laptop.
- Before changing anything in AWS, confirm that the login is non-root, belongs to the intended account and has the required permissions.
- Work through phases in order and mark tasks complete only after verification. Record completed work, evidence, blockers, and the next action in section 6.

## 2. Confirmed architecture

Deploy across two Availability Zones (AZs) in Singapore.

| Component | Required design |
|---|---|
| VPC and subnets | One AWS network across two AZs. ALB and NAT gateways use public subnets; workers use private subnets; RDS uses isolated database subnets. |
| EKS workers | Two managed node groups, each restricted to one AZ with one desired worker: one worker per AZ in steady state. |
| Flask | Two Flask/Gunicorn replicas: one on each worker, enforced through Kubernetes placement rules. |
| ALB | The public entrance to the website. It sends requests to healthy Flask replicas through a Kubernetes Ingress and ClusterIP Service, using IP targets. |
| EKS management | A private-only Kubernetes API. Ansible on the PC or laptop reaches it through an authenticated Systems Manager tunnel and a small private EC2 relay. |
| NAT gateways | One per AZ. Each worker subnet uses its own AZ's gateway to reach ECR, Secrets Manager and other required public endpoints. |
| PostgreSQL | RDS Multi-AZ, with a primary database and a synchronized standby in the other AZ. Use encryption, backups and verified TLS connections. |
| Credentials | Secrets Manager stores the credentials. Flask gets its own restricted database user and permission to read only its application secret. |
| Container images | Private ECR repository; deploy immutable image digests for reproducibility. |
| HTTPS | Use the purchased cheelong.xyz domain registered through Exabytes; verify registrar delegation to Route 53, then attach a free non-exportable ACM public certificate from Singapore to the ALB. Redirect HTTP to HTTPS. |
| Security checks | Enable AWS Config and Security Hub's AWS Foundational Security Best Practices (FSBP) standard. Record findings, fixes and remaining exceptions. |

**Evaluator clarification:** creating the Ingress triggers ALB creation. Terraform creates the network and IAM prerequisites. Ansible installs the AWS Load Balancer Controller and applies the Ingress. The controller owns the ALB, listeners and target groups; Terraform must not create a second ALB.

**Traffic paths:**

```text
Visitors:
Browser → HTTPS ALB → private Flask replica → TLS → private RDS

Deployment:
Local Ansible/kubectl → Systems Manager tunnel → private relay → private EKS API

Outbound access:
Private worker or pod → NAT in the same AZ → required public service endpoint
```

Only the ALB accepts public inbound application traffic. The relay has no public IP or inbound SSH port. NAT is not needed between ALB and Flask, or between Flask and RDS.

The ALB-to-Flask connection will use HTTP within the VPC, restricted by security groups. Document this clearly: browser-to-ALB and Flask-to-RDS are encrypted, but this internal connection is not.

Availability rationale: separate managed node groups enforce one worker per AZ; spread Flask replicas preserve application capacity after an AZ failure; Multi-AZ RDS provides database failover; one NAT gateway per AZ preserves outbound access in the surviving AZ. RDS failover still causes a temporary interruption, so Flask must reconnect successfully. Losing the single relay affects management access, not the running website.

## 3. Budget and resource lifecycle

**Budget:** approximately US$140 AWS credits; initial usage target US$10 drawn from those credits. The Singapore cost document is an unapproved planning estimate. Verify current calculator pricing and credit eligibility/expiry before paid deployment. Keep paid runtime under ten hours total across provisioning, deletion, setup, rehearsal and demo.

**Domain:** `cheelong.xyz` was registered through Exabytes. Registrar nameserver delegation to the planned Route 53 hosted zone is still pending; do not claim DNS or HTTPS works yet.

Destroy runtime infrastructure between work sessions. **Every full rebuild creates a new, empty RDS database.** Submissions are disposable demo data and are intentionally deleted with RDS. They must still survive pod restarts and application redeployments while that database exists. This replaces the earlier requirement to retain submissions across teardown.

| Keep between sessions | Rebuild each time |
|---|---|
| Domain and DNS zone | VPC, NAT gateways and relay |
| Encrypted, versioned S3 Terraform state with locking | EKS cluster, workers and application |
| Security evidence and required retained logs | Fresh Multi-AZ RDS database and newly generated application credentials |
| Foundation resources needed for state/evidence encryption | ECR repository, published image and other runtime resources |

Enable automated RDS backups while the instance runs. For deliberate demo teardown, skip the final snapshot and delete automated backups; do not implement snapshot restoration or retain database recovery metadata. Configure database deletion protection for this teardown workflow and document the demo-specific exception. Never use real personal data for the demo.

Use separate Terraform configurations and state for the persistent foundation and the running environment. Create the state backend through Terraform from the workstation, and preserve the bootstrap state safely.

Inspect existing account security services before assigning Terraform ownership and teardown behaviour. Preserve unrelated resources.

DNS, state, retained logs and evidence storage may still cost money after teardown. Include them in the estimate.

## 4. Implementation phases

The phases below are the implementation sequence, not dated evidence or a promise of available AWS runtime. Section 6 records actual status. Track all paid workload runtime against the single less-than-ten-hour total.

**Next live milestone:** a submission through the ALB is stored in RDS.

**Completion milestone:** security evidence, successful teardown/fresh rebuild, complete deliverables and laptop rehearsal.

### Phase 0 — Access and workstation checks

- [x] Check the PC's repository, Git status and local repository instructions.
- [ ] Verify non-root AWS access to the correct account. Set up authorized access on the laptop too; keep credentials out of Git.
- [ ] Check Docker, AWS CLI, Session Manager plugin, Terraform, Ansible, kubectl, Helm, Python and required Ansible collections. Pin compatible versions.
- [ ] Check Singapore service versions, permissions, quotas, costs and credits. Inspect any existing Config, Security Hub and CloudTrail setup.
- [x] Choose and purchase `cheelong.xyz` through Exabytes.
- [ ] Verify registrar nameserver delegation to Route 53 and document the live result.

**Acceptance:** the tools work and the correct non-root AWS identity is confirmed. If AWS access is blocked, continue only with local development.

### Phase 1 — Application and local tests

- [x] Build the form and confirmation page. Validate email and field lengths, add CSRF protection, use parameterized SQL and return safe error messages.
- [x] Add a liveness check for the running application and a readiness check that includes database connectivity. A database outage should not cause endless container restarts.
- [x] Build a non-root Gunicorn container with pinned dependencies and the RDS certificate bundle.
- [ ] Verify the drafted Boto3 application-secret read through its service-account IAM role in live EKS. Keep the shared signing secret secure and test database reconnections there.
- [x] Test valid and invalid submissions, saved rows, database errors and non-root startup against local PostgreSQL. Avoid logging passwords or submitted personal information.

**Acceptance:** a local submission is saved and the focused tests pass.

### Phase 2 — Terraform infrastructure

- [x] Create and verify the persistent S3 state bucket.
- [ ] Create DNS and evidence resources. Create the empty application secret as part of the disposable runtime environment.
- [ ] Create the network, two NAT gateways, private EKS API, two managed node groups, EKS core add-ons, relay, ECR and Multi-AZ RDS.
- [ ] Guard against deploying to the wrong account or region. Give the controller, database setup Job, Flask and deployment identities only their required permissions.
- [ ] Let RDS generate and manage the master password. Pass secret identifiers (ARNs) through Terraform, keeping actual passwords out of Terraform inputs, outputs and state.
- [ ] Configure restrictive security groups, encryption, RDS backups, EKS control-plane logs, ECR scanning and appropriate access/audit logging. Open no inbound management ports on the relay.
- [ ] Enable Config recording and FSBP early. Configure the supporting CloudTrail resources needed for the selected controls, respecting any existing setup.
- [ ] Create the Route 53 hosted zone, configure registrar delegation, then request and DNS-validate the ACM certificate. Provide non-secret Terraform outputs for Ansible.
- [ ] Apply Terraform and test the local tunnel to EKS. Keep certificate and hostname verification enabled.
- [ ] Configure disposable RDS/secret lifecycles and prepare the ordered teardown workflow before the first destroy. Phase 5 validates the full rebuild.

**Acceptance:** the infrastructure exists and the workstation can reach the private EKS API.

### Phase 3 — Ansible deployment

- [ ] Automate building and pushing the image from the workstation. Read Terraform outputs automatically instead of copying IDs by hand.
- [ ] Install the pinned AWS Load Balancer Controller with Helm. Manage the namespace, service accounts, Kubernetes RBAC and manifests through Ansible.
- [ ] Run a database setup Job using the master secret. On a fresh build, generate application credentials and create the table and restricted database user. On reruns against the same database, reuse credentials and preserve existing rows.
- [ ] Give Flask access only to its own secret and required database operations. It should not need schema-changing or unnecessary Kubernetes permissions.
- [ ] Deploy two replicas, one per worker/AZ, with health checks, CPU/memory requests and limits, non-root execution, no privilege escalation, dropped capabilities and a read-only filesystem where compatible.
- [ ] Apply the Service and HTTPS Ingress, wait for the ALB and healthy targets, then create the application's DNS alias through Ansible.

Each resource must have one owner. Repeating Ansible against an existing environment must reuse credentials and preserve data; rebuilding after a full destroy intentionally starts empty.

**Acceptance:** the HTTPS website accepts a submission and stores it in RDS.

### Phase 4 — Functional and security verification

- [ ] Submit a recognizable test message and show its database row through a controlled query from inside the VPC.
- [ ] Check that only the ALB accepts public inbound traffic. Verify private EKS access, RDS certificate verification, secret permissions, RBAC, logs and container settings.
- [ ] Inspect node AZ labels and pod placement: one worker in each AZ and one Flask replica on each worker.
- [ ] Replace an application pod and confirm the submission remains. Test recovery of database connections.
- [ ] Rerun Terraform plan and Ansible. Check for unexpected changes, duplicate resources, password resets or lost data.
- [ ] Export timestamped FSBP findings. Fix issues within scope and explain remaining findings or account prerequisites. A check awaiting evaluation is not a pass.

**Acceptance:** the application works, the agreed layout is verified and security evidence is saved.

### Phase 5 — Teardown and fresh rebuild

- [ ] Exercise the local teardown workflow prepared before the first destroy: stop new submissions, finish pending requests and remove the application DNS alias and Ingress.
- [ ] Wait for the controller to delete its ALB resources before destroying EKS and the network.
- [ ] Destroy runtime resources, including RDS and its application credentials. Preserve only the declared foundation resources and security evidence.
- [ ] Handle non-empty ECR cleanup and Secrets Manager deletion timing so rebuilding does not fail on retained resource names.
- [ ] Run a fresh Terraform apply, republish the image and run Ansible using the new resource outputs. Initialize a new database, table and application user.
- [ ] Verify that the previous test submission is absent, submit a new message and prove it is stored. Check for orphaned billable resources after teardown.

**Acceptance:** a complete destroy/rebuild starts with an empty database, accepts new submissions and requires no manual Console repairs.

### Phase 6 — Documentation and laptop rehearsal

- [ ] Finish the deliverables below, including exact setup, deployment, teardown and fresh-rebuild commands.
- [ ] On the laptop, verify AWS identity, use the same code/tool versions and rehearse the complete teardown and fresh deployment.
- [ ] Save security findings from rehearsal. Newly enabled Security Hub controls can take time to produce results; label evidence with its actual date.
- [ ] Check Git history and tracked files for credentials, Terraform state, private keys, generated kubeconfig or sensitive evidence.
- [ ] Finish by Sunday 20:00 Singapore time and use the remaining buffer for required fixes.

**Acceptance:** the laptop can reproduce the deployment and every demo requirement has a clear step.

## 5. Deliverables and live demo

Suggested folders: `app/`, `terraform/bootstrap/`, `terraform/foundation/`, `terraform/workload/`, `ansible/`, `scripts/` and `docs/`.

- [ ] Terraform code.
- [ ] Ansible playbooks and roles.
- [x] Flask source, tests and container build, verified locally.
- [ ] Kubernetes manifests/templates and Helm configuration.
- [ ] Architecture diagram showing both AZs, public/private traffic, secrets and workstation access.
- [ ] README covering prerequisites, deployment, verification, troubleshooting, teardown and fresh rebuild; state explicitly that destroying RDS deletes demo submissions.
- [ ] Security-hardening document explaining the controls and limitations.
- [ ] FSBP configuration, findings, fixes and remaining exceptions.
- [ ] Clean Git history with meaningful commits and no secrets.

Execute the live demo from the local workstation:

1. Show the AWS identity and bootstrap any missing declared prerequisites.
2. Run a fresh Terraform apply and show the EKS workers and the newly created RDS database.
3. Show the Secrets Manager secret metadata without exposing its password.
4. Build/push the image, open the management tunnel and run Ansible.
5. Show that the Ingress creates the ALB and the HTTPS website works.
6. Submit the form and show the saved PostgreSQL row.
7. Demonstrate the security controls and findings.

Declare retained prerequisites: domain/DNS, state backend, required foundation encryption resources and security evidence. Build the runtime infrastructure from zero with a new empty database. Rehearse the demo steps and count provisioning, deletion, setup, rehearsal and demo against the less-than-ten-hour total paid runtime target.

## 6. Progress and next action

**Verified locally (26 September 2026):** requirements review, architecture decisions, diagram, and application implementation. Dockerized PostgreSQL accepted a browser form submission and stored its row. Thirteen focused tests passed; the Gunicorn image ran as UID/GID 10001. The disposable local containers and network were removed with `make down`. This earlier proof remains valid even though Docker is currently unavailable in WSL. Full AWS rebuilds are planned to create a fresh database; snapshot restoration is excluded.

**AWS bootstrap completed (26 September 2026):** the scoped `ContactFormTerraformStateAccess` and temporary `ContactFormTerraformBucketSetup` inline policies were attached to the non-root deployer; the temporary policy was removed after bootstrap verification. Terraform created the S3 state bucket in account `203888389134`, Region `ap-southeast-1`. The first apply created the bucket but lacked `s3:GetBucketAcl`; after adding the provider's required read actions, the bucket was confirmed in AWS, its taint was safely removed from local state, and a second apply configured the five remaining settings. A fresh Terraform plan reported `No changes`. Direct AWS reads verified versioning, four public-access blocks, SSE-S3 `AES256`, enforced bucket ownership, and the deny-insecure-transport policy. The bootstrap state is local, Git-ignored, and restricted to owner-only mode `600`. No foundation/workload state objects had been written at that verification; remote S3 state has not been freshly checked.

**Local infrastructure and deployment draft (27 September 2026):** Foundation stages and the workload S3 backend are explicit in the runbook. No remote backend initialization or state migration was run as part of these local changes. Workload Terraform has required version inputs, a read-only preflight helper and a scoped controller role policy. The controller policy and Terraform validated locally; live IAM simulation and reconciliation are pending. Ansible deploy/cleanup playbooks, Kubernetes templates and workstation helpers previously passed local syntax/render checks with synthetic outputs. None has run against AWS; tunnel, ALB, DNS, RDS, teardown and rebuild behavior remain unverified.

**Reviewed local fixes (27 September 2026):** The image-specific database setup Job now creates when absent, reuses completion, waits on a running Job, and safely diagnoses and recreates a terminal failed Job. Foundation now owns seven-day EKS and RDS log groups; the workload requires the foundation's RDS log-group output. The foundation evidence bucket has a scoped ALB log-delivery policy and `service-logs/alb/` lifecycle rules, passed through workload outputs to the Ingress annotation. These three code checkpoints passed independent review and were committed. The combined workstation/helper suite passed 30 offline tests, separate from the earlier 13 application tests; both Terraform roots passed formatting and validation, and Ansible deployment syntax and synthetic Ingress rendering passed. The controller inline policy rendered at 7,869 characters. None of these checks proves live Job recovery, IAM reconciliation, log delivery, credential reuse, or data preservation. No local foundation/workload `terraform.tfstate*` files were found; remote S3 keys remain unchecked. Follow the [backend and RDS log-group state handoff](terraform/README.md#backend-initialization) before any apply.

**Verification, cost and cleanup draft (27 September 2026):** The Singapore cost allowance, residual-resource inventory, RDS log exports, synthetic readback Job and security runbook are local drafts. The inventory now covers tagged EBS volumes/snapshots, retained RDS automated backups and workload KMS keys, with `PendingDeletion` reported separately from actionable remnants. Worker/relay root-volume tags are specified in Terraform but unverified live; untagged/manual resources and other Regions remain outside the checker. Its expanded read policy and the preflight read policy are both unattached and untested live. The first inventory read was denied on `ec2:DescribeVpcs`. No paid workload resources were created by this work.

**Current access and tooling (27 September 2026):** The `contact-form-deployer` profile previously returned a non-root IAM user in account `203888389134`, Region `ap-southeast-1`. Fresh read-only STS and quota attempts failed because the AWS login expired; the applied Standard EC2 quota and available headroom are unknown. Terraform 1.16.4, AWS CLI 2.37.0, kubectl 1.36.2, Helm 4.3.0, Ansible 2.21.4, Python 3.12.3 and Session Manager plugin 1.2.835.0 are installed. Docker is currently unavailable in the WSL distribution. The domain is purchased, but nameserver delegation and ACM validation are pending.

**Unresolved predeployment gates:** Restore AWS login and Docker; recheck ongoing backend access after the temporary setup policy was removed, inspect both actual remote states for RDS log-group ownership, and securely back up local bootstrap state. Choose actual supported EKS/add-on/node and relay AMI pins and run read-only preflight. Verify applied Singapore quota, update headroom, service availability, account security-service ownership, credits, and an updated cost estimate. Scoped Terraform provisioning IAM remains **unresolved**: no provisioning policy has been attached, simulated, or approved; the read-only policy drafts do not grant apply access. Provisioning role-policy management needs separate trusted-administrator review. Foundation/workload apply, live Ansible validation, first real ALB `.log.gz` delivery, FSBP evidence, teardown/rebuild and laptop rehearsal are pending.

**Next action:** restore local access, then verify the non-root account and Region, backend state and permissions, quota and version pins. Review provisioning IAM, existing security services, the full less-than-ten-hour paid schedule, credit eligibility and a current Singapore cost estimate before any paid apply. Finish registrar delegation and certificate validation at the appropriate foundation stage. After a live deployment, use the [ALB access-log verification](docs/security.md#alb-access-log-verification) to check a real recent `.log.gz` object. Do not treat local validation as live deployment evidence.

## References

- [ALB creation from an EKS Ingress](https://docs.aws.amazon.com/eks/latest/userguide/alb-ingress.html)
- [Systems Manager port forwarding](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html)
- [RDS deletion and backup behaviour](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DeleteInstance.html)
- [Security Hub evaluation timing](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-standards-schedule.html)
