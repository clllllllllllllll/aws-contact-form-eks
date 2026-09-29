# AWS contact form on EKS

Terraform provisions a two-AZ VPC, private EKS workers, private Multi-AZ PostgreSQL RDS, Secrets Manager and supporting AWS services. Ansible builds the Flask image, deploys two pods and an Ingress, and installs the AWS Load Balancer Controller that creates the **single public ALB**. When deployed, the application is served at `https://cheelong.xyz/`.

![Contact form architecture](docs/architecture.png)

## 1. Prerequisites

This repository is configured for account `203888389134`, Region `ap-southeast-1`, IAM profile `contact-form-deployer`, and domain `cheelong.xyz`. Use WSL with AWS CLI, Terraform, Python 3, Docker, Ansible, kubectl, Helm and the Session Manager plugin. The profile must have the reviewed policies in [terraform/policies/](terraform/policies/README.md); policy files alone do not grant access. In this account, the CLI evidence and scoped self-attachment group policies are installed. The temporary managed `ContactFormWorkloadBootstrapTemporary` policy is attached only around the first workload target.

On a new workstation, run this from the repository root to install dependencies:

```bash
python3 -m venv "$HOME/.venvs/assignment"
source "$HOME/.venvs/assignment/bin/activate"
python -m pip install --no-cache-dir -r requirements-workstation.txt
ansible-galaxy collection install -r ansible/requirements.yml
```

Then run from the repository root:

```bash
cd /home/limch/projects/aws-contact-form-eks
source "$HOME/.venvs/assignment/bin/activate"
umask 077
export AWS_PROFILE=contact-form-deployer AWS_REGION=ap-southeast-1 AWS_DEFAULT_REGION=ap-southeast-1
export AWS_PAGER=""
aws sts get-caller-identity --query '{Account:Account,Arn:Arn}' --output json
aws configure get region --profile "$AWS_PROFILE"
docker info --format '{{.ServerVersion}}'
```

Stop unless the account, IAM user and Region match.

**Paid deployment gate:** Estimate current Singapore costs for EKS, workers, NAT, Multi-AZ RDS, ALB and supporting services. Check AWS credits, EC2 vCPU quota, expected runtime and each saved Terraform plan. Obtain the owner's explicit approval before the first paid apply; a budget alert does not stop charges. Keep all plans, Terraform state, verified inputs and kubeconfig out of Git. Never use `-auto-approve` or reuse an old plan.

## 2. Bootstrap and foundation

The three Terraform roots are `terraform/bootstrap` (S3 state bucket), `terraform/foundation` (retained DNS, certificate, logs and security services), and `terraform/workload` (disposable runtime). Foundation and workload use separate S3 state keys.

**Existing configured account:** Bootstrap and foundation stages 01–03 are already deployed. Verify, then continue to section 3. Do not apply an early foundation stage file to the retained foundation.

```bash
terraform -chdir=terraform/foundation init -input=false
terraform -chdir=terraform/foundation state list
terraform -chdir=terraform/foundation output -json
CERT_ARN="$(terraform -chdir=terraform/foundation output -raw certificate_arn)"
aws acm describe-certificate --certificate-arn "$CERT_ARN" \
  --query 'Certificate.{Domain:DomainName,Status:Status}' --output json
```

Continue only when the foundation state contains the expected zone, certificate and security services and the certificate is `ISSUED`.

**Fresh setup only:** An administrator first publishes the reviewed bootstrap state and foundation IAM policies from [terraform/policies](terraform/policies/README.md). Create the state bucket with a fresh, reviewed, approved plan:

```bash
mkdir -p .local
chmod 700 .local
terraform -chdir=terraform/bootstrap init -input=false
BOOTSTRAP_PLAN="$PWD/.local/$(date -u +%Y%m%dT%H%M%SZ)-bootstrap.tfplan"
terraform -chdir=terraform/bootstrap plan -input=false -out="$BOOTSTRAP_PLAN"
terraform -chdir=terraform/bootstrap show -no-color "$BOOTSTRAP_PLAN"
```

After reviewing the plan and obtaining the fresh bootstrap cost approval:

```bash
terraform -chdir=terraform/bootstrap apply "$BOOTSTRAP_PLAN"
```

**First-time setup only.** The current account already has this foundation; go to section 3 for a redeploy. On a new account, review each saved plan and its cost before running the apply command beneath it. Do not run the next stage until the previous one succeeds.

**Stage 01 — base DNS zone, evidence bucket and log groups:**

