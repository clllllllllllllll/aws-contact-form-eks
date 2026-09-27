# AWS contact form on EKS

A Flask contact form for name, email, and message. PostgreSQL on Amazon RDS stores submissions; Amazon EKS runs the app. Terraform owns the AWS infrastructure, and Ansible owns the Kubernetes deployment.

**Status (27 September 2026):** The Flask form, PostgreSQL schema, and Docker image were verified locally; an earlier 13 application tests passed and a browser submission reached local PostgreSQL. The combined workstation/helper suite passed 30 offline tests. The Terraform state bucket and foundation stages 01–03 are applied in AWS: Route 53 delegation is verified, the ACM certificate is `ISSUED`, AWS Config is recording, CloudTrail is logging, and Security Hub FSBP is `READY`. The approved first workload target created `aws_kms_key.eks` and `aws_secretsmanager_secret.app` metadata. The separately approved cluster target is now applied. Direct AWS reads confirmed EKS `contact-form-eks` `ACTIVE` at 1.36 with a private-only API, all five control-plane log types and Secrets encryption enabled, and two NAT gateways `available`, one per AZ. The user confirmed the live-issuer OIDC provisioning policy's default JSON and deployer attachment, and the exact-ARN secret/ECR policy attachment; the OIDC-provider read returned `NoSuchEntity` while the secret metadata read succeeded. A refreshed full Terraform plan proposes 50 additions, zero changes and zero destroys, with no apply or cost approval yet. No workers, RDS, ALB or AWS application have been deployed; Ansible deployment remains pending.

**Cluster target recovery (27 September 2026):** The initial 20-create plan partly failed after creating the VPC, app/public subnets, internet gateway, public routing, two tagged EIPs and cluster IAM role because `ec2:DescribeAddressesAttribute` was denied. After the missing read action was added, both live tagged EIPs were verified and safely untainted. A fresh seven-create, zero-change, zero-destroy retry plan was applied. The cluster and two NAT gateways are live and accruing charges. An ignored mode-600 policy copy with the cluster's live OIDC issuer was prepared; the user confirmed all four statements in the published default JSON and attachment to `contact-form-deployer`. A direct exact-ARN `GetOpenIDConnectProvider` returned `NoSuchEntity`, consistent with authorized read and the provider not yet created. The user confirmed `ContactFormWorkloadSecretECR` attached, and direct `DescribeSecret` metadata succeeded. IAM simulation remains unverified. The 50-addition full plan still needs review, current cost assessment and separate apply approval.

## Architecture

![Contact form architecture](docs/architecture.png)

The environment is planned for `ap-southeast-1` across two Availability Zones (AZs):

- One internet-facing ALB uses the two public subnets. A NAT gateway in each public subnet provides outbound access for the worker in the same AZ.
- One EKS cluster has two managed node groups, each confined to one AZ with one EC2 worker. Two Flask replicas are spread across those workers.
- RDS PostgreSQL uses a Multi-AZ DB instance: one writer and one standby in separate private database subnets. The app connects to the writer endpoint, which can move after failover.
- The EKS Kubernetes API is private. Ansible runs on the local workstation and reaches it through an AWS Systems Manager (SSM) tunnel and a private EC2 relay. The relay has no public IP or inbound SSH rule.
- Terraform provisions the network, EKS, RDS, IAM, Secrets Manager, and supporting services. Ansible installs the AWS Load Balancer Controller and applies the Kubernetes Ingress. The controller creates **one** physical ALB; Terraform does not create a separate `aws_lb`.
- The Route 53 hosted zone is publicly delegated and the ACM certificate is `ISSUED`. Browser-to-ALB traffic will use HTTPS. ALB-to-pod traffic uses HTTP inside the VPC, restricted by security groups. Flask-to-RDS traffic must verify the RDS TLS certificate.

