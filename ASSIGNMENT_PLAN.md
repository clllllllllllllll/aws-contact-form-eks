# AWS Contact Form on EKS — Implementation Plan

**Status (28 September 2026):** The Flask/PostgreSQL app and Docker image were verified locally. Terraform bootstrap and foundation stages 01–03 remain in account `203888389134`, Region `ap-southeast-1`, including the state backend, DNS/ACM and security services. The user approved the full workload deployment and teardown after a US$0.50–1.00/hour estimate and a US$10–20 allowance before credits. A partial workload apply created a private EKS cluster, two NAT gateways, a private SSM relay, encrypted private Multi-AZ RDS with its managed master secret, application-secret metadata, ECR and an immutable app image. A TLS-verifying SSM tunnel returned Kubernetes `/readyz=ok`. Both managed node groups failed because the caller was denied `iam:GetRole` for `AWSServiceRoleForAmazonEKSNodegroup`; no Flask pods, ALB or end-to-end AWS application were created. The partial workload was subsequently torn down. Terraform now tracks no workload resources; direct reads found no project VPC, NAT gateway, EIP, active EC2 instance, tagged EBS volume, RDS instance or ALB. The EKS KMS key is `PendingDeletion` until 5 October. Snapshot reads were denied, and secret/ECR and backup metadata reads were also denied after deletion, so zero residual cost is **not** verified. A new cluster will have a new OIDC issuer; the old saved plans and kubeconfig were removed. Scoped IAM corrections and verification are required before another paid build.

**Objective:** Deploy a Flask contact form accepting name, email and message, with persistence in RDS PostgreSQL. Provision AWS infrastructure through Terraform and deploy the application through Ansible, entirely from the local workstation. Application infrastructure is provisioned from the workstation, not manually in the AWS Console. Initial IAM access policies were attached in the Console as an account prerequisite.

**Official deadline:** Tuesday 29 September 2026, 18:00 Singapore time. **Personal target:** Sunday 27 September 2026, 23:59; this target has passed. IAM preparation, end-to-end deployment, security evidence and a full teardown/rebuild remain open.

## 1. Resume context

- Repository: https://github.com/clllllllllllllll/aws-contact-form-eks
- Current PC checkout: `/home/limch/projects/aws-contact-form-eks` in WSL Ubuntu; branch `main`, tracking `origin/main`. Verify a separate laptop checkout before rehearsal.
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

**Budget:** approximately US$140 AWS credits reported by the user; eligibility and expiry are unverified. The US$10 budget and US$5 actual-cost email alert are warnings, **not a spending cap**. The user approved the 27/28 September full deployment and teardown at an estimated US$0.50–1.00/hour, with a US$10–20 planning allowance before credits for less than ten hours of total workload runtime. That workload was torn down; foundation resources remain, the EKS KMS key is pending deletion, and denied inventory reads prevent a zero-cost claim. Recheck costs, credits, permissions and a fresh plan before another paid build; destroy the workload after each session.

