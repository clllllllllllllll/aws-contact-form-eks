# AWS Contact Form on EKS — Implementation Plan

**Status (27 September 2026):** The Flask/PostgreSQL app and Docker image were verified locally. The Terraform state bucket and foundation stages 01, 02 and 03 were applied in account `203888389134`, Region `ap-southeast-1`. Route 53 delegation for `cheelong.xyz` was verified, and its ACM certificate is `ISSUED`. AWS Config is recording, CloudTrail is logging, and the Security Hub Foundational Security Best Practices standard is `READY`. The read-only workload preflight returned `READY` for the pinned EKS 1.36, add-on, AMI and Multi-AZ PostgreSQL inputs; the Standard On-Demand EC2 quota was eight vCPUs. The first workload target created `aws_kms_key.eks` and `aws_secretsmanager_secret.app` metadata. The separately approved cluster target initially stopped after creating part of the network, two tagged EIPs and its IAM role because `ec2:DescribeAddressesAttribute` was denied. After that read permission was added, the live EIPs were verified and safely untainted; a fresh seven-create, zero-change, zero-destroy retry plan was applied. Direct AWS reads confirmed EKS `contact-form-eks` is `ACTIVE` at 1.36 with a private-only API, all five control-plane log types enabled and Secrets encryption, and two NAT gateways are `available`, one per AZ. The user confirmed that the default `ContactFormIAMProvisioning` JSON contains the live issuer in all four OIDC statements and is attached to `contact-form-deployer`; an exact-ARN `GetOpenIDConnectProvider` read returned `NoSuchEntity`, confirming read authorization while the provider remains uncreated. The user also confirmed the exact-ARN `ContactFormWorkloadSecretECR` policy attached, and a direct `DescribeSecret` metadata read succeeded. A refreshed full Terraform plan succeeded with 50 additions, zero changes and zero destroys; it has not been applied or cost-approved. IAM simulation remains unverified. Workers, RDS, ALB, the AWS application, teardown and rebuild remain unverified. The deployer cannot read Billing/Cost Explorer or the full workload inventory through its current CLI grants.

**Objective:** Deploy a Flask contact form accepting name, email and message, with persistence in RDS PostgreSQL. Provision AWS infrastructure through Terraform and deploy the application through Ansible, entirely from the local workstation. Application infrastructure is provisioned from the workstation, not manually in the AWS Console. Initial IAM access policies were attached in the Console as an account prerequisite.

**Official deadline:** Tuesday 29 September 2026, 18:00 Singapore time. **Personal target:** Sunday 27 September 2026, 23:59. The target remains at risk until IAM preparation, workload deployment, security evidence and teardown/rebuild are verified.

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

