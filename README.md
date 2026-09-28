# AWS contact form on EKS

Deploy a Flask contact form from a local workstation. Amazon EKS runs the app, a private Multi-AZ Amazon RDS PostgreSQL instance stores submissions, and AWS Secrets Manager holds database credentials. Terraform provisions AWS infrastructure; Ansible deploys the Kubernetes application and Ingress.

![Two-AZ contact form architecture](docs/architecture.png)

The Ingress and AWS Load Balancer Controller create **one** public Application Load Balancer (ALB). Terraform does not create a separate ALB. Visitors use HTTPS; the ALB forwards to private Flask pods, which connect to private RDS with verified TLS. The Kubernetes API is private and is reached from the workstation through Systems Manager and a private relay. See [security controls and evidence](docs/security.md) for the actual boundaries, findings status, and demo exceptions.

## Prerequisites and cost gate

This checkout is configured for account `203888389134`, Region `ap-southeast-1`, domain `cheelong.xyz`, and non-root CLI profile `contact-form-deployer`. Use WSL with AWS CLI, Terraform, Python, Docker, kubectl, Helm, PostgreSQL client tools, Ansible, and the Session Manager plugin. The domain must delegate to the Terraform-managed Route 53 zone, and the foundation's ACM certificate must be `ISSUED` before deploying the Ingress. Another account or domain requires reviewing the backend, IAM, DNS, and policy scopes.

For an optional local form and PostgreSQL rehearsal before AWS work, use the short `make` sequence in [app/README.md](app/README.md). It creates no AWS resources.

From the repository root, check the identity and workstation before any apply:

```bash
cd /home/limch/projects/aws-contact-form-eks
export AWS_PROFILE=contact-form-deployer AWS_REGION=ap-southeast-1 AWS_DEFAULT_REGION=ap-southeast-1
aws sts get-caller-identity --query '{Account:Account,Arn:Arn}' --output json
aws configure get region --profile "$AWS_PROFILE"
aws --version && terraform version && kubectl version --client && helm version
docker info --format '{{.ServerVersion}}'
session-manager-plugin --version
```

The account must match `203888389134`; the ARN must identify `contact-form-deployer`, not root. If the AWS session expired, sign in with the configured deployer profile and repeat the identity check. `docker info` verifies WSL access to Docker. Install the pinned Python and Ansible dependencies if needed:

```bash
python3 -m venv "$HOME/.venvs/assignment"
source "$HOME/.venvs/assignment/bin/activate"
python -m pip install --no-cache-dir -r requirements-workstation.txt
ansible-galaxy collection install -r ansible/requirements.yml
```

The 28 September workload deployment and teardown were approved and completed. Before **each new paid deployment**, inspect its fresh saved plan, current Singapore prices, credits, quota, expected runtime, and teardown steps; present the estimate and obtain the owner's confirmation. The earlier planning estimate for a fully running stack was **US$0.50–1.00 per hour**, with a **US$10–20 allowance** for under ten total hours across setup, rehearsals, and demo, before credits and variable charges. Reprice before use; these are not quotes or limits. A configured **US$10 budget** and **US$5 actual-cost email alert** notify but do **not** stop spending. EKS, two NAT gateways, public IPv4, workers, Multi-AZ RDS, ALB, logs, and data transfer drive cost. The state bucket, DNS, evidence storage, logs, and security services can continue to cost money after workload teardown.

### IAM and service policy windows

