# AWS Contact Form on EKS — Implementation Plan

**Status (27 September 2026):** The application and container were verified locally, and the S3 state bucket and foundation stage 01 were applied in account `203888389134`, `ap-southeast-1`. After a partial stage 01 failure and policy repair, a fresh plan showed three additions only; apply succeeded with three added, leaving 11 foundation resources in remote state. These include Route 53 zone `cheelong.xyz` (`Z0153068M1DZTUZ2CE23`), the configured evidence bucket and three seven-day EKS/RDS log groups. Customer-managed `ContactFormFoundationStage01` was attached for this stage; later provisioning policy drafts remain unverified live. A shortened preflight read policy was attached inline to the deployer, and CLI read the effective Singapore Standard On-Demand quota as 8 vCPUs. Three local code checkpoints passed review and the combined workstation/helper suite passed 30 offline tests. Later foundation stages, workload Terraform, Ansible, full read-only preflight and cleanup remain untested in AWS. No EKS, RDS, NAT gateway, ALB, ACM, Config, Security Hub, CloudTrail or AWS application deployment is verified; registrar delegation and account-wide inventory remain unverified. AWS CLI identity was reverified; Docker needs a fresh WSL check.

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

**Domain:** `cheelong.xyz` was registered through Exabytes. Route 53 hosted zone `Z0153068M1DZTUZ2CE23` exists, but registrar nameserver delegation is still pending; do not claim public DNS or HTTPS works yet.

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
- [ ] PC non-root AWS identity was reverified; set up and verify authorized access on the laptop too. Keep credentials out of Git.
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
- [ ] Recheck the exact foundation/workload state keys and RDS log-group ownership before the next apply; the workload key remains unchecked.
- [x] Apply stage 01 with customer-managed `ContactFormFoundationStage01` attached for the approved window; update it with `logs:TagLogGroup` after the partial failure. The [stage 01 policy source](terraform/policies/foundation/deployer-foundation-stage-01.json) also retains `logs:TagResource`.
- [ ] Confirm the temporary stage 01 policy's attachment status and detach it after its completed window.
- [ ] Review the two IAM drafts and broader foundation refresh/apply/destroy drafts for later stages. An administrator creates, versions and attaches approved policies for each window; keep role-write access short-lived. Rotate refresh + apply or refresh + destroy, never all service writes by default.
- [x] Apply foundation stage 01: the Route 53 zone, configured evidence bucket and three retained log groups; the recovery plan had three additions only and the apply added three, for 11 resources total.
- [x] Scope the three later foundation service drafts to hosted zone `arn:aws:route53:::hostedzone/Z0153068M1DZTUZ2CE23`.
- [ ] Inspect account security-service ownership and apply the selected Config/FSBP and trail stage after its own review and approval.
- [ ] Verify registrar nameserver delegation to the new Route 53 hosted zone and document the live result.
- [ ] Apply the DNS-validated ACM stage after delegation. After ACM creation, narrow its certificate ARN and validation CNAME for later changes or teardown. Do not replay an earlier stage file over a later state.
- [ ] Run read-only preflight with verified Singapore version, AMI and quota inputs; update the estimate and credit check and obtain approval before each paid apply.
- [ ] For first workload creation, a trusted administrator uses the same workload Terraform state for a separately reviewed targeted apply of only `aws_kms_key.eks` and empty `aws_secretsmanager_secret.app` metadata. Copy their exact generated ARNs into the KMS, EKS and Secrets Manager drafts; validate/simulate and attach the approved policies. The deployer drafts grant neither key nor app-secret creation; exact-ARN management must not overlap broad create-time tagging. Keep all four OIDC grants inert at `id/BOOTSTRAP-PLACEHOLDER` through the next target.
- [ ] Using the same verified variables, the deployer reviews a separate saved `-target=aws_eks_cluster.main` plan. Inspect VPC/NAT/role dependencies, update the Singapore estimate and credits, and obtain separate approval; EKS paid time starts when the cluster is created. Read its issuer with `aws eks describe-cluster`. An administrator regenerates ignored mode-600 `.local/deployer-iam-provisioning.json` from the inert tracked template, rebinds all four OIDC grants in that copy, validates/simulates allowed and denied cases, and publishes/attaches that copy before a **fresh full** workload plan/apply.
- [ ] Create the network, two NAT gateways, private EKS API, two managed node groups, EKS core add-ons, relay, ECR and Multi-AZ RDS.
- [ ] Guard against deploying to the wrong account or region. Give the controller, database setup Job, Flask and deployment identities only their required permissions.
- [ ] Let RDS generate and manage the master password. Pass secret identifiers (ARNs) through Terraform, keeping actual passwords out of Terraform inputs, outputs and state.
- [ ] Configure restrictive security groups, encryption, RDS backups, EKS control-plane logs, ECR scanning and appropriate access/audit logging. Open no inbound management ports on the relay.
- [ ] Provide non-secret foundation and workload Terraform outputs for Ansible.
- [ ] Review and apply the saved full workload plan after **both** target stages and exact-ARN policy rebinding; test the local tunnel to EKS. Keep certificate and hostname verification enabled.
- [ ] Configure disposable RDS/secret lifecycles and prepare the ordered teardown workflow before the first destroy. Phase 5 validates the full rebuild.