Secrets Manager will hold two kinds of database credentials: the RDS-managed master secret and a separate, restricted application credential. Only the application-secret metadata exists so far; the applied first target had no secret-version resource. The Flask pods read only the application secret using an IAM role for their Kubernetes service account (IRSA). The diagram leaves Secrets Manager unconnected to keep the traffic path readable; access is through the workers' same-AZ NAT gateways unless a VPC endpoint is added.

## Repository layout

Present now:

| Path | Purpose |
| --- | --- |
| `README.md` | Design, intended deployment sequence, and verification checklist |
| `ASSIGNMENT_PLAN.md` | Implementation decisions and task tracking |
| `docs/architecture.png` | High-level architecture diagram |
| `docs/security.md` | Planned controls, evidence commands, actual-findings register, and demo exceptions; dated screenshots will be added after live checks |
| `app/` | Flask form, SQL schema, Docker image, local Makefile, and integration tests; verified locally |
| `terraform/bootstrap/`, `terraform/foundation/`, `terraform/workload/` | Applied state-bucket bootstrap and foundation stages 01–03; workload first and cluster targets applied, with workers/RDS/ALB pending |
| `terraform/policies/` | Operator IAM policy drafts for manual review; see [policy notes](terraform/policies/README.md) |
| `terraform/README.md`, `ansible/README.md` | Terraform backend/stage instructions and Kubernetes deployment/cleanup commands |
| `ansible/` | Draft deploy/cleanup playbooks and manifests; locally syntax checked |
| `scripts/` | Draft tunnel, image publishing and ALB/DNS helpers |
| `.gitignore` | Excludes local secrets, state, plans, and generated files |

Foundation stages 01–03 and the first and cluster workload targets are applied and verified as described above. The remaining workload Terraform and Ansible deployment are locally validated but untested against EKS.

## Prerequisites and cost gate

Use a non-root AWS identity in account `203888389134` and Region `ap-southeast-1`. The workstation needs AWS CLI, Terraform, Ansible and required collections, kubectl, Helm, Python, Docker with WSL integration, PostgreSQL client tools, and the Session Manager plugin. Pin compatible tool and chart versions before the live rehearsal.

Run these **read-only checks** from the workstation:

```bash
aws sts get-caller-identity --profile contact-form-deployer
aws configure list --profile contact-form-deployer
aws --version
terraform version
ansible --version
kubectl version --client
helm version
docker version
session-manager-plugin --version
```

For a fresh Python environment, install the pinned workstation packages and Ansible collection:

    mkdir -p "$HOME/.venvs"
    python3 -m venv "$HOME/.venvs/assignment"
    source "$HOME/.venvs/assignment/bin/activate"
    python -m pip install --no-cache-dir -r requirements-workstation.txt
    ansible-galaxy collection install -r ansible/requirements.yml

The Botocore CRT extra is required for this workstation's AWS login method. The repository contains no AWS access keys.

Check that the AWS identity is not root, the account ID is correct, Docker can reach its daemon, and the SSM plugin starts. `aws configure list` shows where credentials and the default Region come from; do not paste access keys into the repository.

**Before every further paid foundation or workload apply, including a full workload apply or rebuild, update the Singapore estimate, check credit balance, eligibility and expiry, review the exact saved plan and teardown schedule, and obtain explicit user approval.** The EKS cluster, two NAT gateways and allocated public IPv4 addresses are live and charging now; the earlier cluster-stage allowance was about US$0.25–0.40 per hour before credits and variable usage, not an AWS bill or guarantee. The state bucket was approved separately; with small state files and ordinary runs, its expected cost is well under US$1 for the assignment week, not a fixed fee or cap. Price the remaining EC2 workers, SSM relay, Multi-AZ RDS, ALB, Secrets Manager, ECR, Config/Security Hub, logs, DNS, data transfer and storage that remains after teardown. Check the account's credits, their expiry, and budget alerts. A US$10 monthly budget with a US$5 actual-cost email alert has been configured; it is not a hard spending cap. The earlier Singapore planning allowance was about US$10–20 for the whole under-ten-hour activity before credits; it is neither a cap nor an AWS quote. Regional rates, credit eligibility, and expiry still need verification. Domain registration is a separate cost. Provisioning and deletion count toward runtime, and the retained foundation can continue to incur charges after workload destroy.