IAM files under [terraform/policies/](terraform/policies/README.md) are **manual account-access prerequisites**; committing them does not attach them. An administrator must review the published default versions, effective grants, attachment slots, and any boundary or account policy. The temporary first-target grant, named workload service policies, `ContactFormIAMProvisioning`, and short-lived `ContactFormIAMRoleWrites` grant are described in the [Terraform runbook](terraform/README.md#iam-and-service-policy-windows). The workstation helper and residual-inventory policies have separate windows. An IAM denial is a stop-and-review point, not a reason to grant broad access. An administrator must publish the reviewed reusable policy versions once to replace copies bound to destroyed IDs. Future workload rebuilds need fresh plans and short attachment windows, but no generated-ID edits or per-run policy-version changes. The temporary key/secret creation grant remains a deliberate first-target window.

Keep `.local/` plans, verified version inputs, policy copies, kubeconfig, and alias ownership records private and out of Git. Do not put passwords, access keys, Terraform state, or real contact submissions in the repository.

## Deployment runbook

Run the following stages from the repository root. The retained foundation can be reused; the workload is rebuilt for each live session.

## 1. State and retained foundation

### Backend initialization

There are three Terraform roots: `bootstrap/` creates the S3 state bucket and keeps its own local state; `foundation/` holds DNS, certificate, logs, evidence, and security services; `workload/` holds the disposable runtime. Foundation and workload use different keys in the same versioned S3 bucket. Read the [backend and state reconciliation procedure](terraform/README.md#backend-initialization) before initializing from another workstation. Never treat an AWS read error as an empty state bucket.

**For this account:** bootstrap and foundation stages 01–03 already exist. Keep them and verify their state and outputs; do not replay earlier stage files, since their flags can propose deleting later-stage services.

```bash
umask 077
terraform -chdir=terraform/foundation init -input=false
terraform -chdir=terraform/foundation state list
terraform -chdir=terraform/foundation output -json
```

**For a genuinely fresh setup in this configured account only:** first attach the reviewed bucket setup and state-access policies, preserve the local bootstrap state securely, then plan and apply `terraform/bootstrap/`. Review the plan and cost before its apply:

```bash
umask 077
mkdir -p .local && chmod 700 .local
terraform -chdir=terraform/bootstrap init -input=false
BOOTSTRAP_PLAN="$PWD/.local/bootstrap.tfplan"
git check-ignore -q "$BOOTSTRAP_PLAN" &&
rm -f -- "$BOOTSTRAP_PLAN" &&
terraform -chdir=terraform/bootstrap plan -input=false -out="$BOOTSTRAP_PLAN" &&
terraform -chdir=terraform/bootstrap show -no-color "$BOOTSTRAP_PLAN"
```

After reviewing the new plan and obtaining approval for this fresh bootstrap setup:

```bash
terraform -chdir=terraform/bootstrap apply "$BOOTSTRAP_PLAN"
```

For an empty foundation state, use `01-base.tfvars`, then choose either the `existing-trail` or `project-trail` branch after checking account ownership of CloudTrail, AWS Config, and Security Hub. Apply stage 02, delegate the Route 53 nameservers at the registrar, verify public delegation, and apply stage 03 from the **same branch** to issue the certificate. A fresh foundation setup needs its own cost review and approval. Use a new saved plan at each stage:

```bash
terraform -chdir=terraform/foundation init -input=false
FOUNDATION_STAGE=stages/01-base.tfvars  # then 02-security-<branch> and 03-ready-<branch>
FOUNDATION_PLAN="$PWD/.local/foundation.tfplan"
git check-ignore -q "$FOUNDATION_PLAN" &&
rm -f -- "$FOUNDATION_PLAN" &&
terraform -chdir=terraform/foundation plan -input=false -var-file="$FOUNDATION_STAGE" -out="$FOUNDATION_PLAN" &&
terraform -chdir=terraform/foundation show -no-color "$FOUNDATION_PLAN"
```

After reviewing that stage's new plan and confirming its cost approval, apply it. Set the next stage file and repeat only after checking the prior stage's outputs:

```bash
terraform -chdir=terraform/foundation apply "$FOUNDATION_PLAN"
```

Check the exact stage filenames and DNS/certificate gates in the [foundation instructions](terraform/README.md#foundation-stages). Do not run a fresh-setup command against an already managed bucket or zone.

## 2. Version preflight and disposable workload

The workload example contains deliberately invalid version placeholders. Choose supported Singapore EKS, add-on, node-release, and relay AMI values, then let preflight verify them and write a mode-600 file. It also checks the effective EC2 vCPU quota and current capacity. The last observed quota was eight Standard On-Demand vCPUs; two `t3.medium` workers and one `t3.micro` relay need six. Recheck at deployment time.

```bash
source "$HOME/.venvs/assignment/bin/activate"
umask 077
mkdir -p .local && chmod 700 .local
cp .local/verified-workload.tfvars.json .local/workload-candidate.tfvars.json
chmod 600 .local/workload-candidate.tfvars.json
python3 scripts/preflight.py --profile "$AWS_PROFILE" --versions-file .local/workload-candidate.tfvars.json
```

The command above rechecks the frozen inputs on this workstation. For an entirely new workstation without the ignored verified file, begin with [the version-input example](terraform/workload/version-inputs.tfvars.json.example), choose supported regional versions and AMIs, and run the same preflight. Do not commit the verified file.

Continue only when preflight reports `READY`:

```bash
WORKLOAD_VARS="$PWD/.local/verified-workload.tfvars.json"
test -s "$WORKLOAD_VARS"
terraform -chdir=terraform/workload init -input=false
```

`READY` from preflight writes the verified file. Stop on `BLOCKED` or `INCOMPLETE`; do not use a previous file as proof of current readiness. Check workload state and the S3 backend before the first target. The two targets below are for a **new empty workload**; the 27 September plans must not be reused. The [two-target procedure](terraform/workload/README.md#two-target-first-creation-and-repeatable-iam) gives the exact IAM policy windows and plan checks.

Keep the same shell variables and verified input file through these Terraform stages. In a new terminal, set `AWS_PROFILE`, `AWS_REGION`, and `WORKLOAD_VARS` again before planning.

First, attach the reviewed **temporary** workload bootstrap policy. Plan only the KMS key and app-secret metadata; inspect that these are the only two creates. Confirm the plan fits the existing workload approval and remove the temporary policy immediately after applying, including after a partial failure:

```bash
FIRST_PLAN="$PWD/.local/workload-first.tfplan"
git check-ignore -q "$FIRST_PLAN" &&
rm -f -- "$FIRST_PLAN" &&
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" \
  -target=aws_kms_key.eks -target=aws_secretsmanager_secret.app -out="$FIRST_PLAN" &&
terraform -chdir=terraform/workload show -no-color "$FIRST_PLAN"
```

After reviewing the exact new plan and confirming it is within the approved scope and allowance:

```bash
terraform -chdir=terraform/workload apply "$FIRST_PLAN"
```

After the temporary policy is detached, verify the new key and secret ARNs and ownership tags against state and live metadata. Confirm the reusable KMS, EKS and secret/ECR policy versions have been published; no ARN replacement is required. Next, plan the cluster target. It can create paid network and EKS dependencies, including two NAT gateways, so review its full dependency list against the costed approval for this deployment:

```bash
CLUSTER_PLAN="$PWD/.local/workload-cluster.tfplan"
git check-ignore -q "$CLUSTER_PLAN" &&
rm -f -- "$CLUSTER_PLAN" &&
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" \
  -target=aws_eks_cluster.main -out="$CLUSTER_PLAN" &&
terraform -chdir=terraform/workload show -no-color "$CLUSTER_PLAN"
```

After reviewing this new plan and confirming it is within the approved scope and allowance:

```bash
terraform -chdir=terraform/workload apply "$CLUSTER_PLAN"
```

Read and verify the cluster's **current** OIDC issuer; Terraform uses it in exact pod-role trust:

```bash
CLUSTER_NAME="$(terraform -chdir=terraform/workload output -raw cluster_name)"
OIDC_ISSUER="$(aws eks describe-cluster --region "$AWS_REGION" --name "$CLUSTER_NAME" --query 'cluster.identity.oidc.issuer' --output text)"
printf '%s\n' "$OIDC_ISSUER"
```

The published `ContactFormIAMProvisioning` version already covers this regional 32-character issuer ID. Check its default version and attachment, and confirm there is no pre-existing untagged provider on that issuer path. No policy copy or version change is needed. Confirm the other reviewed service and short-lived role-write grants before planning the rest of the workload. The recent failed node-group creation showed that `iam:GetRole` for the EKS node-group service role needs verification in the effective policy; check it before another paid apply.

Only then create a **fresh full** plan. Review all proposed actions, especially worker count, private RDS settings, IAM, and any replacement or destroy action. Stop on an unexpected action or a cost estimate beyond the approved scope or allowance:

```bash
FULL_PLAN="$PWD/.local/workload.tfplan"
git check-ignore -q "$FULL_PLAN" &&
rm -f -- "$FULL_PLAN" &&
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" -out="$FULL_PLAN" &&
terraform -chdir=terraform/workload show -no-color "$FULL_PLAN"
```

After reviewing this new plan and confirming it is within the approved scope and allowance:

```bash
terraform -chdir=terraform/workload apply "$FULL_PLAN"
```

Before Ansible, show the created infrastructure and both secret identities without reading secret values:

```bash
aws eks describe-cluster --region ap-southeast-1 --name contact-form-eks \
  --query 'cluster.{status:status,public:resourcesVpcConfig.endpointPublicAccess,private:resourcesVpcConfig.endpointPrivateAccess}'
aws eks list-nodegroups --region ap-southeast-1 --cluster-name contact-form-eks
aws rds describe-db-instances --region ap-southeast-1 --db-instance-identifier contact-form-postgres \
  --query 'DBInstances[0].{status:DBInstanceStatus,engine:Engine,public:PubliclyAccessible,multiAZ:MultiAZ,encrypted:StorageEncrypted}'
aws rds describe-db-instances --region ap-southeast-1 --db-instance-identifier contact-form-postgres \
  --query 'DBInstances[0].MasterUserSecret.{arn:SecretArn,status:SecretStatus}'
aws secretsmanager describe-secret --region ap-southeast-1 \
  --secret-id "$(terraform -chdir=terraform/workload output -raw app_secret_arn)" \
  --query '{name:Name,arn:ARN}'
```

The RDS API shows the active RDS-managed master secret; the deployer cannot directly describe or read that master secret. The app's restricted SQL credential is created by the Ansible database setup Job in the next phase. Verify the new relay's tags and use its current Terraform output for the tunnel. Separate Kubernetes service-account IAM roles give Flask access only to the app secret and the setup Job access to the master secret.

## 3. Deploy through the private EKS API

The [Ansible playbook](ansible/README.md) publishes or reuses an immutable ECR image, installs the pinned AWS Load Balancer Controller, creates the restricted database user, and applies the two-replica Deployment, ClusterIP Service, and HTTPS Ingress. The controller creates the physical ALB. Once the Ingress reports its hostname, Ansible adds the DNS alias and waits for a successful public HTTPS readiness request.

In **terminal 1**, leave the authenticated SSM tunnel open:

```bash
cd /home/limch/projects/aws-contact-form-eks
source "$HOME/.venvs/assignment/bin/activate"
export AWS_PROFILE=contact-form-deployer
python3 scripts/open_tunnel.py
```

In **terminal 2**, use its TLS-verifying kubeconfig. `kubectl` verifies private API access and worker placement before Ansible changes the cluster:

```bash
cd /home/limch/projects/aws-contact-form-eks
source "$HOME/.venvs/assignment/bin/activate"
export AWS_PROFILE=contact-form-deployer
export KUBECONFIG="$PWD/.local/kubeconfig"
kubectl --request-timeout=8s get nodes -L topology.kubernetes.io/zone
ansible-playbook -i ansible/inventory.ini ansible/deploy.yml
```

## 4. Verify the application and security evidence

Inspect the live application, Ingress and public endpoint:

```bash
kubectl -n contact-form get deployment,pods,service,ingress -o wide
kubectl -n contact-form describe ingress contact-form
curl --head --max-time 15 http://cheelong.xyz/
curl --fail --silent --show-error https://cheelong.xyz/health/ready
```

Open `https://cheelong.xyz`, submit **synthetic** name, email, and message data, then prove the row reached PostgreSQL through the temporary readback Job:

```bash
ansible-playbook -i ansible/inventory.ini ansible/verify.yml -e demo_email=demo@example.com
ansible-playbook -i ansible/inventory.ini ansible/deploy.yml
```

An unchanged Ansible rerun should report `changed=0`. Check credential reuse and row persistence while the same RDS database exists. Record EKS/RDS/ALB settings, pod placement, log delivery, Config and actual Security Hub FSBP findings with timestamps in [security.md](docs/security.md). A `READY` standard subscription is not a passing control. The [read-only evidence policy](terraform/policies/README.md#read-only-demo-evidence-grant) is saved as a group inline policy. Current retained-resource findings are classified in `security.md`; the next live deployment still needs current EKS/RDS findings captured before teardown.

## 5. Ordered workload teardown

Stop submissions and **keep the SSM tunnel open** while Ansible removes the application DNS alias and Ingress and waits for the controller to delete the ALB. It then removes the controller and Kubernetes resources. Do not destroy EKS or the VPC while the ALB remains. This full cleanup path applies only after Ansible deployment; use the [partial-deployment procedure](terraform/workload/README.md#partial-deployment-teardown-before-ansible) if no Ingress or ALB was ever created.

```bash
ansible-playbook -i ansible/inventory.ini ansible/teardown.yml
```

After Ansible confirms that the ALB is gone, close the tunnel. From the repository root, create a fresh destroy plan with the verified version inputs:

```bash
umask 077
WORKLOAD_VARS="${WORKLOAD_VARS:-$PWD/.local/verified-workload.tfvars.json}"
DESTROY_PLAN="$PWD/.local/workload-destroy.tfplan"
git check-ignore -q "$DESTROY_PLAN" &&
rm -f -- "$DESTROY_PLAN" &&
terraform -chdir=terraform/workload plan -destroy -input=false -var-file="$WORKLOAD_VARS" -out="$DESTROY_PLAN" &&
terraform -chdir=terraform/workload show -no-color "$DESTROY_PLAN"
```

After reviewing the exact destroy plan and confirming it excludes foundation resources:

```bash
terraform -chdir=terraform/workload apply "$DESTROY_PLAN"
```

If a destroy waiter fails after AWS has already deleted a resource, use the [guarded partial-destroy recovery](terraform/workload/README.md#recovery-after-a-partial-destroy). Verify actual absence before reconciling state or releasing an exact project EIP; do not treat an access denial as proof of deletion. After Terraform completes, run the read-only residual inventory:

```bash
"$HOME/.venvs/assignment/bin/python" scripts/check_residual.py --profile contact-form-deployer
```

A full workload destroy deletes RDS and its demo submissions, EKS, NAT gateways, runtime secrets, and ECR; KMS deletion can remain scheduled. The residual checker returns `0` only for no actionable resources in its declared scope, `2` for found resources, and `1` when a read fails. Its latest complete read found no actionable workload resources under the project's names and tags; three project KMS keys were pending deletion. Check actual Billing separately because retained foundation and other resources remain outside this result. For another session, use **new plans, a current costed approval, current Terraform resource outputs, and the same ordered deploy/teardown sequence**. The reusable IAM policy versions need no generated-ID edits.

## Final cleanup of retained resources

Workload destroy deliberately leaves the state bucket and foundation. The Route 53 zone and ACM certificate may support later use of `cheelong.xyz`; evidence storage, log groups, Config, Security Hub, and CloudTrail have separate ownership and may keep charging. Review actual resource ownership, billing, S3 object versions, and a separate foundation/bootstrap teardown plan before removing them. Preserve unrelated account security services. The [residual inventory notes](scripts/README.md#residual-inventory-and-retained-costs) explain what the workload checker cannot prove.