**Acceptance:** the infrastructure exists and the workstation can reach the private EKS API.

### Phase 3 — Ansible deployment

- [ ] Replace the helper draft's hosted-zone wildcard with the exact foundation zone ARN, validate/simulate its ECR, Session Manager and Route 53 grants, and attach it only for the approved image, tunnel and alias operations. Check the live session-document restriction before relying on it.
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
- [ ] On rebuild, repeat the trusted key/app-secret target, the deployer cluster target, and exact KMS/secret/OIDC ARN policy review for all new IDs. Regenerate the ignored OIDC policy copy from the inert template; reject an old or mixed issuer. Each target needs its own reviewed saved plan, updated cost and approval. Generate a fresh full workload plan only after the new issuer copy is published; apply it, republish the image and run Ansible using new outputs. Initialize a new database, table and application user.
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
2. After retained prerequisites, state review, preflight and the paid-apply gate, run the reviewed trusted-administrator target creation of the workload key and app-secret metadata. Rebind those exact ARNs and rotate approved policies. With OIDC permissions still inert, review and separately approve the deployer's saved cluster target, apply it, read its issuer and have the administrator rebind all four OIDC statements in an ignored mode-600 review copy made from the inert template. After validating/simulating and publishing/attaching that copy, run a fresh full workload plan/apply and show the EKS workers and new RDS database.
3. Show the Secrets Manager secret metadata without exposing its password.
4. Build/push the image, open the management tunnel and run Ansible.
5. Show that the Ingress creates the ALB and the HTTPS website works.
6. Submit the form and show the saved PostgreSQL row.
7. Demonstrate the security controls and findings.

Declare retained prerequisites: domain/DNS, state backend, required foundation encryption resources and security evidence. Build the runtime infrastructure from zero with a new empty database. Rehearse the demo steps and count provisioning, deletion, setup, rehearsal and demo against the less-than-ten-hour total paid runtime target.

## 6. Progress and next action

**Verified locally (26 September 2026):** requirements review, architecture decisions, diagram, and application implementation. Dockerized PostgreSQL accepted a browser form submission and stored its row. Thirteen focused tests passed; the Gunicorn image ran as UID/GID 10001. The disposable local containers and network were removed with `make down`. This earlier proof remains valid even though Docker is currently unavailable in WSL. Full AWS rebuilds are planned to create a fresh database; snapshot restoration is excluded.

**AWS bootstrap completed (26 September 2026):** the scoped `ContactFormTerraformStateAccess` and temporary `ContactFormTerraformBucketSetup` inline policies were attached to the non-root deployer; the temporary policy was removed after bootstrap verification. Terraform created the S3 state bucket in account `203888389134`, Region `ap-southeast-1`. The first apply created the bucket but lacked `s3:GetBucketAcl`; after adding the provider's required read actions, the bucket was confirmed in AWS, its taint was safely removed from local state, and a second apply configured the five remaining settings. A fresh Terraform plan reported `No changes`. Direct AWS reads verified versioning, four public-access blocks, SSE-S3 `AES256`, enforced bucket ownership, and the deny-insecure-transport policy. The bootstrap state is local, Git-ignored, and restricted to owner-only mode `600`. At that 26 September verification, no foundation/workload state objects had been written; foundation remote state was created on 27 September, while the workload key remains unchecked.