```bash
terraform -chdir=terraform/foundation init -input=false
FOUNDATION_PLAN="$PWD/.local/$(date -u +%Y%m%dT%H%M%SZ)-foundation-01.tfplan"
terraform -chdir=terraform/foundation plan -input=false -var-file=stages/01-base.tfvars -out="$FOUNDATION_PLAN"
terraform -chdir=terraform/foundation show -no-color "$FOUNDATION_PLAN"
```

After reviewing and approving this plan, run `terraform -chdir=terraform/foundation apply "$FOUNDATION_PLAN"`. Get the hosted-zone nameservers with `terraform -chdir=terraform/foundation output -json name_servers` and set them at the domain registrar.

**Stage 02 — Config, Security Hub and CloudTrail:** Check whether these account-wide services already exist. The command below uses the project-managed CloudTrail branch. If this account has an existing trail, use `stages/02-security-existing-trail.tfvars` here and the matching existing-trail file in stage 03.

```bash
FOUNDATION_PLAN="$PWD/.local/$(date -u +%Y%m%dT%H%M%SZ)-foundation-02.tfplan"
terraform -chdir=terraform/foundation plan -input=false -var-file=stages/02-security-project-trail.tfvars -out="$FOUNDATION_PLAN"
terraform -chdir=terraform/foundation show -no-color "$FOUNDATION_PLAN"
```

After reviewing and approving this plan, run `terraform -chdir=terraform/foundation apply "$FOUNDATION_PLAN"`.

**Stage 03 — certificate and final foundation settings:** Verify the domain's public nameservers match the Route 53 output before planning this stage.

```bash
FOUNDATION_PLAN="$PWD/.local/$(date -u +%Y%m%dT%H%M%SZ)-foundation-03.tfplan"
terraform -chdir=terraform/foundation plan -input=false -var-file=stages/03-ready-project-trail.tfvars -out="$FOUNDATION_PLAN"
terraform -chdir=terraform/foundation show -no-color "$FOUNDATION_PLAN"
```

