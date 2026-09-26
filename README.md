# AWS contact form on EKS

A Flask contact form for name, email, and message. PostgreSQL on Amazon RDS stores submissions; Amazon EKS runs the app. Terraform owns the AWS infrastructure, and Ansible owns the Kubernetes deployment.

**Status (26 September 2026):** The design, diagram, Flask form, PostgreSQL schema, local integration tests, and Docker image are present. Thirteen local tests passed, and a Dockerized browser submission was stored in disposable PostgreSQL. Terraform AWS resources, Ansible deployment tasks, and AWS deployment are not implemented or verified. The runbook below describes the intended AWS sequence; its apply and deployment commands cannot yet produce this environment.

## Architecture

![Contact form architecture](docs/architecture.png)

The environment is planned for `ap-southeast-1` across two Availability Zones (AZs):

- One internet-facing ALB uses the two public subnets. A NAT gateway in each public subnet provides outbound access for the worker in the same AZ.
- One EKS cluster has two managed node groups, each confined to one AZ with one EC2 worker. Two Flask replicas are spread across those workers.
- RDS PostgreSQL uses a Multi-AZ DB instance: one writer and one standby in separate private database subnets. The app connects to the writer endpoint, which can move after failover.
- The EKS Kubernetes API is private. Ansible runs on the local workstation and reaches it through an AWS Systems Manager (SSM) tunnel and a private EC2 relay. The relay has no public IP or inbound SSH rule.
- Terraform provisions the network, EKS, RDS, IAM, Secrets Manager, and supporting services. Ansible installs the AWS Load Balancer Controller and applies the Kubernetes Ingress. The controller creates **one** physical ALB; Terraform does not create a separate `aws_lb`.
- Route 53 and an ACM certificate are planned for the HTTPS hostname. Browser-to-ALB traffic uses HTTPS. ALB-to-pod traffic uses HTTP inside the VPC, restricted by security groups. Flask-to-RDS traffic must verify the RDS TLS certificate.

Secrets Manager holds two kinds of database credentials: the RDS-managed master secret and a separate, restricted application credential. The Flask pods read only the application secret using an IAM role for their Kubernetes service account (IRSA). The diagram leaves Secrets Manager unconnected to keep the traffic path readable; access is through the workers' same-AZ NAT gateways unless a VPC endpoint is added.

## Repository layout

Present now:

| Path | Purpose |
| --- | --- |
| `README.md` | Design, intended deployment sequence, and verification checklist |
| `ASSIGNMENT_PLAN.md` | Implementation decisions and task tracking |
| `docs/architecture.png` | High-level architecture diagram |
| `docs/security.md` | Template for actual controls, findings, and exceptions |
| `app/` | Flask form, SQL schema, Docker image, local Makefile, and integration tests; verified locally |
| `terraform/bootstrap/`, `terraform/foundation/`, `terraform/workload/` | Terraform root-module placeholders; no AWS resources |
| `ansible/` | Playbook and role placeholders; playbooks stop until implemented |
| `scripts/` | Placeholder for local deployment helpers |
| `.gitignore` | Excludes local secrets, state, plans, and generated files |

The Terraform and Ansible scaffolds mark their unfinished entry points. No AWS resources have been created by these files.

## Prerequisites and cost gate

Use a non-root AWS identity in account `203888389134` and Region `ap-southeast-1`. The workstation needs AWS CLI, Terraform, Ansible and required collections, kubectl, Helm, Python, Docker with WSL integration, PostgreSQL client tools, and the Session Manager plugin. Pin compatible tool and chart versions before the live rehearsal.

Run these **read-only checks** from the workstation:

```bash
aws sts get-caller-identity
aws configure list
aws --version
terraform version
ansible --version
kubectl version --client
helm version
docker version
session-manager-plugin --version
```

Check that the AWS identity is not root, the account ID is correct, Docker can reach its daemon, and the SSM plugin starts. `aws configure list` shows where credentials and the default Region come from; do not paste access keys into the repository.