**Foundation stage 01 completed (27 September 2026):** In account `203888389134`, Region `ap-southeast-1`, the approved `01-base.tfvars` apply initially failed partway through. Customer-managed `ContactFormFoundationStage01` was attached for the stage and updated with `logs:TagLogGroup` in addition to the existing `logs:TagResource` grant. A fresh plan after repair showed three additions only, and the apply succeeded with three added. Remote foundation state contains 11 resources: Route 53 hosted zone `cheelong.xyz` (`Z0153068M1DZTUZ2CE23`); evidence bucket `aws-contact-form-evidence-203888389134-ap-southeast-1` with public-access block, ownership controls, SSE-S3, versioning, lifecycle rules and bucket policy; and the EKS cluster plus RDS `postgresql` and `upgrade` CloudWatch log groups, each with seven-day retention. Bucket configuration applied, but actual service log delivery is unverified. Registrar delegation remains pending.

**Local infrastructure and deployment draft (27 September 2026):** The package procedures in [Terraform roots](terraform/README.md), [workload first creation](terraform/workload/README.md#two-target-first-creation-and-oidc-binding), and [Ansible deployment](ansible/README.md) cover foundation stages, backend reconciliation, paid-apply gates, trusted key/app-secret target creation, deployer cluster target and OIDC issuer rebinding, then full workload apply and rebuild. Foundation stage 01 has been exercised live; later stages and workload procedures have not. No state migration is verified. Workload Terraform has required version inputs, a read-only preflight helper and a scoped controller role policy. The controller policy and Terraform validated locally; live IAM simulation and workload state reconciliation are pending. Ansible deploy/cleanup playbooks, Kubernetes templates and workstation helpers previously passed local syntax/render checks with synthetic outputs. None has run against AWS; tunnel, ALB, registrar delegation, RDS, teardown and rebuild behavior remain unverified.

**Committed permission drafts (27 September 2026):** Two IAM, three foundation service, six workload service, and one workstation helper customer managed policy JSON drafts are committed; their [IAM and foundation review procedure](terraform/README.md#iam-and-service-policy-windows), [workload review procedure](terraform/workload/README.md#two-target-first-creation-and-oidc-binding), and [helper review procedure](scripts/README.md#helper-permission-window) are in tracked package READMEs. The checked-in IAM OIDC draft has an inert exact issuer placeholder in all four provider statements and a separate request-tag-constrained initial-create Tag grant. Local JSON parsing and nonwhitespace-size checks establish syntax and size only. The IAM role-write draft can alter trust and inline permissions on named roles without a permissions boundary; it needs a trusted administrator's short provisioning window. The separate stage 01 service policy source was used for customer-managed `ContactFormFoundationStage01`, which was attached and repaired for the completed base apply; its current attachment status and live simulation evidence remain unchecked. Other provisioning drafts remain unverified live. Later foundation plan/apply needs refresh + apply; an optional teardown uses refresh + destroy in a separate window. A 27 September console screenshot showed one managed policy attached directly to the deployer before the stage 01 window, while `ContactFormTerraformStateAccess` is inline. Six workload drafts plus two IAM drafts would use **9 of the default 10 user attachment slots** with that one direct attachment; adding the helper would use the tenth. Count the stage 01 policy as another slot if it remains attached. The group's managed policy has a separate group quota. Recheck actual grants and attachment slots before each window. Do not keep foundation and workload writes attached together by default. Workload KMS, app-secret and OIDC grants still contain exact-ARN placeholders pending both target creations and rebinding.

**Reviewed local fixes (27 September 2026):** The image-specific database setup Job now creates when absent, reuses completion, waits on a running Job, and safely diagnoses and recreates a terminal failed Job. Foundation stage 01 applied the seven-day EKS and RDS log groups; the workload requires the foundation's RDS log-group output. The foundation evidence bucket has an applied scoped ALB log-delivery policy and `service-logs/alb/` lifecycle rules, passed through workload outputs to the Ingress annotation. These three code checkpoints passed independent review and were committed. The combined workstation/helper suite passed 30 offline tests, separate from the earlier 13 application tests; both Terraform roots passed formatting and validation, and Ansible deployment syntax and synthetic Ingress rendering passed. The controller inline policy rendered at 7,869 characters. None of these checks proves live Job recovery, IAM reconciliation, log delivery, credential reuse, or data preservation. Foundation remote state now exists; the workload remote key remains unchecked. Follow the [backend and RDS log-group state handoff](terraform/README.md#backend-initialization) before the next apply.

**Verification, cost and cleanup draft (27 September 2026):** The Singapore cost allowance, residual-resource inventory, RDS log exports, synthetic readback Job and security runbook are local drafts. The inventory now covers tagged EBS volumes/snapshots, retained RDS automated backups and workload KMS keys, with `PendingDeletion` reported separately from actionable remnants. Worker/relay root-volume tags are specified in Terraform but unverified live; untagged/manual resources and other Regions remain outside the checker. The expanded runtime-inventory read policy remains unattached; the first inventory read was denied on `ec2:DescribeVpcs`. A shortened preflight read policy was attached inline and its quota read succeeded, but the full preflight has not run. No paid workload resources were created by this work.

**Current access and tooling (27 September 2026):** After `aws login`, STS returned `arn:aws:iam::203888389134:user/contact-form-deployer` in account `203888389134`; the configured Region is `ap-southeast-1`. CLI read the effective Singapore Standard On-Demand EC2 quota as 8 vCPUs; check available headroom before workload provisioning. Terraform 1.16.4, AWS CLI 2.37.0, kubectl 1.36.2, Helm 4.3.0, Ansible 2.21.4, Python 3.12.3 and Session Manager plugin 1.2.835.0 were previously verified; recheck tool availability before deployment. Docker has not been rechecked in this WSL session. The domain is purchased and its Route 53 zone exists, but registrar delegation and ACM validation are pending. The foundation S3 backend now has stage 01 state; workload state remains unchecked.

**Unresolved predeployment gates:** Verify Docker and recheck ongoing backend access, inspect both actual remote states for RDS log-group ownership, and securely back up local bootstrap state. Check at least 6 free Standard On-Demand vCPUs before creating the two workers and relay; the effective quota is 8 vCPUs. Choose supported EKS/add-on/node and relay AMI pins and run the full read-only preflight. Verify update headroom, service availability, account security-service ownership, credits, and an updated cost estimate. Further scoped provisioning remains **unresolved** despite the completed stage 01: an administrator must inspect actual grants/attachment slots, validate and simulate the final IAM and service policies, review role-write escalation and stage-specific generated ARN replacements, and attach only the approved window. The trusted KMS/app-secret target and deployer cluster target each need a reviewed saved plan, updated cost and paid-apply approval before the OIDC issuer can be rebound and a fresh full workload plan approved. The read-only preflight grant does not authorize apply. Later foundation stages, workload apply, live Ansible validation, first real ALB `.log.gz` delivery, FSBP evidence, teardown/rebuild and laptop rehearsal are pending.

**Next action:** record the stage 01 state and output values, confirm whether `ContactFormFoundationStage01` remains attached and detach it after its window, then enter the hosted zone's nameservers at Exabytes and verify public delegation. Before the next apply, verify Docker and the non-root account/Region, reconcile the foundation and workload state keys and RDS log-group ownership, and check current quota headroom and supported version pins. Inspect Config, Security Hub and CloudTrail ownership; verify the exact hosted-zone ARN already bound in the later foundation policies, validate/simulate the reviewed policies, and approve the selected stage 02 plan, cost and attachment window. Apply stage 03 only after delegation, then verify ACM issuance. Continue with the separately approved trusted workload key/app-secret target, rebind those ARNs, review/approve the separate deployer cluster target, and rebind the new OIDC issuer before a fresh full plan. After a live deployment, use the [ALB access-log verification](docs/security.md#alb-access-log-verification) to check a real recent `.log.gz` object. Local validation is not live deployment evidence.

## References

- [ALB creation from an EKS Ingress](https://docs.aws.amazon.com/eks/latest/userguide/alb-ingress.html)
- [Systems Manager port forwarding](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html)
- [RDS deletion and backup behaviour](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DeleteInstance.html)
- [Security Hub evaluation timing](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-standards-schedule.html)