**Domain:** `cheelong.xyz` was registered through Exabytes. Public DNS delegation to Route 53 hosted zone `Z0153068M1DZTUZ2CE23` was verified and the ACM certificate is `ISSUED`. Live HTTPS application access remains unverified until the ALB and Ingress exist.

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
- [x] Reverify the PC's non-root AWS identity as `contact-form-deployer` in the intended account and Region. Keep credentials out of Git.
- [ ] Set up and verify authorized access on the laptop.
- [ ] Check Docker, AWS CLI, Session Manager plugin, Terraform, Ansible, kubectl, Helm, Python and required Ansible collections. Pin compatible versions.
- [x] Read the effective Singapore Standard On-Demand EC2 quota of 8 vCPUs by CLI.
- [ ] Check Singapore service versions, other permissions and quotas, costs and credits. Inspect any existing Config, Security Hub and CloudTrail setup.
- [ ] Inspect the deployer's actual managed and inline policies, boundaries and account controls; the recorded `ContactFormTerraformStateAccess` policy is inline and uses no managed attachment slot. Validate and simulate final provisioning/read policies before further attachment or paid apply.
- [x] Choose and purchase `cheelong.xyz` through Exabytes.

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
- [x] Create remote foundation stage 01 state; preserve the local bootstrap state.
- [x] Recheck the foundation and workload S3 state prefixes before first workload creation; foundation has state and workload has none. Retain the foundation RDS log-group ownership handoff.
- [x] Apply stage 01 with customer-managed `ContactFormFoundationStage01` attached for the approved window; update it with `logs:TagLogGroup` after the partial failure. The [stage 01 policy source](terraform/policies/foundation/deployer-foundation-stage-01.json) also retains `logs:TagResource`.
- [ ] Confirm the temporary stage 01 policy's attachment status and detach it after its completed window.
- [ ] Review the current attached workload IAM provisioning and role-write policy versions, then rotate grants by stage. Do not keep foundation and workload write permissions attached together.
- [x] Apply foundation stage 01: the Route 53 zone, configured evidence bucket and three retained log groups; the recovery plan had three additions only and the apply added three, for 11 resources total.
- [x] Scope the three later foundation service drafts to hosted zone `arn:aws:route53:::hostedzone/Z0153068M1DZTUZ2CE23`.
- [x] Apply foundation stage 02 after review and approval; verify AWS Config recording, CloudTrail logging and Security Hub FSBP `READY`. Record actual findings and any exceptions later.
- [x] Verify public delegation of `cheelong.xyz` to the four Route 53 nameservers using independent DNS resolvers.
- [x] Apply foundation stage 03 after delegation and verify that the `cheelong.xyz` ACM certificate is `ISSUED`.
- [x] Run read-only workload preflight with verified Singapore EKS/add-on/AMI, PostgreSQL and quota inputs; the 27 September result was `READY`.
- [ ] Recheck live inputs, cost and credits before the next paid apply.
- [x] Apply the first workload target on 27 September: `aws_kms_key.eks` and `aws_secretsmanager_secret.app` metadata were created with the [temporary managed bootstrap policy](terraform/policies/workload/deployer-workload-bootstrap-temporary-draft.json). These were part of the subsequently destroyed workload; the KMS key remains `PendingDeletion` until 5 October.
- [x] Record the user's 27 September confirmation that `ContactFormWorkloadBootstrapTemporary` was detached from `contact-form-deployer` and deleted. Attachment slots still require review before later grants.
- [x] Prepare exact-ARN KMS, EKS and secret/ECR policy copies for the first build; direct KMS and application-secret metadata reads succeeded at the time. Rebind generated ARNs before a rebuild; prior copies and issuer are stale.
- [ ] Have the IAM administrator inspect current default versions and attachments, remove any no-longer-needed `kms:CreateGrant` access after reviewing ongoing needs, and validate allowed and denied cases. `kms:CreateGrant` permits grantee choice.
- [x] Apply the separately approved cluster target on 27 September. Its first attempt needed `ec2:DescribeAddressesAttribute`; after that read grant and safe EIP untaint, a retry created private-only EKS 1.36 with five control-plane log types, Secrets encryption and two same-AZ NAT gateways. These resources were subsequently destroyed.
- [x] Bind the first cluster's live OIDC issuer to the published IAM provisioning policy for that attempt. Its exact-ARN `GetOpenIDConnectProvider` read returned `NoSuchEntity` before provider creation. The first cluster and its issuer no longer exist.
- [ ] Publish and verify scoped IAM corrections before another paid apply, especially `iam:GetRole` for `AWSServiceRoleForAmazonEKSNodegroup` and EKS read permissions needed when deleted resources lose tags or disappear. Bind all OIDC grants to the **new** cluster issuer; verify the default policy versions, attachments and direct API reads. Do not rely on the old issuer or old saved plans.
- [ ] Rebuild the full workload from zero: network, private EKS cluster, two managed node groups, core add-ons, private SSM relay, ECR, application secret and Multi-AZ RDS. The first full apply reached the relay, RDS, secrets and ECR, but never produced working worker nodes or an application; its partial stack was torn down.
- [ ] Guard against deploying to the wrong account or region. Give the controller, database setup Job, Flask and deployment identities only their required permissions.
- [x] Verify on the first build that RDS generated and managed its master secret, used private subnets, Multi-AZ and encryption. Pass secret identifiers (ARNs) through Terraform; keep actual passwords out of inputs, outputs and state.
- [ ] Reverify restrictive security groups, encryption, RDS backups, EKS control-plane logs, ECR scanning and access/audit logging on a successful rebuild. Open no inbound management ports on the relay.
- [ ] Provide non-secret foundation and workload Terraform outputs for Ansible.
- [x] Generate and apply an approved full workload plan on 27/28 September. The partial apply created the private relay, private encrypted Multi-AZ RDS, managed master secret, app-secret metadata and ECR; both managed node groups failed at the EKS service-role lookup. No Flask pods or ALB were created.
- [x] Open a TLS-verifying SSM tunnel through the private relay and receive Kubernetes `/readyz=ok` from the private EKS API. The relay, cluster and old kubeconfig were subsequently removed.
- [ ] Generate a fresh plan after IAM corrections, review its current costs and confirm the new plan remains within the approved scope and cost allowance, or obtain renewed approval. Do not reuse removed saved plans or kubeconfig.
- [x] Exercise the partial-workload Terraform teardown. Phase 5 still requires an ordered teardown and fresh rebuild **after** an ALB/application deployment.

