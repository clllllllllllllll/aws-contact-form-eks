# AWS Contact Form on EKS — Implementation Plan

**Status:** The application is verified locally. The state bucket is applied and verified in AWS. Foundation Terraform is drafted and locally validated, but not applied. Workload infrastructure and the application have not been deployed.

**Objective:** Deploy a Flask contact form accepting name, email and message, with persistence in RDS PostgreSQL. Provision AWS infrastructure through Terraform and deploy the application through Ansible, entirely from the local workstation. Application infrastructure is provisioned from the workstation, not manually in the AWS Console. Initial IAM access policies were attached in the Console as an account prerequisite.

**Official deadline:** Tuesday 29 September 2026, 18:00 Singapore time. **Personal target:** Sunday 27 September 2026, 23:59; aim to finish by 20:00 to leave time for fixes.

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
| HTTPS | Buy an inexpensive domain, use Route 53 for DNS, and attach a free non-exportable ACM public certificate from Singapore to the ALB. Redirect HTTP to HTTPS. |
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

**Budget:** approximately US$140 AWS credits; initial usage target US$10 drawn from those credits. The agreed Multi-AZ design has not been priced. Estimate Singapore costs and verify credit eligibility/expiry before deployment.

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

Plan approximately ten focused hours per day. Phase durations are estimates.

**Day 1 milestone:** a submission through the ALB is stored in RDS.

**Day 2 milestone:** verified security, successful teardown/fresh rebuild, complete deliverables and laptop rehearsal.

### Phase 0 — Access and workstation checks

*Day 1, hour 1*

- [ ] Check the PC's repository, Git status and local repository instructions.
- [ ] Verify non-root AWS access to the correct account. Set up authorized access on the laptop too; keep credentials out of Git.
- [ ] Check Docker, AWS CLI, Session Manager plugin, Terraform, Ansible, kubectl, Helm, Python and required Ansible collections. Pin compatible versions.
- [ ] Check Singapore service versions, permissions, quotas, costs and credits. Inspect any existing Config, Security Hub and CloudTrail setup.
- [ ] Choose the domain and document how its registrar points DNS to Route 53.

**Acceptance:** the tools work and the correct non-root AWS identity is confirmed. If AWS access is blocked, continue only with local development.

### Phase 1 — Application and local tests

*Day 1, hours 2–3*

- [ ] Build the form and confirmation page. Validate email and field lengths, add CSRF protection, use parameterized SQL and return safe error messages.
- [ ] Add a liveness check for the running application and a readiness check that includes database connectivity. A database outage should not cause endless container restarts.
- [ ] Build a non-root Gunicorn container with pinned dependencies and the RDS certificate bundle.
- [ ] Use Boto3 to read the application secret through an IAM role assigned to its Kubernetes service account (IRSA). Store the shared signing secret securely and handle database reconnections.
- [ ] Test valid and invalid submissions, saved rows, database errors and non-root startup against local PostgreSQL. Avoid logging passwords or submitted personal information.

**Acceptance:** a local submission is saved and the focused tests pass.

### Phase 2 — Terraform infrastructure

*Day 1, hours 4–6*

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

*Day 1, hours 7–8*

- [ ] Automate building and pushing the image from the workstation. Read Terraform outputs automatically instead of copying IDs by hand.
- [ ] Install the pinned AWS Load Balancer Controller with Helm. Manage the namespace, service accounts, Kubernetes RBAC and manifests through Ansible.
- [ ] Run a database setup Job using the master secret. On a fresh build, generate application credentials and create the table and restricted database user. On reruns against the same database, reuse credentials and preserve existing rows.
- [ ] Give Flask access only to its own secret and required database operations. It should not need schema-changing or unnecessary Kubernetes permissions.
- [ ] Deploy two replicas, one per worker/AZ, with health checks, CPU/memory requests and limits, non-root execution, no privilege escalation, dropped capabilities and a read-only filesystem where compatible.
- [ ] Apply the Service and HTTPS Ingress, wait for the ALB and healthy targets, then create the application's DNS alias through Ansible.

Each resource must have one owner. Repeating Ansible against an existing environment must reuse credentials and preserve data; rebuilding after a full destroy intentionally starts empty.

**Acceptance:** the HTTPS website accepts a submission and stores it in RDS.

### Phase 4 — Functional and security verification

*Day 1, hours 9–10; Day 2, hours 1–2*