After reviewing and approving this plan, run `terraform -chdir=terraform/foundation apply "$FOUNDATION_PLAN"`. Run the ACM check above and wait for `ISSUED`. See [foundation stage details](terraform/README.md#foundation-stages) for account ownership and DNS troubleshooting.

## 3. Deploy the disposable workload

Initialize the workload state and confirm it is empty before a fresh build:

```bash
terraform -chdir=terraform/workload init -input=false
terraform -chdir=terraform/workload state list
```

Prepare current EKS/add-on, node-release, relay AMI and RDS inputs. On this workstation, copy the previous verified file. On a new workstation, use `cp terraform/workload/version-inputs.tfvars.json.example .local/workload-candidate.tfvars.json` instead, then fill its placeholder values with current Singapore choices before preflight:

```bash
mkdir -p .local
chmod 700 .local
cp .local/verified-workload.tfvars.json .local/workload-candidate.tfvars.json
chmod 600 .local/workload-candidate.tfvars.json
python scripts/preflight.py --profile "$AWS_PROFILE" --versions-file .local/workload-candidate.tfvars.json
export WORKLOAD_VARS="$PWD/.local/verified-workload.tfvars.json"
test -s "$WORKLOAD_VARS"
```

Continue only on `READY`, with two AZs and at least six free Standard EC2 vCPUs. Create unique plan filenames in the same shell:

```bash
RUN_TAG="$(date -u +%Y%m%dT%H%M%SZ)"
FIRST_PLAN="$PWD/.local/$RUN_TAG-first.tfplan"
CLUSTER_PLAN="$PWD/.local/$RUN_TAG-cluster.tfplan"
FULL_PLAN="$PWD/.local/$RUN_TAG-full.tfplan"
```

**First target — EKS encryption key and empty application-secret entry.** The administrator must have published the reviewed Bootstrap policy. Attach it to this deployer, then verify the exact name:

```bash
BOOTSTRAP_POLICY_ARN=arn:aws:iam::203888389134:policy/ContactFormWorkloadBootstrapTemporary
aws iam get-policy --policy-arn "$BOOTSTRAP_POLICY_ARN" \
  --query 'Policy.{ARN:Arn,Version:DefaultVersionId}' --output json
aws iam attach-user-policy --user-name contact-form-deployer --policy-arn "$BOOTSTRAP_POLICY_ARN"
aws iam list-attached-user-policies --user-name contact-form-deployer \
  --query "AttachedPolicies[?PolicyArn=='${BOOTSTRAP_POLICY_ARN}'].PolicyName" --output json
```

Plan and run the concise read-only plan check:

```bash
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" \
  -target=aws_kms_key.eks -target=aws_secretsmanager_secret.app -out="$FIRST_PLAN"
python scripts/check_plan.py first "$FIRST_PLAN"
```

The checker must print `PLAN CHECK PASS`. If it fails, stop and inspect `terraform -chdir=terraform/workload show -no-color "$FIRST_PLAN"`. After the current costed deployment is approved, apply the saved plan:

```bash
terraform -chdir=terraform/workload apply "$FIRST_PLAN"
```

**Always detach Bootstrap after this target, including after a failed plan or apply:**

```bash
aws iam detach-user-policy --user-name contact-form-deployer --policy-arn "$BOOTSTRAP_POLICY_ARN"
aws iam list-attached-user-policies --user-name contact-form-deployer \
  --query "AttachedPolicies[?PolicyArn=='${BOOTSTRAP_POLICY_ARN}'].PolicyName" --output json
```

The last output must be `[]`. The regular KMS and Secrets/ECR policies stay attached.

**Cluster target — VPC, two NAT gateways and private EKS.**

```bash
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" \
  -target=aws_eks_cluster.main -out="$CLUSTER_PLAN"
python scripts/check_plan.py cluster "$CLUSTER_PLAN"
```

Require `PLAN CHECK PASS` and an expected costed plan before applying:

```bash
terraform -chdir=terraform/workload apply "$CLUSTER_PLAN"
aws eks describe-cluster --name contact-form-eks \
  --query 'cluster.{Status:status,Version:version,PublicAPI:resourcesVpcConfig.endpointPublicAccess,PrivateAPI:resourcesVpcConfig.endpointPrivateAccess,OIDC:identity.oidc.issuer}' --output json
```

The earlier plan check must have passed. After apply, require `ACTIVE`, public API `false`, private API `true`. Stop on an unexpected action or IAM denial and investigate before continuing.

**Remaining workload — workers, SSM relay, RDS, ECR and IAM/IRSA.**

```bash
terraform -chdir=terraform/workload plan -input=false -var-file="$WORKLOAD_VARS" -out="$FULL_PLAN"
python scripts/check_plan.py full "$FULL_PLAN"
```

Require `PLAN CHECK PASS` and an expected costed plan before applying:

```bash
terraform -chdir=terraform/workload apply "$FULL_PLAN"
```

Before apply, the plan check must confirm two private `t3.medium` workers in separate AZs; a private `t3.micro` relay; private encrypted Multi-AZ PostgreSQL with an RDS-managed master secret; and no replacement or Terraform-created ALB. If the checker fails, inspect `terraform -chdir=terraform/workload show -no-color "$FULL_PLAN"` and stop.

## 4. Verify AWS resources before Ansible

Read only metadata; **never retrieve secret values**:

```bash
aws eks describe-cluster --name contact-form-eks \
  --query 'cluster.{Status:status,PublicAPI:resourcesVpcConfig.endpointPublicAccess,PrivateAPI:resourcesVpcConfig.endpointPrivateAccess}' --output json
aws rds describe-db-instances --db-instance-identifier contact-form-postgres \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Engine:Engine,MultiAZ:MultiAZ,Public:PubliclyAccessible,Encrypted:StorageEncrypted}' --output json
aws rds describe-db-instances --db-instance-identifier contact-form-postgres \
  --query 'DBInstances[0].MasterUserSecret.{ARN:SecretArn,Status:SecretStatus}' --output json
aws secretsmanager describe-secret \
  --secret-id "$(terraform -chdir=terraform/workload output -raw app_secret_arn)" \
  --query '{Name:Name,ARN:ARN}' --output json
```

Require available private encrypted Multi-AZ PostgreSQL and two distinct secret entries. The Ansible setup Job fills the restricted app secret later.

## 5. Deploy through the private EKS API

In **terminal A**, keep the TLS-verifying SSM tunnel open:

```bash
cd /home/limch/projects/aws-contact-form-eks
source "$HOME/.venvs/assignment/bin/activate"
export AWS_PROFILE=contact-form-deployer
python scripts/open_tunnel.py --profile "$AWS_PROFILE"
```

In **terminal B**, check the two Ready workers in different AZs, then run Ansible:

```bash
cd /home/limch/projects/aws-contact-form-eks
source "$HOME/.venvs/assignment/bin/activate"
export AWS_PROFILE=contact-form-deployer AWS_REGION=ap-southeast-1 AWS_DEFAULT_REGION=ap-southeast-1
export AWS_PAGER=""
export KUBECONFIG="$PWD/.local/kubeconfig"
kubectl --request-timeout=8s get nodes -L topology.kubernetes.io/zone
ansible-playbook -i ansible/inventory.ini ansible/deploy.yml
```

Ansible publishes the immutable image, creates the restricted SQL user, installs the ALB controller and applies the two-replica Deployment, Service and Ingress. It adds the Route 53 alias after the controller creates the ALB.

## 6. Verify the application and collect evidence

```bash
kubectl -n contact-form get deployment,pods,service,ingress -o wide
aws elbv2 describe-load-balancers \
  --query 'LoadBalancers[].{Name:LoadBalancerName,State:State.Code,DNS:DNSName}' --output json
curl -I --max-time 15 http://cheelong.xyz/
curl -I --max-time 15 https://cheelong.xyz/health/ready
```

Require two Ready Flask pods, one ClusterIP Service, one Ingress and one active project ALB. HTTP must redirect to HTTPS; HTTPS must validate the certificate and return `200`. In a browser, submit only synthetic data, for example `Demo User`, `demo@example.com`, `Hello from the live demo`. Show the thank-you page, then verify the row and repeat Ansible:

```bash
ansible-playbook -i ansible/inventory.ini ansible/verify.yml -e demo_email=demo@example.com
ansible-playbook -i ansible/inventory.ini ansible/deploy.yml
python scripts/show_findings.py --profile "$AWS_PROFILE"
```

The readback must match the synthetic submission and the second deploy should report `changed=0`. Capture live EKS, RDS, secret **metadata**, ALB, pod hardening, IRSA, logging, Config and FSBP evidence as described in [security.md](docs/security.md). Save reviewed PNGs under `docs/evidence/`. Do not tear down until the form, row and screenshots are confirmed complete.

## 7. Tear down only the workload

Keep the tunnel open while Ansible removes the DNS alias, Ingress and ALB:

```bash
ansible-playbook -i ansible/inventory.ini ansible/teardown.yml
```

Once the ALB is gone, use a **new** saved destroy plan in the Terraform shell and review it before apply:

```bash
DESTROY_PLAN="$PWD/.local/$(date -u +%Y%m%dT%H%M%SZ)-destroy.tfplan"
terraform -chdir=terraform/workload plan -destroy -input=false -var-file="$WORKLOAD_VARS" -out="$DESTROY_PLAN"
terraform -chdir=terraform/workload show -no-color "$DESTROY_PLAN"
```

After reviewing the exact destroy plan and confirming it contains only the disposable workload, apply it. Foundation values listed under **Changes to Outputs** are workload outputs being removed, not foundation resources being destroyed:

```bash
terraform -chdir=terraform/workload apply "$DESTROY_PLAN"
terraform -chdir=terraform/workload state list
python scripts/check_residual.py --profile "$AWS_PROFILE"
```

The state list must be empty and the scoped residual report must say `no_actionable_resources_observed` with no read errors. Workload teardown deletes RDS submissions and schedules customer KMS keys for deletion; bootstrap and foundation remain and may incur charges.

If the EIP disassociation permission error recurs, the first plan may leave two allocated IPs after the NAT gateways are gone. Inspect the residual report and confirm the project IPs have no association or network interface:

```bash
aws ec2 describe-addresses --filters \
  Name=tag:Project,Values=aws-contact-form-eks Name=tag:Lifecycle,Values=workload \
  --query 'Addresses[].{AllocationId:AllocationId,AssociationId:AssociationId,NetworkInterfaceId:NetworkInterfaceId}' --output json
```

Only if the remaining resources are those unassociated EIPs, create a **new** saved plan. Review that it deletes only `aws_eip.nat` before applying it:

```bash
RETRY_PLAN="$PWD/.local/$(date -u +%Y%m%dT%H%M%SZ)-destroy-eips.tfplan"
terraform -chdir=terraform/workload plan -destroy -input=false -var-file="$WORKLOAD_VARS" -out="$RETRY_PLAN"
terraform -chdir=terraform/workload show -no-color "$RETRY_PLAN"
```

```bash
terraform -chdir=terraform/workload apply "$RETRY_PLAN"
terraform -chdir=terraform/workload state list
python scripts/check_residual.py --profile "$AWS_PROFILE"
```

Stop and investigate if another resource remains, any read fails, or the retry plan includes anything beyond the EIPs. Never reuse a partly applied plan or remove state to conceal a live resource.