**Budget:** approximately US$140 AWS credits reported by the user; eligibility and expiry are unverified. The US$10 budget and US$5 actual-cost email alert are warnings, not a spending cap. The EKS cluster, two NAT gateways and their allocated public IPv4 addresses are now live and accruing charges; the earlier cluster-stage allowance was about US$0.25–0.40 per hour before credits and variable use, not a bill or guarantee. Verify current pricing, credits and actual billing before the next paid apply. Keep total paid runtime under ten hours across provisioning, deletion, setup, rehearsal and demo, and destroy the workload when the session is over.

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
- [x] Recheck the foundation and workload S3 state prefixes before first workload creation; foundation has state and workload has none. Retain the foundation RDS log-group ownership handoff.
- [x] Apply stage 01 with customer-managed `ContactFormFoundationStage01` attached for the approved window; update it with `logs:TagLogGroup` after the partial failure. The [stage 01 policy source](terraform/policies/foundation/deployer-foundation-stage-01.json) also retains `logs:TagResource`.
- [ ] Confirm the temporary stage 01 policy's attachment status and detach it after its completed window.
- [ ] Review the workload IAM provisioning and role-write drafts before their short attachment windows. Rotate grants by stage; do not keep foundation and workload write permissions attached together.
- [x] Apply foundation stage 01: the Route 53 zone, configured evidence bucket and three retained log groups; the recovery plan had three additions only and the apply added three, for 11 resources total.
- [x] Scope the three later foundation service drafts to hosted zone `arn:aws:route53:::hostedzone/Z0153068M1DZTUZ2CE23`.
- [x] Apply foundation stage 02 after review and approval; verify AWS Config recording, CloudTrail logging and Security Hub FSBP `READY`. Record actual findings and any exceptions later.
- [x] Verify public delegation of `cheelong.xyz` to the four Route 53 nameservers using independent DNS resolvers.
- [x] Apply foundation stage 03 after delegation and verify that the `cheelong.xyz` ACM certificate is `ISSUED`.
- [x] Run read-only workload preflight with verified Singapore EKS/add-on/AMI, PostgreSQL and quota inputs; result `READY`. [ ] Recheck live cost and credits before each paid apply.
- [x] Apply the saved first workload target: `aws_kms_key.eks` and `aws_secretsmanager_secret.app` were created on 27 September in `ap-southeast-1`, with zero changes or destroys. The [temporary managed bootstrap policy](terraform/policies/workload/deployer-workload-bootstrap-temporary-draft.json) was attached for this apply.
- [x] Record the user's 27 September confirmation that `ContactFormWorkloadBootstrapTemporary` was detached from `contact-form-deployer` and deleted. Attachment slots still require review before later grants.
- [x] Prepare and statically review three exact-ARN KMS, EKS and secret/ECR policy copies under ignored `.local/`. The user reports all three attached; direct KMS and application-secret metadata reads succeeded. IAM simulation and review of those three current policy versions remain outstanding.
- [ ] Have the IAM administrator verify the current grants and remove the cluster-only `kms:CreateGrant` permission from the published version after reviewing ongoing access needs. `kms:CreateGrant` permits grantee choice. Validate/simulate the attached secret/ECR and other grants needed for the remaining workload.
- [x] Apply the separately approved cluster target. The initial 20-create plan partly failed on missing `ec2:DescribeAddressesAttribute` after VPC, four subnets, IGW, public route table/associations, two tagged EIPs and cluster role were created. The live tagged EIPs were verified, the exact missing read action was added and tested, both state entries were safely untainted, and a fresh seven-create, zero-change, zero-destroy retry plan applied. EKS `contact-form-eks` is `ACTIVE` at 1.36 with a private-only endpoint, five control-plane log types and Secrets encryption; both NAT gateways are `available` in separate AZs.
- [x] Record the user's confirmation that the default `ContactFormIAMProvisioning` JSON contains the live EKS issuer in all four OIDC statements and is attached to `contact-form-deployer`. A direct exact-ARN `GetOpenIDConnectProvider` read returned `NoSuchEntity`, consistent with read authorization and the provider not yet being created.
- [ ] Validate/simulate allowed and denied IAM cases, including OIDC provider creation and tag conditions, before the full workload apply. The read result above does not verify create or tag permissions.
- [ ] Create the remaining two managed node groups, EKS core add-ons, relay, ECR and Multi-AZ RDS. The network, two NAT gateways and private EKS cluster already exist.
- [ ] Guard against deploying to the wrong account or region. Give the controller, database setup Job, Flask and deployment identities only their required permissions.
- [ ] Let RDS generate and manage the master password. Pass secret identifiers (ARNs) through Terraform, keeping actual passwords out of Terraform inputs, outputs and state.
- [ ] Configure restrictive security groups, encryption, RDS backups, EKS control-plane logs, ECR scanning and appropriate access/audit logging. Open no inbound management ports on the relay.
- [ ] Provide non-secret foundation and workload Terraform outputs for Ansible.
- [x] Generate a refreshed full workload plan from post-cluster state: 50 additions, zero changes and zero destroys. No full apply or cost approval yet.
- [ ] Review the exact full plan and current cost/credits, obtain separate paid-apply approval, then apply and test the local tunnel to EKS. Keep certificate and hostname verification enabled.
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
- [ ] On rebuild, repeat the short-lived deployer managed bootstrap grant and key/app-secret target, remove the grant immediately afterward, then repeat the cluster target and exact KMS/secret/OIDC ARN review for new IDs. Keep saved plans mode 600 under ignored `.local/`, and obtain a fresh costed approval for each apply. Rebuild a fresh database, image and Ansible deployment.
- [ ] Verify that the previous test submission is absent, submit a new message and prove it is stored. Check for orphaned billable resources after teardown.

**Acceptance:** a complete destroy/rebuild starts with an empty database, accepts new submissions and requires no manual Console repairs. The current exact-issuer IAM policy and exact KMS/secret grants require an administrator to bind newly generated identifiers on every rebuild; this acceptance criterion remains open until a secure repeatable authorization path is implemented and demonstrated. Do not claim an unattended rebuild from the current runbook.

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
2. After retained prerequisites, state review and preflight, attach the temporary managed bootstrap policy to the deployer in a short IAM Console window, review the two-create saved plan and cost, and obtain separate apply approval. Remove the policy immediately after the target, bind exact key/secret ARNs, then review and separately approve the cluster target. Rebind all four OIDC grants from the cluster's live issuer before a fresh full workload plan.
3. Show the Secrets Manager secret metadata without exposing its password.
4. Build/push the image, open the management tunnel and run Ansible.
5. Show that the Ingress creates the ALB and the HTTPS website works.
6. Submit the form and show the saved PostgreSQL row.
7. Demonstrate the security controls and findings.