Never commit AWS credentials, Terraform state or plan files, kubeconfig, private keys, database passwords, or real contact-form submissions.

## Verified Terraform state bootstrap

The non-root `contact-form-deployer` user in account `203888389134` created the state bucket `aws-contact-form-eks-tfstate-203888389134-ap-southeast-1` in Singapore. Terraform reported no drift after apply. Direct AWS checks returned versioning `Enabled`, all four public-access blocks `true`, default SSE-S3 encryption `AES256`, and `BucketOwnerEnforced` ownership. The bucket policy denies S3 requests when `aws:SecureTransport` is `false`. At the 26 September bucket verification, no foundation or workload state objects had been written; both S3 state keys now contain applied resources. Recheck their current versions before initialization on another workstation.

For a fresh setup in this specific AWS account, attach the scoped `terraform/policies/bootstrap/bucket-setup-policy.json` and `terraform/policies/bootstrap/state-access-policy.json` as inline policies on an authorized non-root deployer before running:

```bash
cd /home/limch/projects/aws-contact-form-eks
umask 077
aws sts get-caller-identity --profile contact-form-deployer
terraform -chdir=terraform/bootstrap init
AWS_PROFILE=contact-form-deployer terraform -chdir=terraform/bootstrap plan -no-color
AWS_PROFILE=contact-form-deployer terraform -chdir=terraform/bootstrap apply -no-color
AWS_PROFILE=contact-form-deployer terraform -chdir=terraform/bootstrap plan -no-color
```

Confirm the account and review the plan and cost before typing `yes` at apply. The last plan should say `No changes`. The IAM policy files document manual account access setup; the S3 resource itself was created by Terraform. The bucket-setup policy was removed after bootstrap verification on 26 September 2026. Verify the actual state-access grant and backend access before relying on them. Restore the setup policy temporarily for deliberate bootstrap maintenance. A full bucket teardown needs a separately reviewed deletion procedure after foundation and workload are gone.

Bootstrap state stays local at `terraform/bootstrap/terraform.tfstate` and is excluded from Git. The state and backup were restricted to owner-only mode `600`; use `umask 077` before future local Terraform runs. Preserve it securely: the S3 backend makes **foundation and workload state** shareable between workstations, not bootstrap's own local state. Do not run bootstrap apply from another checkout without first restoring this state or deliberately importing the bucket. AWS recommends waiting 15 minutes after first enabling S3 versioning before writing state objects to the bucket. [S3 versioning guidance](https://docs.aws.amazon.com/AmazonS3/latest/userguide/manage-versioning-examples.html).

## Deployment runbook

Run the commands below from the local WSL workstation. Keep the same Git revision and verified workload version file for a laptop rehearsal. The [Terraform instructions](terraform/README.md), [Ansible instructions](ansible/README.md), and [security evidence register](docs/security.md) give the stage-specific checks.

This is the target order for the local-workstation deployment. Bootstrap, foundation stages 01–03 and the first and cluster workload targets are applied. Workers, relay, RDS, ALB and Ansible deployment remain pending. Complete and test each remaining stage before using its apply or deployment commands. Review the actual plan and cost before each apply.