**Do not run a Terraform apply until the Singapore cost estimate and teardown plan have been reviewed and approved.** Price the EKS cluster, two EC2 workers, two NAT gateways and data processing, the SSM relay, Multi-AZ RDS, ALB, Secrets Manager, ECR, Config/Security Hub, logs, DNS, public IPv4 addresses, and storage that remains after teardown. Check the account's credits, their expiry, and budget alerts. A US$10 monthly budget with a US$5 actual-cost email alert has been configured; it is not a hard spending cap. The full Singapore estimate and credit eligibility still need verification. Domain registration is a separate cost.

Never commit AWS credentials, Terraform state or plan files, kubeconfig, private keys, database passwords, or real contact-form submissions.

## Deployment runbook

This is the target order for the local-workstation deployment. The paths exist, but the Terraform roots have no resources and the Ansible playbooks stop intentionally. Complete and test each stage before using the apply or deployment commands. Review the actual plan and cost before each apply.

1. **Build and test the app locally.** Start a local PostgreSQL instance, run the Flask tests, submit a test form, and query the saved row. Build the container and confirm it runs as a non-root user. Local development may use a separate local database credential; production credentials come from Secrets Manager.
2. **Bootstrap remote Terraform state.** Create the encrypted, versioned S3 backend and locking through `terraform/bootstrap/`. Preserve the bootstrap state securely. Do not put secrets in Terraform inputs or outputs.
3. **Apply the persistent foundation.** Use `terraform/foundation/` for the state, DNS, retained logs/evidence, and other resources intended to survive a demo teardown. Inspect existing account-wide security services before trying to manage them.
4. **Apply the runtime infrastructure.** Use `terraform/workload/` for the VPC, two NAT gateways, private EKS cluster and worker groups, private relay, RDS Multi-AZ instance, application secret metadata, ECR, IAM roles, and security groups. Review the plan before applying it. Confirm Terraform outputs contain identifiers and endpoints, not secret values.
5. **Open the management tunnel.** Start an SSM port-forwarding session from the workstation through the private relay to the private EKS API. Use the tunnel-aware kubeconfig with TLS hostname verification intact. The exact script and local port will be fixed when implemented. Verify `kubectl get nodes` before running Ansible.
6. **Run Ansible locally.** The planned `ansible/deploy.yml` builds and pushes an immutable image to private ECR, installs the pinned AWS Load Balancer Controller, and applies the namespace, service accounts, RBAC, database setup Job, Deployment, ClusterIP Service, and HTTPS Ingress. The database Job creates the restricted app user and table on a fresh database; a rerun must reuse credentials and preserve rows. Ansible then waits for healthy ALB targets and creates the Route 53 alias.
7. **Verify the site and security controls.** Submit synthetic data through HTTPS, query its row from a controlled client inside the VPC, and record the evidence listed below. Run Ansible again and check that it makes no unwanted changes.

The intended Terraform invocation pattern, **after resource definitions and backend settings are implemented**, is:

```bash
terraform -chdir=terraform/bootstrap init
terraform -chdir=terraform/bootstrap plan
terraform -chdir=terraform/bootstrap apply

terraform -chdir=terraform/foundation init
terraform -chdir=terraform/foundation plan
terraform -chdir=terraform/foundation apply

terraform -chdir=terraform/workload init
terraform -chdir=terraform/workload plan
terraform -chdir=terraform/workload apply
```

After the deployment playbook is implemented and the tunnel is working, the intended command is:

```bash
ansible-playbook -i 'localhost,' -c local ansible/deploy.yml
```

Before the live demo, update these examples with the tested scripts, variables, pinned versions, and tunnel command.

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

These are **design targets, not claims of enabled controls**. Record actual values and dates after deployment.