Declare retained prerequisites: domain/DNS, state backend, required foundation encryption resources and security evidence. Build the runtime infrastructure from zero with a new empty database. Rehearse the demo steps and count provisioning, deletion, setup, rehearsal and demo against the less-than-ten-hour total paid runtime target.

## 6. Progress and next action

**Verified locally (26 September 2026):** requirements review, architecture decisions, diagram, and application implementation. Dockerized PostgreSQL accepted a browser form submission and stored its row. Thirteen focused tests passed; the Gunicorn image ran as UID/GID 10001. The disposable local containers and network were removed with `make down`. Docker access from WSL was later rechecked and works. Full AWS rebuilds are planned to create a fresh database; snapshot restoration is excluded.

**AWS bootstrap completed (26 September 2026):** the scoped `ContactFormTerraformStateAccess` and temporary `ContactFormTerraformBucketSetup` inline policies were attached to the non-root deployer; the temporary policy was removed after bootstrap verification. Terraform created the S3 state bucket in account `203888389134`, Region `ap-southeast-1`. The first apply created the bucket but lacked `s3:GetBucketAcl`; after adding the provider's required read actions, the bucket was confirmed in AWS, its taint was safely removed from local state, and a second apply configured the five remaining settings. A fresh Terraform plan reported `No changes`. Direct AWS reads verified versioning, four public-access blocks, SSE-S3 `AES256`, enforced bucket ownership, and the deny-insecure-transport policy. The bootstrap state is local, Git-ignored, and restricted to owner-only mode `600`. At that 26 September verification, no foundation/workload state objects had been written; foundation remote state was created on 27 September, and the workload prefix was subsequently checked and found empty before first creation.

**Foundation stages 01–03 completed (27 September 2026):** Stage 01 created the Route 53 zone, evidence bucket and three retained CloudWatch log groups. Stage 02 enabled AWS Config, CloudTrail and Security Hub FSBP; live reads showed Config recording `SUCCESS`, CloudTrail logging with no delivery error, and FSBP `READY`. Stage 03 created the DNS-validated ACM certificate for `cheelong.xyz`; ACM returned `ISSUED`. Public DNS resolvers returned all four delegated Route 53 nameservers. Foundation resources and security services remain active until deliberate foundation teardown. The first real service logs and project-specific security findings still require evidence.

**First workload target (27 September 2026):** The workload S3 backend initialized successfully and its state prefix was empty before first creation. Read-only preflight returned `READY` for the pinned EKS 1.36 versions and AMIs, the Multi-AZ PostgreSQL class, two available AZs and an eight-vCPU Standard EC2 quota. The saved mode-600 target plan under ignored `.local/` applied successfully in `ap-southeast-1`: two creates (`aws_kms_key.eks` and `aws_secretsmanager_secret.app`), zero changes and zero destroys. Live AWS checks confirmed the symmetric customer-managed KMS key is `Enabled`, has rotation enabled and `Project`/`ManagedBy`/`Lifecycle` tags, and uses the default `Allow` key-policy statement for principal `arn:aws:iam::203888389134:root` on `kms:*` (account-root IAM delegation). The app secret exists with the `contact-form/app-` prefix and those tags; no secret-version resource was in the applied plan. Ansible templates and helpers passed local checks earlier; live ALB, RDS, database submission and teardown tests have not run.

**Permission status (27 September 2026):** The user confirmed that the temporary first-target policy was detached and deleted; the deployer CLI cannot independently list its attachments. The user reported exact-ARN KMS, EKS and `ContactFormWorkloadSecretECR` policies attached. Direct KMS and application-secret `DescribeSecret` metadata reads succeeded. The cluster target initially failed when `ContactFormWorkloadEC2Network` lacked `ec2:DescribeAddressesAttribute`; after the action was added, a direct call to that API succeeded and the retry applied. The tracked IAM template still contains inert OIDC placeholders. An ignored mode-600 copy with the live issuer ending `CA1A506A94A42855899E0176A0F40FE7` was prepared; the user confirmed the default `ContactFormIAMProvisioning` JSON now has that issuer in all four statements and is attached to `contact-form-deployer`. A direct `GetOpenIDConnectProvider` read on the exact ARN returned `NoSuchEntity`, showing the read was authorized and the provider does not yet exist. This does not validate OIDC create/tag access. An administrator must still validate/simulate allowed and denied IAM cases and review current attachment slots and grants. `kms:CreateGrant` permits grantee choice; review removal from the published policy version now that cluster creation completed. `iam:ListAttachedUserPolicies` and `access-analyzer:ValidatePolicy` are denied on the deployer. Foundation-stage write grants should be detached when no longer needed.