1. **Build and test the app locally.** Start a local PostgreSQL instance, run the Flask tests, submit a test form, and query the saved row. Build the container and confirm it runs as a non-root user. Local development may use a separate local database credential; production credentials come from Secrets Manager.
2. **Bootstrap remote Terraform state (done for this account).** The encrypted, versioned S3 bucket is ready for foundation/workload state and S3 lockfiles. Preserve the local bootstrap state securely. Do not put secrets in Terraform inputs or outputs.
3. **Apply the persistent foundation (done for this account).** Use `terraform/foundation/` for DNS, retained logs/evidence, and other resources intended to survive a demo teardown. `terraform/bootstrap/` owns the state bucket; foundation stores its own state there. Inspect existing account-wide security services before trying to manage them.
4. **Finish the runtime infrastructure.** The first target created the KMS key and application-secret metadata; the recovered cluster target created the VPC, NAT gateways and private EKS cluster. Do not rerun either target plan against current state. The user confirmed the default `ContactFormIAMProvisioning` JSON contains the live issuer in all four OIDC grants and is attached, along with the exact-ARN secret/ECR policy. Direct exact-ARN OIDC-provider read authorization and secret metadata access were verified; OIDC provider creation and IAM simulation remain unverified. The tracked template remains inert. A refreshed full plan from post-cluster state succeeded with 50 additions, zero changes and zero destroys. Review its exact changes and current costs, complete IAM validation, and obtain separate approval before applying the remaining workers, relay, RDS Multi-AZ instance, ECR, IAM roles and security groups. Follow the [Terraform first-create procedure](terraform/README.md) and confirm outputs contain identifiers and endpoints, not secret values. On a fresh rebuild, repeat both approved targets and generate a new issuer-bound copy.
5. **Open the management tunnel.** Start an SSM port-forwarding session from the workstation through the private relay to the private EKS API. Use the tunnel-aware kubeconfig with TLS hostname verification intact. The drafted scripts/open_tunnel.py writes a TLS-verifying kubeconfig and forwards local port 8443. Verify `kubectl get nodes` before running Ansible.
6. **Run Ansible locally.** The drafted `ansible/deploy.yml` builds and pushes an immutable image to private ECR, installs the pinned AWS Load Balancer Controller, and applies the namespace, service accounts, RBAC, database setup Job, Deployment, ClusterIP Service, and HTTPS Ingress. The setup Job creates the restricted app user and table on a fresh database; reruns reuse a completed Job or safely recreate a failed one while the setup script preserves credentials and rows. Ansible then waits for healthy ALB targets and creates the Route 53 alias.
7. **Verify the site and security controls.** Submit synthetic data through HTTPS, query its row from a controlled client inside the VPC, and record the evidence listed below. Run Ansible again and check that it makes no unwanted changes.