**Acceptance:** the infrastructure exists and the workstation can reach the private EKS API.

### Phase 3 — Ansible deployment

- [x] Bind the first build's workstation helper grant to its exact relay and hosted-zone ARNs; the SSM tunnel worked. The relay ID is now stale after teardown.
- [ ] Rebind and verify the helper grant for a new relay, including its Session Manager document restriction and Route 53/ECR permissions.
- [x] Build and push an immutable application image to private ECR from the workstation during the first build. ECR deletion was requested during teardown, but the post-delete metadata read was denied; publish a fresh image on rebuild.
- [ ] Verify the image-publishing workflow and automatic use of fresh Terraform outputs on rebuild.
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
- [x] Destroy the 27/28 September **partial** workload. EKS add-on/cluster deletion waiters lost IAM read permission after resources disappeared; remove state entries only after direct deletion evidence. Terraform finished with no workload resources in state. NAT gateways were destroyed and their EIPs released after becoming unassociated. This did not test ALB/Ingress teardown because no ALB existed.
- [ ] After a successful application deployment, destroy runtime resources, including ALB, RDS and its application credentials, while preserving declared foundation resources and security evidence.
- [ ] Handle non-empty ECR cleanup and Secrets Manager deletion timing so rebuilding does not fail on retained resource names.
- [ ] On rebuild, repeat the short-lived deployer managed bootstrap grant and key/app-secret target, remove the grant immediately afterward, then repeat the cluster target and exact KMS/secret/OIDC ARN review for new IDs. The first cluster's OIDC issuer, saved plans and kubeconfig are stale and were removed. Keep new saved plans mode 600 under ignored `.local/`, and obtain renewed approval before paid creation if the plan exceeds the approved scope or cost allowance. Rebuild a fresh database, image and Ansible deployment.
- [ ] Verify that the previous test submission is absent, submit a new message and prove it is stored. Check for orphaned billable resources after teardown.
- [ ] Complete residual checks: `ec2:DescribeSnapshots` was denied, and secret/ECR and backup metadata reads were denied after deletion. Direct reads found no project VPC, NAT, EIP, active EC2, tagged EBS, RDS or ALB, but do not infer zero ongoing charges. The EKS KMS key is `PendingDeletion` until 5 October.

**Acceptance:** a complete destroy/rebuild starts with an empty database, accepts new submissions and requires no manual Console repairs. The current exact-issuer IAM policy and exact KMS/secret grants require an administrator to bind newly generated identifiers on every rebuild; this acceptance criterion remains open until a secure repeatable authorization path is implemented and demonstrated. Do not claim an unattended rebuild from the current runbook.

### Phase 6 — Documentation and laptop rehearsal

- [ ] Finish the deliverables below, including exact setup, deployment, teardown and fresh-rebuild commands.
- [ ] On the laptop, verify AWS identity, use the same code/tool versions and rehearse the complete teardown and fresh deployment.
- [ ] Save security findings from rehearsal. Newly enabled Security Hub controls can take time to produce results; label evidence with its actual date.
- [ ] Check Git history and tracked files for credentials, Terraform state, private keys, generated kubeconfig or sensitive evidence.
- [ ] Finish and rehearse before the official Tuesday 29 September 18:00 Singapore deadline; the Sunday personal target has passed.

**Acceptance:** the laptop can reproduce the deployment and every demo requirement has a clear step.

## 5. Deliverables and live demo

Suggested folders: `app/`, `terraform/bootstrap/`, `terraform/foundation/`, `terraform/workload/`, `terraform/policies/`, `ansible/`, `scripts/` and `docs/`.

- [ ] Terraform code.
- [ ] Ansible playbooks and Kubernetes templates.
- [x] Flask source, tests and container build, verified locally.
- [ ] Kubernetes manifests/templates and Helm configuration.
- [ ] Architecture diagram showing both AZs, public/private traffic, secrets and workstation access.
- [ ] README covering prerequisites, deployment, verification, troubleshooting, teardown and fresh rebuild; state explicitly that destroying RDS deletes demo submissions.
- [ ] Security-hardening document explaining the controls and limitations.
- [ ] FSBP configuration, findings, fixes and remaining exceptions.
- [ ] Clean Git history with meaningful commits and no secrets.

Execute the live demo from the local workstation:

1. Show the AWS identity and bootstrap any missing declared prerequisites.
2. After retained prerequisites, state review and preflight, publish and verify the scoped IAM corrections. Attach the temporary managed bootstrap policy to the deployer in a short IAM Console window, review the new saved plan and cost, and confirm it fits the existing costed approval; seek renewed approval if it does not. Remove the policy immediately after its target, bind exact key/secret ARNs, then review the cluster target. Rebind all four OIDC grants from the **new** cluster's live issuer before the remaining workload apply.
3. Show the Secrets Manager secret metadata without exposing its password.
4. Build/push the image, open the management tunnel and run Ansible.
5. Show that the Ingress creates the ALB and the HTTPS website works.
6. Submit the form and show the saved PostgreSQL row.
7. Demonstrate the security controls and findings.