**Cluster target and recovery (27 September 2026):** The 20-create, zero-change, zero-destroy saved target plan was separately approved. Its first apply stopped after creating the VPC, two public and two private app subnets, internet gateway, public routing, two tagged EIPs and cluster IAM role because the EC2 provider refresh needed `ec2:DescribeAddressesAttribute`. Terraform marked both EIPs tainted. Their live allocation and project tags were checked; after the missing read action was authorized and verified, both EIPs were safely untainted in state. A fresh retry plan showed seven creates, zero changes and zero destroys; its apply completed. Direct AWS reads returned EKS `contact-form-eks` `ACTIVE`, version 1.36, public endpoint `false`, private endpoint `true`, five control-plane log types enabled and Secrets encryption. NAT gateways `nat-0a1db40e369242b73` and `nat-0753f6f9280cbc84d` were `available` in VPC `vpc-0681d87d2afde0705`, each in a different public subnet/AZ. No worker nodes, RDS instance, ALB or AWS application were created by this target.

**Full workload plan (27 September 2026):** After the issuer-bound provisioning policy and secret/ECR policy were reported attached, a refreshed Terraform plan succeeded with 50 additions, zero changes and zero destroys. This is proposed infrastructure only: no full apply, paid-apply approval, worker, RDS instance, ALB or AWS application exists yet. Review the exact plan and current costs before seeking separate approval.

**Reviewed local fixes (27 September 2026):** The image-specific database setup Job now creates when absent, reuses completion, waits on a running Job, and safely diagnoses and recreates a terminal failed Job. Foundation stage 01 applied the seven-day EKS and RDS log groups; the workload requires the foundation's RDS log-group output. The foundation evidence bucket has an applied scoped ALB log-delivery policy and `service-logs/alb/` lifecycle rules, passed through workload outputs to the Ingress annotation. These three code checkpoints passed independent review and were committed. The combined workstation/helper suite passed 30 offline tests, separate from the earlier 13 application tests; both Terraform roots passed formatting and validation, and Ansible deployment syntax and synthetic Ingress rendering passed. The controller inline policy rendered at 7,869 characters. None of these checks proves live Job recovery, IAM reconciliation, log delivery, credential reuse, or data preservation. Foundation remote state exists; the workload prefix was checked and found empty before the first apply. Follow the [backend and RDS log-group state handoff](terraform/README.md#backend-initialization) before the next apply.

**Verification, cost and cleanup (27 September 2026):** Preflight was `READY` before the first target; a fresh full stack needs six Standard EC2 vCPUs for the planned workers and relay, while simultaneous node updates could need fourteen. Direct AWS reads verified the live EKS cluster and two NAT gateways, but the separate runtime-inventory policy is not attached and absence of other out-of-state resources is not proved. EKS, two NAT gateways and their public IPv4 addresses are accruing charges now. The earlier cluster-stage allowance was about US$0.25–0.40 per hour before credits and variable usage; verify actual charges and credits in Billing. The $10 budget with a $5 actual-cost alert is not a spending cap. The deployer cannot read Budgets or Cost Explorer. The residual checker and teardown sequence remain untested against live workload resources.

**Current access and tooling (27 September 2026):** AWS CLI login returned `arn:aws:iam::203888389134:user/contact-form-deployer` in Singapore. Terraform initialized the workload S3 backend and applied the first target and recovered cluster target. Earlier workstation versions and the local Docker run were verified; recheck Docker before image publication. DNS delegation and ACM issuance are verified. The full application deployment is pending.

**Unresolved predeployment gates:** IAM simulation of allowed and denied OIDC create/tag and remaining service actions has not been verified. Review the successful 50-addition full plan against post-cluster state, current attachments and billing/credits, then obtain separate costed approval before applying it. The deployer lacks full inventory and billing reads, so account-wide resource absence and credits are not independently verified by CLI. Later stages still require Ansible deployment, security evidence, teardown and rebuild.

**Next action:** Review IAM simulations and the refreshed 50-addition full workload plan, confirm current costs and credits, then seek separate approval for workers, relay, RDS and other paid resources. EKS and two NAT gateways are already live; monitor charges and destroy the workload after the session. RDS, ALB, AWS application, teardown and rebuild remain pending.

## References

- [ALB creation from an EKS Ingress](https://docs.aws.amazon.com/eks/latest/userguide/alb-ingress.html)
- [Systems Manager port forwarding](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html)
- [RDS deletion and backup behaviour](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DeleteInstance.html)
- [Security Hub evaluation timing](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-standards-schedule.html)