Bootstrap and foundation stages 01–03 have been run and verified for this account; workload S3 state contains the first and cluster targets. Check local and S3 state before backend initialization on another workstation. **The stage 01 commands below are for an empty foundation state only.** On a laptop with existing foundation state, initialize the reconciled backend, inspect `terraform -chdir=terraform/foundation state list` and `terraform -chdir=terraform/foundation output -json`, retain the latest applied stage and trail branch, and skip stages already applied. An earlier stage file sets later flags to `false` and can propose deletion. The [Terraform backend and RDS log-group state handoff](terraform/README.md#backend-initialization) gives the ownership gates; if workload state already tracks either RDS log group, resolve ownership before any apply. These commands are for future use after cost approval and valid AWS login:

```bash
export AWS_PROFILE=contact-form-deployer
umask 077
terraform -chdir=terraform/foundation init
FOUNDATION_STAGE=stages/01-base.tfvars
terraform -chdir=terraform/foundation plan -input=false -var-file="$FOUNDATION_STAGE" -out=foundation.tfplan
terraform -chdir=terraform/foundation show -no-color foundation.tfplan
```

After reviewing that saved plan and obtaining explicit approval for this paid apply:

```bash
terraform -chdir=terraform/foundation apply foundation.tfplan
```

For a fresh build, after stage 01, check the Route 53 nameservers and set them at the domain registrar. Stages 02 and 03 are already applied in this account; skip the following stage blocks on the current state. Inspect any existing account-wide services before choosing the stage 02 trail branch:

```bash
terraform -chdir=terraform/foundation output -json name_servers
aws configservice describe-configuration-recorders --region ap-southeast-1
aws cloudtrail describe-trails --region ap-southeast-1
aws securityhub describe-hub --region ap-southeast-1
```

`describe-hub` may report that Security Hub is disabled; record the result. Choose `existing-trail` only if a suitable management-event trail already exists. Otherwise review the project-trail cost and ownership. For an **unapplied** stage 02, plan with the selected file, inspect it, update the cost review and get approval before applying the saved plan:

```bash
TRAIL_MODE=existing-trail  # or project-trail, after inspecting the account
FOUNDATION_STAGE="stages/02-security-${TRAIL_MODE}.tfvars"
terraform -chdir=terraform/foundation plan -input=false -var-file="$FOUNDATION_STAGE" -out=foundation.tfplan
terraform -chdir=terraform/foundation show -no-color foundation.tfplan
```

After reviewing this exact stage 02 plan and receiving explicit cost approval:

```bash
terraform -chdir=terraform/foundation apply foundation.tfplan
```

Check public `cheelong.xyz` NS delegation against all Route 53 nameservers, ignoring case and trailing dots. An AWS hosted-zone output alone does not prove registrar delegation. Once the public records match, use the **same trail branch** for an unapplied certificate stage. Review and approve its saved plan separately:

```bash
curl --fail --silent --show-error 'https://dns.google/resolve?name=cheelong.xyz&type=NS' | python3 -m json.tool
FOUNDATION_STAGE="stages/03-ready-${TRAIL_MODE}.tfvars"
terraform -chdir=terraform/foundation plan -input=false -var-file="$FOUNDATION_STAGE" -out=foundation.tfplan
terraform -chdir=terraform/foundation show -no-color foundation.tfplan
```

After reviewing this exact stage 03 plan and receiving explicit cost approval:

```bash
terraform -chdir=terraform/foundation apply foundation.tfplan
CERT_ARN="$(terraform -chdir=terraform/foundation output -raw certificate_arn)"
aws acm describe-certificate --region ap-southeast-1 --certificate-arn "$CERT_ARN" --query 'Certificate.{domain:DomainName,status:Status,validation:DomainValidationOptions[*].ValidationStatus}'
```

The certificate is `ISSUED` for this account. On a workstation with an already applied foundation, skip completed stages and retain the **latest applied** stage file; an earlier file can plan to disable later features. Before further workload creation or a fresh rebuild, use the [read-only preflight](terraform/workload/README.md) to choose currently compatible versions and check quota. On a first run, make a local candidate from the example, replace its invalid placeholders with verified Singapore versions and AMIs, then run:

```bash
mkdir -p .local
chmod 700 .local
cp terraform/workload/version-inputs.tfvars.json.example .local/workload-candidate.tfvars.json
chmod 600 .local/workload-candidate.tfvars.json
# Edit .local/workload-candidate.tfvars.json with actual supported versions and AMIs.
python3 scripts/preflight.py --profile contact-form-deployer --versions-file .local/workload-candidate.tfvars.json
```

Only `READY` creates an ignored mode-600 `.local/verified-workload.tfvars.json`; `BLOCKED` or `INCOMPLETE` stops deployment. The fresh stack needs 6 free Standard On-Demand EC2 vCPUs for two workers and the relay. Preflight also reports 14-vCPU simultaneous managed-node update headroom separately. Keep the verified file through destroy and securely carry it to the rehearsal workstation. After inspecting local and remote state, initialize the reconciled workload backend:

```bash
terraform -chdir=terraform/workload init
WORKLOAD_VARS="$PWD/.local/verified-workload.tfvars.json"
```

Before a full workload plan, follow [both required target stages](terraform/README.md). In this account, both targets are already in workload S3 state. The temporary first-target policy removal was user-confirmed. The original 20-create cluster plan partly failed; after the specific EC2 read permission fix, a new seven-create retry plan applied successfully. Do not reuse either saved target plan. The user confirmed the default OIDC policy JSON and attachment, plus the exact-ARN secret/ECR attachment. The direct OIDC-provider read returned `NoSuchEntity` because the provider is not yet created; secret metadata read succeeded. IAM simulation remains unverified. A refreshed full plan already succeeded with **50 additions, zero changes and zero destroys**, but no full apply or cost approval has occurred. The key, app secret, network, NAT gateways and cluster must remain in state without replacement. Review the exact plan and current costs before approval. On a fresh rebuild, repeat both targets with new approvals and regenerate the issuer-bound OIDC review copy before this full-plan command:

```bash
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" -out=workload.tfplan
terraform -chdir=terraform/workload show -no-color workload.tfplan
```

After reviewing this new full plan and obtaining explicit approval for the paid workload apply:

```bash
terraform -chdir=terraform/workload apply workload.tfplan
```

After the workload is applied and the tunnel works, the draft deployment command is:

```bash
ansible-playbook -i ansible/inventory.ini ansible/deploy.yml
```

The Ansible runbook gives the two-terminal tunnel/deploy sequence. These commands still require a live rehearsal and cost approval before use.

## Drafted workstation deployment

In terminal 1, activate the assignment virtualenv and open the SSM tunnel:

    cd /home/limch/projects/aws-contact-form-eks
    source "$HOME/.venvs/assignment/bin/activate"
    export AWS_PROFILE=contact-form-deployer
    python3 scripts/open_tunnel.py

In terminal 2, use the generated kubeconfig and run Ansible:

    cd /home/limch/projects/aws-contact-form-eks
    source "$HOME/.venvs/assignment/bin/activate"
    export AWS_PROFILE=contact-form-deployer
    export KUBECONFIG="$PWD/.local/kubeconfig"
    kubectl get nodes -L topology.kubernetes.io/zone
    ansible-playbook -i ansible/inventory.ini ansible/deploy.yml

The first command checks access to the private EKS API and worker placement. The playbook publishes or reuses an immutable image digest, installs the controller, initializes the restricted database user, applies the app and Ingress, creates the DNS alias and waits for HTTPS readiness. For cleanup after a full deployment, keep the tunnel open and run ansible-playbook -i ansible/inventory.ini ansible/teardown.yml before reviewing the Terraform destroy plan. See ansible/README.md for the exact sequence and safety checks. This sequence is drafted, not live-tested.

## IAM and database credentials

| Identity | Intended access |
| --- | --- |
| Local deployment identity | Non-root principal for Terraform, image publishing, EKS authentication, SSM session start, and Ansible operations. Scope it to this environment where AWS permits; record any broader provisioning permissions needed. |
| EKS worker role | Node registration, required ECR image pulls, and node functions. Do not give it the Flask database secret. |
| AWS Load Balancer Controller service account | Dedicated IAM role for ALB, target group, and related AWS changes. Scope resources to this cluster using supported tags and conditions. |
| Flask service account | IRSA role allowed to read only the application secret with `secretsmanager:GetSecretValue`; add `kms:Decrypt` only if its encryption key requires it. No RDS master-secret permission. |
| Database setup Job | Separate, short-lived access to the RDS-managed master secret and the application secret. It creates/reuses the restricted SQL user and schema without writing passwords to logs, Terraform state, or manifests. |
| Private SSM relay | Instance role needed for SSM management. No public IP, inbound SSH, or app database access. |
| Kubernetes deployer and app | RBAC grants only the operations each needs. The Flask service account does not need general Kubernetes API permissions. |

RDS generates and stores the master password in Secrets Manager. The app uses a different SQL user with only the database privileges it needs for submissions and health checks; schema changes belong to the setup Job. Terraform passes secret ARNs, not secret values. Ansible and Kubernetes manifests must not contain plaintext passwords.

## Planned security controls and evidence

These are **runtime design targets**. AWS Config recording, CloudTrail logging, and Security Hub FSBP `READY` were verified for the foundation on 27 September; record deployment-specific values and dates after the runtime is built.

| Area | Target and verification |
| --- | --- |
| Public access | Only the ALB accepts public inbound application traffic. EKS nodes, RDS, and the SSM relay have no public IP; the EKS Kubernetes API is private-only. Check subnet routes, public IPs, endpoint settings, and security groups. |
| Network rules | ALB accepts HTTPS (and HTTP only for redirect). The shared worker security group accepts port 8000 from the ALB group and has self-referencing all-protocol ingress. RDS accepts port 5432 from that shared worker group, not only from the Flask or setup pods. Keep the relay's inbound management ports closed. |
| TLS | Route 53 hostname and ACM certificate at the ALB; HTTP from ALB to pods inside the VPC; verified RDS TLS from Flask. Test the public certificate and RDS certificate chain. |
| IAM and secrets | IRSA per workload, separate master/app secrets, no static AWS keys in pods, least-privilege SQL user. Inspect IAM policies and demonstrate that the app cannot read the master secret. |
| Kubernetes | Two replicas in different AZs; non-root process, no privilege escalation, dropped capabilities, health checks, resource requests/limits, and RBAC. Confirm with deployed pod specs and node AZ labels. |
| RDS and storage | Private, encrypted Multi-AZ RDS with backups during operation. Encrypt Terraform state and relevant logs; limit access to evidence and state buckets. |
| Logging | Foundation retains EKS control-plane and RDS PostgreSQL/upgrade log groups for seven days. The Ingress requests ALB access logs in the evidence bucket under `service-logs/alb/`; verify a recent real `.log.gz` object through [metadata-only ALB log checks](docs/security.md#alb-access-log-verification), not just the test file. Review CloudTrail coverage without overwriting unrelated account configuration. |
| Security findings | AWS Config is recording and Security Hub FSBP is `READY`; save dated findings, fixes, and remaining exceptions. A control still awaiting evaluation is not a pass. |

FSBP is the selected AWS foundational standard for this assignment. Do not claim CIS certification or that a control passed until it has been checked. Security Hub and Config are active in the applied foundation; inspect their account ownership before future changes. Findings can take time to appear.

## End-to-end verification

Use non-secret Terraform outputs to supply `CLUSTER_NAME`, `DB_ID`, and `APP_SECRET_ARN`. These commands inspect metadata and settings; none retrieves a password.

```bash
aws eks describe-cluster --region ap-southeast-1 --name "$CLUSTER_NAME" --query 'cluster.{status:status,public:resourcesVpcConfig.endpointPublicAccess,private:resourcesVpcConfig.endpointPrivateAccess,logging:logging.clusterLogging}'
aws eks list-nodegroups --region ap-southeast-1 --cluster-name "$CLUSTER_NAME"
aws rds describe-db-instances --region ap-southeast-1 --db-instance-identifier "$DB_ID" --query 'DBInstances[0].{status:DBInstanceStatus,public:PubliclyAccessible,multiAZ:MultiAZ,encrypted:StorageEncrypted}'
aws secretsmanager describe-secret --region ap-southeast-1 --secret-id "$APP_SECRET_ARN" --query '{name:Name,arn:ARN,created:CreatedDate}'
kubectl get nodes -L topology.kubernetes.io/zone
kubectl -n contact-form get deployment,pods,service,ingress -o wide
aws securityhub get-enabled-standards --region ap-southeast-1
```

Also check the ALB target health, HTTPS form response, a submitted row through the short-lived readback Job inside the VPC, and survival of that row after replacing a Flask pod. After submitting a synthetic address such as `demo@example.com`, run `ansible-playbook -i ansible/inventory.ini ansible/verify.yml -e demo_email=demo@example.com` while the private API tunnel remains open. The Job uses the setup role and prints at most five matching rows; use synthetic data only. Re-run the Terraform plan and Ansible deployment to test repeatability. Capture FSBP findings with timestamps and distinguish newly pending checks from passes.

## Teardown and fresh rebuild

The runtime environment is disposable. **Destroying RDS deletes the contact-form submissions.** Use synthetic demo data only. RDS backups are enabled while it runs; the planned full demo teardown does not retain a final snapshot.

The numbered sequence below is for a fully deployed app. For the current partial deployment (EKS and two NAT gateways, without workers, relay, RDS, app or ALB), follow the [partial deployment teardown](terraform/workload/README.md#partial-deployment-teardown-current-cluster-only-state): check Terraform state and scoped AWS/Console inventory for any Ingress, ALB, app, RDS or app DNS alias. Stop if a required read is denied or an unexpected resource exists. Skip Ansible cleanup only after absence is verified; then review a fresh full workload destroy plan, apply the approved saved plan, inspect residuals and review retained foundation costs.

1. Stop submissions. Remove the Route 53 app alias and Kubernetes Ingress through the Ansible cleanup workflow.
2. Wait until the AWS Load Balancer Controller has deleted the ALB and target groups. Do not destroy EKS or the VPC first.
3. Remove the remaining Kubernetes resources, close the SSM tunnel, and destroy `terraform/workload/`. From the repository root, set `WORKLOAD_VARS="$PWD/.local/verified-workload.tfvars.json"`, then run `terraform -chdir=terraform/workload plan -destroy -input=false -var-file="$WORKLOAD_VARS" -out=workload-destroy.tfplan`. Review with `terraform -chdir=terraform/workload show -no-color workload-destroy.tfplan`; only then run `terraform -chdir=terraform/workload apply workload-destroy.tfplan`. The saved plan carries the verified version inputs.
4. Run `python3 scripts/check_residual.py --profile contact-form-deployer` after destroy. Exit 0 means no actionable remnants within its declared Singapore names and tags; a workload KMS key in `PendingDeletion` is reported separately in `expected_pending_cleanup`. Exit 2 means actionable remnants remain; exit 1 means a read failed and cleanup is unproven. Other accounts/Regions and resources outside those names and tags, including some untagged or manual assets, are outside the check; exit 0 is not a zero-bill claim. Review retained foundation charges separately under [final cleanup](#final-cleanup-of-retained-resources).
5. Recheck the paid-apply gate before **each target and full rebuild apply**; repeat [both target stages and exact KMS/secret/OIDC ARN rebinding](terraform/README.md) for the new IDs. Regenerate the ignored OIDC review copy from the inert template; never reuse the old issuer. Generate a fresh full plan from the post-cluster state, apply only after review and approval, republish the image, and rerun Ansible. Confirm the old demo row is absent and a new submission works.

Persistent foundation services can still cost money after runtime teardown. The residual-cost check is drafted but has not been run against AWS. It must be rehearsed before the demo. The [security evidence](docs/security.md) page records actual findings.

## Final cleanup of retained resources

Workload destroy does not remove the state bucket or foundation. Before deciding on final removal, inspect the reviewed foundation plan and actual account ownership. The Route 53 zone and ACM certificate support `cheelong.xyz`; do not remove DNS that the owner still needs. The evidence bucket and seven-day EKS/RDS log groups can retain data and incur charges after the workload is gone. Config, Security Hub and CloudTrail may be account-wide or pre-existing; preserve unrelated controls. The versioned state bucket can retain old state versions and lockfiles, and its local bootstrap state must be preserved securely. Review retained RDS backups and snapshots, EBS volumes and snapshots, NAT gateways/EIPs, ECR images, secrets and the workload KMS key separately; the scoped residual checker cannot prove a zero bill. Final foundation/backend teardown needs its own ownership decision, saved plan, cost review and approval.

## Reference documentation

- [AWS Load Balancer Controller and Ingress](https://docs.aws.amazon.com/eks/latest/userguide/aws-load-balancer-controller.html)
- [EKS service-account IAM roles](https://docs.aws.amazon.com/eks/latest/userguide/service-accounts.html)
- [RDS-managed master password](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-secrets-manager.html)
- [SSM Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html)
- [EKS control-plane logs](https://docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html)
- [Security Hub FSBP and Config](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-setup-prereqs.html)