| Area | Target and verification |
| --- | --- |
| Public access | Only the ALB accepts public inbound application traffic. EKS nodes, RDS, and the SSM relay have no public IP; the EKS Kubernetes API is private-only. Check subnet routes, public IPs, endpoint settings, and security groups. |
| Network rules | ALB accepts HTTPS (and HTTP only for redirect). App targets accept traffic from the ALB; RDS accepts PostgreSQL port 5432 only from the app or setup Job security group. Keep the relay's inbound management ports closed. |
| TLS | Route 53 hostname and ACM certificate at the ALB; HTTP from ALB to pods inside the VPC; verified RDS TLS from Flask. Test the public certificate and RDS certificate chain. |
| IAM and secrets | IRSA per workload, separate master/app secrets, no static AWS keys in pods, least-privilege SQL user. Inspect IAM policies and demonstrate that the app cannot read the master secret. |
| Kubernetes | Two replicas in different AZs; non-root process, no privilege escalation, dropped capabilities, health checks, resource requests/limits, and RBAC. Confirm with deployed pod specs and node AZ labels. |
| RDS and storage | Private, encrypted Multi-AZ RDS with backups during operation. Encrypt Terraform state and relevant logs; limit access to evidence and state buckets. |
| Logging | Enable selected EKS control-plane API, audit, authenticator, controller-manager, and scheduler logs; set retention and inspect CloudWatch log delivery. Review CloudTrail coverage without overwriting unrelated account configuration. |
| Security findings | Enable AWS Foundational Security Best Practices (FSBP) in Security Hub with the required AWS Config recording. Save dated findings, fixes, and remaining exceptions. A control still awaiting evaluation is not a pass. |

FSBP is the selected AWS foundational standard for this assignment. Do not claim CIS certification or that a control passed until it has been checked. Security Hub and Config may already be configured in the account; inspect them before Terraform takes ownership. Findings can take time to appear.

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

Also check the ALB target health, HTTPS form response, a submitted row through a temporary database client inside the VPC, and survival of that row after replacing a Flask pod. Re-run the Terraform plan and Ansible deployment to test repeatability. Capture FSBP findings with timestamps and distinguish newly pending checks from passes.

## Teardown and fresh rebuild

The runtime environment is disposable. **Destroying RDS deletes the contact-form submissions.** Use synthetic demo data only. RDS backups are enabled while it runs; the planned full demo teardown does not retain a final snapshot.

1. Stop submissions. Remove the Route 53 app alias and Kubernetes Ingress through the Ansible cleanup workflow.
2. Wait until the AWS Load Balancer Controller has deleted the ALB and target groups. Do not destroy EKS or the VPC first.
3. Remove the remaining Kubernetes resources, close the SSM tunnel, and destroy `terraform/workload/`. The planned command is `terraform -chdir=terraform/workload destroy`; review its targets before confirming.
4. Verify that RDS, EKS, worker instances, ALB, NAT gateways, the relay, and unused Elastic IPs are gone. Keep only the declared foundation: state, DNS/domain, and required security evidence.
5. Rebuild from Terraform, republish the image, and rerun Ansible. Use a fresh app secret name or another tested lifecycle strategy so Secrets Manager's deletion recovery window does not block recreation. Confirm the old demo row is absent and a new submission works.

Persistent foundation services can still cost money after runtime teardown. The final scripts and residual-cost check must be rehearsed before the demo.

## Reference documentation

- [AWS Load Balancer Controller and Ingress](https://docs.aws.amazon.com/eks/latest/userguide/aws-load-balancer-controller.html)
- [EKS service-account IAM roles](https://docs.aws.amazon.com/eks/latest/userguide/service-accounts.html)
- [RDS-managed master password](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-secrets-manager.html)
- [SSM Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html)
- [EKS control-plane logs](https://docs.aws.amazon.com/eks/latest/userguide/control-plane-logs.html)
- [Security Hub FSBP and Config](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-setup-prereqs.html)