Declare retained prerequisites: domain/DNS, state backend, required foundation encryption resources and security evidence. Build the runtime infrastructure from zero with a new empty database. Rehearse the demo steps and count provisioning, deletion, setup, rehearsal and demo against the less-than-ten-hour total paid runtime target.

## 6. Progress and next action

**Verified locally (26 September 2026):** The Flask form, schema, PostgreSQL persistence and non-root Gunicorn container worked locally. Thirteen focused tests passed and a browser submission produced a database row. Disposable local containers were removed with `make down`.

**Retained AWS prerequisites (26–27 September 2026):** Terraform created and verified the encrypted, versioned S3 state bucket. Foundation stages 01–03 established the Route 53 zone and delegation for `cheelong.xyz`, evidence bucket, retained EKS/RDS log groups, AWS Config recording, CloudTrail logging, Security Hub FSBP subscription and an `ISSUED` ACM certificate. The bootstrap and foundation layers remain; actual project-specific FSBP findings and exceptions still need to be collected. The Singapore Standard On-Demand EC2 quota was confirmed at eight vCPUs.

**Historical partial workload deployment (27–28 September 2026):** The user approved the full deployment and teardown after an estimated US$0.50–1.00/hour and US$10–20 planning allowance before credits. Terraform created a private-only EKS 1.36 cluster, two NAT gateways, a private SSM relay with no public IP, encrypted private Multi-AZ RDS PostgreSQL with an RDS-managed master secret, application-secret metadata and private ECR. The app image was published to ECR by immutable digest. A TLS-verifying SSM tunnel through the relay returned Kubernetes `/readyz=ok`. This verified management access to the private EKS API, not an application deployment.

**Node-group blocker (27–28 September 2026):** Both managed node groups failed when EKS could not validate `AWSServiceRoleForAmazonEKSNodegroup` because the caller was denied `iam:GetRole`. No worker nodes, Flask pods, Ingress-created ALB, HTTPS form submission or RDS application row were verified. Scoped IAM fixes for the role lookup and EKS deletion/refresh reads must be published as live default policy versions and tested before another paid apply. A freshly created cluster will have a different OIDC issuer and generated resource ARNs.

**Historical partial teardown (28 September 2026):** EKS add-on and cluster deletion waiters became IAM read-denied after the resources disappeared; state entries were removed only after direct deletion evidence. NAT gateways were destroyed and EIPs released after they became unassociated. Terraform's final workload state listed no managed resources. Direct reads found no project VPC, NAT gateway, EIP, active EC2 instance, tagged EBS volume, RDS instance or ALB. The EKS KMS key is `PendingDeletion` until 5 October. The residual checker was incomplete because `ec2:DescribeSnapshots` was denied; secret/ECR and backup metadata reads were also denied after deletion. These checks do not prove zero remaining charges. Old saved plans and kubeconfig were removed.

**Cost and access limits:** The US$10 budget and US$5 actual-cost email alert are warnings, not a cap. Reported US$140 credits have not had their eligibility, balance and expiry verified. Foundation resources remain active, and the pending KMS deletion and incomplete inventory need follow-up. The deployer lacks Billing/Cost Explorer access; check actual charges in the account before another paid build.

**Current completion gates:** Verify the published, attached IAM policy versions with direct API reads; repeat preflight, cost review and a fresh Terraform plan; confirm the rebuild fits the existing costed approval or seek renewed approval; bind the new cluster's OIDC issuer and generated ARNs; create both workers; deploy controller, setup Job, Flask, Service and the single Ingress-created ALB through Ansible; verify HTTPS submission and its RDS row; capture actual security findings; then demonstrate ordered teardown and a fresh rebuild. Do not claim the prior partial teardown proves ALB cleanup or end-to-end reproducibility.

**Next action:** Publish and verify the narrowly scoped IAM corrections, including the node-group service-role lookup and EKS reads used by deletion waiters. Confirm the workload state is empty and check incomplete residual inventory and current costs. Then prepare a **new** costed Terraform plan under the existing approval if its scope and cost still match. No workload is currently tracked as live; bootstrap and foundation remain, while the first EKS KMS key is pending deletion.

## References

- [ALB creation from an EKS Ingress](https://docs.aws.amazon.com/eks/latest/userguide/alb-ingress.html)
- [Systems Manager port forwarding](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html)
- [RDS deletion and backup behaviour](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DeleteInstance.html)
- [Security Hub evaluation timing](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-standards-schedule.html)