- [ ] Submit a recognizable test message and show its database row through a controlled query from inside the VPC.
- [ ] Check that only the ALB accepts public inbound traffic. Verify private EKS access, RDS certificate verification, secret permissions, RBAC, logs and container settings.
- [ ] Inspect node AZ labels and pod placement: one worker in each AZ and one Flask replica on each worker.
- [ ] Replace an application pod and confirm the submission remains. Test recovery of database connections.
- [ ] Rerun Terraform plan and Ansible. Check for unexpected changes, duplicate resources, password resets or lost data.
- [ ] Export timestamped FSBP findings. Fix issues within scope and explain remaining findings or account prerequisites. A check awaiting evaluation is not a pass.

**Acceptance:** the application works, the agreed layout is verified and security evidence is saved.

### Phase 5 — Teardown and fresh rebuild

*Day 2, hours 3–5*

- [ ] Exercise the local teardown workflow prepared before the first destroy: stop new submissions, finish pending requests and remove the application DNS alias and Ingress.
- [ ] Wait for the controller to delete its ALB resources before destroying EKS and the network.
- [ ] Destroy runtime resources, including RDS and its application credentials. Preserve only the declared foundation resources and security evidence.
- [ ] Handle non-empty ECR cleanup and Secrets Manager deletion timing so rebuilding does not fail on retained resource names.
- [ ] Run a fresh Terraform apply, republish the image and run Ansible using the new resource outputs. Initialize a new database, table and application user.
- [ ] Verify that the previous test submission is absent, submit a new message and prove it is stored. Check for orphaned billable resources after teardown.

**Acceptance:** a complete destroy/rebuild starts with an empty database, accepts new submissions and requires no manual Console repairs.

### Phase 6 — Documentation and laptop rehearsal

*Day 2, hours 6–10*

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
- [ ] Flask source, tests and container build.
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

Declare retained prerequisites: domain/DNS, state backend, required foundation encryption resources and security evidence. Build the runtime infrastructure from zero with a new empty database. Demo duration is not a planning blocker.

## 6. Progress and next action

**Completed (26 September 2026):** requirements review, architecture decisions, diagram, and local application implementation. The WSL profile `contact-form-deployer` previously returned a non-root IAM user in account `203888389134`, with Region `ap-southeast-1`; reconfirm the current session before provisioning. Dockerized PostgreSQL accepted a browser form submission and stored its row. Thirteen focused tests passed; the Gunicorn image runs as UID/GID 10001. The disposable local containers and network were removed with `make down`. Full AWS rebuilds are planned to create a fresh database; snapshot restoration is excluded.

**AWS bootstrap completed (26 September 2026):** the scoped `ContactFormTerraformStateAccess` and temporary `ContactFormTerraformBucketSetup` inline policies were attached to the non-root deployer; the temporary policy was removed after bootstrap verification. Terraform created the S3 state bucket in account `203888389134`, Region `ap-southeast-1`. The first apply created the bucket but lacked `s3:GetBucketAcl`; after adding the provider's required read actions, the bucket was confirmed in AWS, its taint was safely removed from local state, and a second apply configured the five remaining settings. A fresh Terraform plan reported `No changes`. Direct AWS reads verified versioning, four public-access blocks, SSE-S3 `AES256`, enforced bucket ownership, and the deny-insecure-transport policy. The bootstrap state is local, Git-ignored, and restricted to owner-only mode `600`; no foundation/workload state objects have been written.

**Pending:** check ongoing backend access after removing the temporary bucket-setup policy; preserve a secure backup of the local bootstrap state; verify the SSM plugin, Singapore quotas and full-stack cost estimate, credit eligibility, domain nameserver delegation and certificate validation, foundation apply, workload Terraform and Ansible implementation, AWS deployment, security findings, teardown/rebuild, and laptop rehearsal. No EKS, RDS, NAT, ALB, or application AWS infrastructure has been provisioned.

**Next action:** wait for S3 versioning to propagate before the first backend state write; verify backend access through the ongoing state-access policy. Review the drafted foundation tier, price it, and obtain separate cost approval before apply. Do not apply paid foundation or workload resources without explicit cost confirmation.

## References

- [ALB creation from an EKS Ingress](https://docs.aws.amazon.com/eks/latest/userguide/alb-ingress.html)
- [Systems Manager port forwarding](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html)
- [RDS deletion and backup behaviour](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DeleteInstance.html)
- [Security Hub evaluation timing](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-standards-schedule.html)
